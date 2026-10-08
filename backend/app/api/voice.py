import logging
from pathlib import Path
from typing import List, Optional
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import (
    AnonymousSession,
    get_anonymous_session,
    get_db,
    get_optional_current_user,
)
from app.config import get_settings
from app.models.user import User
from app.schemas.voice import (
    StyleCategoryOut,
    StyleListResponse,
    StylePresetOut,
    StyleProcessResponse,
    VoiceEffectRequest,
    VoiceEffectResponse,
    VoiceQuotaOut,
)
from app.security.rate_limit import check_rate_limit
from app.services.audio_validator import validate_and_save_audio_upload
from app.services.quota import (
    PLANS,
    complete_generation,
    get_next_week_reset,
    get_usage_summary,
    release_generation,
    reserve_generation_quota,
)
from app.services.style_presets import (
    CATEGORIES,
    STYLE_PRESETS,
    get_preset,
    get_preset_ids,
    list_categories,
    list_presets,
)
from app.services.voice_style_processor import voice_style_processor
from app.services.voxcpm import voice_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/voice", tags=["Voice Studio"])


def count_words(text: str) -> int:
    return len(text.strip().split())


def cleanup_temp_file(path: Optional[Path]):
    if path and path.exists():
        try:
            path.unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"Could not delete temp file {path}: {e}")


@router.get(
    "/quota",
    response_model=VoiceQuotaOut,
    summary="Get voice generation quota status for current user or anonymous session",
)
def get_voice_quota(
    user: Optional[User] = Depends(get_optional_current_user),
    anon_session: AnonymousSession = Depends(get_anonymous_session),
    db: Session = Depends(get_db),
):
    summary = get_usage_summary(db, user)
    plan_info = PLANS.get(summary["plan"], PLANS["free"])
    weekly_limit = plan_info["weekly_generations"]
    next_reset = get_next_week_reset()

    return VoiceQuotaOut(
        id=user.id if user else None,
        email=user.email if user else None,
        plan=summary["plan"],
        is_pro=summary["is_pro"],
        subscription_active=summary["is_pro"],
        used_generations=summary["used_generations"],
        weekly_generations=weekly_limit,
        weekly_generations_used=summary["used_generations"] if summary["generation_period"] == "weekly" else 0,
        weekly_generations_limit=weekly_limit,
        max_words=summary["max_words"],
        words_limit=summary["max_words"],
        credits=summary["credits"],
        token_usage=summary["token_usage"],
        generation_limit=summary["generation_limit"],
        generation_period=summary["generation_period"],
        free_generations_used=summary["free_generations_used"],
        free_generations_limit=summary["free_generations_limit"],
        active_from=user.plan_active_from if user else None,
        active_until=user.plan_active_until if user else None,
        resets_at=next_reset,
    )


@router.get(
    "/styles",
    response_model=StyleListResponse,
    summary="List all voice style preset categories and presets",
)
def get_voice_styles(category: Optional[str] = Query(None, description="Filter presets by category")):
    presets = list_presets(category)
    return StyleListResponse(
        categories=[
            StyleCategoryOut(
                id=c.id,
                name=c.name,
                myanmar_name=c.myanmar_name,
                description=c.description,
                icon=c.icon,
            )
            for c in CATEGORIES
        ],
        presets=[
            StylePresetOut(
                id=p.id,
                name=p.name,
                myanmar_name=p.myanmar_name,
                category=p.category,
                description=p.description,
                icon=p.icon,
                default_intensity=p.default_intensity,
                tags=p.tags,
            )
            for p in presets
        ],
    )


@router.get(
    "/styles/{preset_id}",
    response_model=StylePresetOut,
    summary="Get details for a specific voice style preset",
)
def get_style_preset_detail(preset_id: str):
    preset = get_preset(preset_id)
    if not preset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Voice style preset '{preset_id}' not found.",
        )
    return StylePresetOut(
        id=preset.id,
        name=preset.name,
        myanmar_name=preset.myanmar_name,
        category=preset.category,
        description=preset.description,
        icon=preset.icon,
        default_intensity=preset.default_intensity,
        tags=preset.tags,
    )


@router.post(
    "/style",
    summary="Apply voice style / character effects to generated audio without regenerating TTS",
)
async def apply_voice_style(
    request: Request,
    generated_audio_id: Optional[str] = Form(None, description="Generated audio ID from voice synthesis"),
    audio_id: Optional[str] = Form(None, description="Audio ID alias"),
    style: str = Form(..., description="Style preset ID (e.g. ghost, deep, robot, etc.)"),
    intensity: float = Form(0.8, description="Effect intensity from 0.0 to 1.0 (or 0 to 100)"),
    audio_file: Optional[UploadFile] = File(None, description="Direct audio upload if audio_id is not provided"),
    user: Optional[User] = Depends(get_optional_current_user),
    anon_session: AnonymousSession = Depends(get_anonymous_session),
):
    settings = get_settings()

    # Rate limiting
    rate_limit_id = f"user:{user.id}" if user else f"anon:{anon_session.anon_id}"
    check_rate_limit(
        request=request,
        scope="voice_style",
        max_requests=settings.RATE_LIMIT_GENERATE_MAX * 5,
        window_seconds=settings.RATE_LIMIT_GENERATE_WINDOW_SECONDS,
        identifier=rate_limit_id,
    )

    # Validate preset
    preset_slug = style.lower().strip()
    preset = get_preset(preset_slug)
    if not preset:
        valid_presets = ", ".join(get_preset_ids()[:8]) + "..."
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid style preset '{style}'. Valid options include: {valid_presets}",
        )

    # Validate intensity bounds
    if intensity < 0.0 or intensity > 100.0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Intensity must be between 0.0 and 1.0 (or 0 and 100).",
        )
    normalized_intensity = intensity / 100.0 if intensity > 1.0 else intensity

    # Resolve audio source
    resolved_id = generated_audio_id or audio_id

    try:
        if audio_file:
            styled_path, meta = await voice_style_processor.apply_style(
                audio_source=audio_file,
                style_id=preset.id,
                intensity=normalized_intensity,
                audio_id=resolved_id,
            )
        elif resolved_id:
            styled_path, meta = await voice_style_processor.apply_style(
                audio_source=resolved_id,
                style_id=preset.id,
                intensity=normalized_intensity,
                audio_id=resolved_id,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either 'generated_audio_id' or 'audio_file' must be provided.",
            )

        output_path = Path(styled_path)
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate styled audio variant.",
            )

        return FileResponse(
            path=str(output_path),
            media_type="audio/wav",
            filename=f"next-aura-{preset.id}.wav",
            headers={
                "Cache-Control": "public, max-age=86400",
                "X-Styled-Audio": "true",
                "X-Audio-Id": str(meta["audio_id"]),
                "X-Preset-Id": str(meta["preset_id"]),
                "X-Preset-Name": str(meta["preset_name"]),
                "X-Category": str(meta["category"]),
                "X-Intensity": str(meta["intensity"]),
                "X-Processing-Time-Ms": str(meta["processing_time_ms"]),
                "X-Cached": str(meta["cached"]).lower(),
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Voice style processing failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not apply voice style '{style}': {str(e)}",
        )


@router.post(
    "/effects",
    response_model=VoiceEffectResponse,
    summary="Apply voice character effect preset and return styled audio URL and metadata",
)
async def apply_voice_effects_api(
    request: Request,
    payload: VoiceEffectRequest,
    user: Optional[User] = Depends(get_optional_current_user),
    anon_session: AnonymousSession = Depends(get_anonymous_session),
):
    settings = get_settings()

    # Rate limiting
    rate_limit_id = f"user:{user.id}" if user else f"anon:{anon_session.anon_id}"
    check_rate_limit(
        request=request,
        scope="voice_effects",
        max_requests=settings.RATE_LIMIT_GENERATE_MAX * 5,
        window_seconds=settings.RATE_LIMIT_GENERATE_WINDOW_SECONDS,
        identifier=rate_limit_id,
    )

    preset_slug = payload.preset.lower().strip()
    preset = get_preset(preset_slug)
    if not preset:
        valid_presets = ", ".join(get_preset_ids()[:8]) + "..."
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid preset '{payload.preset}'. Valid options include: {valid_presets}",
        )

    # Validate intensity bounds (0-100 or 0.0-1.0)
    raw_intensity = payload.intensity
    if raw_intensity < 0.0 or raw_intensity > 100.0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Intensity must be between 0 and 100 (or 0.0 and 1.0).",
        )
    normalized_intensity = raw_intensity / 100.0 if raw_intensity > 1.0 else raw_intensity

    resolved_audio_id = payload.audio_id or payload.generated_audio_id
    if not resolved_audio_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either 'audio_id' or 'generated_audio_id' must be provided.",
        )

    try:
        styled_path, meta = await voice_style_processor.apply_style(
            audio_source=resolved_audio_id,
            style_id=preset.id,
            intensity=normalized_intensity,
            audio_id=resolved_audio_id,
        )

        audio_url = f"/api/voice/audio/{meta['audio_id']}?style={meta['preset_id']}&intensity={meta['intensity']}"

        return VoiceEffectResponse(
            audio_id=meta["audio_id"],
            preset=meta["preset_id"],
            preset_name=meta.get("preset_name"),
            category=meta.get("category"),
            intensity=meta["intensity"],
            intensity_percent=meta["intensity_percent"],
            duration_seconds=meta.get("duration_seconds"),
            sample_rate=meta.get("sample_rate"),
            cached=meta.get("cached", False),
            processing_time_ms=meta.get("processing_time_ms", 0.0),
            url=audio_url,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Voice effects processing failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not apply voice effect '{payload.preset}': {str(e)}",
        )


@router.get(
    "/audio/{audio_id}",
    summary="Stream or download original or styled audio variant",
)
def get_audio_file(
    audio_id: str,
    style: Optional[str] = Query(None, description="Optional style preset ID"),
    intensity: float = Query(0.8, description="Effect intensity"),
):
    path = voice_style_processor.get_audio_path(audio_id=audio_id, style_id=style, intensity=intensity)
    if not path or not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio file not found or expired.",
        )
    return FileResponse(
        path=str(path),
        media_type="audio/wav",
        filename=f"next-aura-{audio_id}.wav",
        headers={
            "Cache-Control": "public, max-age=86400",
            "X-Audio-Id": audio_id,
        },
    )


@router.post(
    "/generate",
    summary="Generate cloned voice audio with VoxCPM",
)
async def generate_voice(
    request: Request,
    background_tasks: BackgroundTasks,
    text: str = Form(..., description="Text script to synthesize", max_length=50000),
    control_instruction: str = Form("", description="Voice style / control instruction", max_length=500),
    ultimate_cloning: bool = Form(False, description="Enable high-fidelity cloning mode"),
    prompt_text: str = Form("", description="Transcript of reference audio", max_length=2000),
    cfg_value: float = Form(1.8, description="Guidance scale (1.0 to 3.0, calibrated for high speaker fidelity)"),
    normalize: bool = Form(False, description="Normalize text/audio input"),
    denoise: bool = Form(False, description="Apply ZipEnhancer denoising filter (disabled by default to preserve reference vocal texture and timbre)"),
    reference_audio: Optional[UploadFile] = File(None, description="Reference voice audio sample (primary speaker anchor)"),
    user: Optional[User] = Depends(get_optional_current_user),
    anon_session: AnonymousSession = Depends(get_anonymous_session),
    db: Session = Depends(get_db),
):
    settings = get_settings()

    user_id_val = None
    if user is not None:
        try:
            user_id_val = user.id
        except Exception:
            user_id_val = None

    # Rate limiting
    rate_limit_id = f"user:{user_id_val}" if user_id_val is not None else f"anon:{anon_session.anon_id}"
    check_rate_limit(
        request=request,
        scope="voice_generate",
        max_requests=settings.RATE_LIMIT_GENERATE_MAX,
        window_seconds=settings.RATE_LIMIT_GENERATE_WINDOW_SECONDS,
        identifier=rate_limit_id,
    )

    # 1. Validate text input
    cleaned_text = text.strip()
    if not cleaned_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Text script cannot be empty.",
        )
    wc = count_words(cleaned_text)

    # 2. Validate CFG
    if not (1.0 <= cfg_value <= 3.0):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CFG guidance value must be between 1.0 and 3.0.",
        )

    # 3. Validate ultimate cloning requirements
    if ultimate_cloning:
        if not reference_audio:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ultimate Cloning requires an uploaded reference voice audio file.",
            )
        if not prompt_text.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ultimate Cloning requires the reference transcript prompt text.",
            )

    # 4. Atomic quota reservation & plan validation
    generation_record, plan_name = reserve_generation_quota(
        db=db,
        user=user,
        anonymous_id=anon_session.anon_id if not user else None,
        ip_abuse_hash=anon_session.ip_hash if not user else None,
        word_count=wc,
    )

    saved_audio_path: Optional[Path] = None
    try:
        # 5. Process audio upload if provided
        if reference_audio:
            saved_audio_path = await validate_and_save_audio_upload(reference_audio)

        # 6. Execute voice synthesis with concurrency & resource protection
        user_tracking_id = f"user_{user_id_val}" if user_id_val is not None else f"anon_{anon_session.anon_id}"
        generated_file_path_str = await voice_service.generate(
            text=cleaned_text,
            control_instruction=control_instruction.strip(),
            reference_audio_path=str(saved_audio_path) if saved_audio_path else None,
            ultimate_cloning=ultimate_cloning,
            prompt_text=prompt_text.strip(),
            cfg_value=cfg_value,
            normalize=normalize,
            denoise=denoise,
            user_identifier=user_tracking_id,
        )

        # 7. Mark reservation as completed
        complete_generation(db=db, generation_id=generation_record.id)

        # Schedule temp cleanup in background
        if saved_audio_path:
            background_tasks.add_task(cleanup_temp_file, saved_audio_path)

        output_path = Path(generated_file_path_str)
        media_type = "audio/wav" if output_path.suffix.lower() == ".wav" else "audio/mpeg"

        # 8. Register original generated audio in voice style processor cache
        registered_audio_id = voice_style_processor.register_audio(output_path)

        file_response = FileResponse(
            path=str(output_path),
            media_type=media_type,
            filename="next-aura-voice.mp3" if media_type == "audio/mpeg" else "next-aura-voice.wav",
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "Pragma": "no-cache",
                "X-Audio-Id": registered_audio_id,
                "X-Generation-Id": str(generation_record.id),
            },
        )

        if not user and anon_session.cookie_to_set:
            file_response.set_cookie(
                key=settings.ANONYMOUS_COOKIE_NAME,
                value=anon_session.cookie_to_set,
                max_age=60 * 60 * 24 * 30,
                httponly=True,
                secure=bool(settings.COOKIE_SECURE),
                samesite=settings.COOKIE_SAMESITE,
            )

        return file_response

    except HTTPException:
        # Release reservation so user is not billed for system/validation errors
        release_generation(db=db, generation_id=generation_record.id)
        if saved_audio_path:
            cleanup_temp_file(saved_audio_path)
        raise
    except Exception as exc:
        release_generation(db=db, generation_id=generation_record.id)
        if saved_audio_path:
            cleanup_temp_file(saved_audio_path)
        logger.error(f"Voice generation unhandled failure: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Voice synthesis error: {str(exc)}" if str(exc) else "Voice synthesis failed. Please try again later.",
        ) from exc
