import logging
import os
import shutil
import tempfile
import uuid
import wave
from pathlib import Path
from typing import Optional, Tuple
from fastapi import HTTPException, UploadFile, status

from app.config import get_settings

logger = logging.getLogger(__name__)

# Magic byte signatures for supported audio formats
AUDIO_MAGIC_SIGNATURES = {
    "wav": [b"RIFF"],
    "mp3": [b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"],
    "ogg": [b"OggS"],
    "flac": [b"fLaC"],
    "m4a": [b"ftypM4A", b"ftypmp42", b"ftypisom", b"ftypMSNV"],
}


def detect_audio_format(header_bytes: bytes) -> Optional[str]:
    """
    Identifies audio container format by inspecting leading magic bytes.
    """
    if len(header_bytes) < 12:
        return None

    # Check WAV
    if header_bytes[:4] == b"RIFF" and header_bytes[8:12] == b"WAVE":
        return ".wav"

    # Check MP3 ID3 tag
    if header_bytes[:3] == b"ID3":
        return ".mp3"

    # Check MP3 sync frames
    if header_bytes[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2", b"\xff\xfa", b"\xff\xe3"):
        return ".mp3"

    # Check Ogg
    if header_bytes[:4] == b"OggS":
        return ".ogg"

    # Check FLAC
    if header_bytes[:4] == b"fLaC":
        return ".flac"

    # Check MP4 / M4A ftyp box
    if len(header_bytes) >= 12 and header_bytes[4:8] == b"ftyp":
        brand = header_bytes[8:12]
        if brand in (b"M4A ", b"mp42", b"isom", b"MSNV", b"dash"):
            return ".m4a"

    return None


def inspect_audio_with_mutagen(file_path: Path) -> Tuple[float, int, int]:
    """
    Inspects audio file using mutagen.
    Returns (duration_seconds, sample_rate, channels).
    """
    try:
        import mutagen
        audio = mutagen.File(str(file_path))
        if audio is None or audio.info is None:
            raise ValueError("Unrecognized or corrupted audio stream.")

        duration = getattr(audio.info, "length", 0.0)
        sample_rate = getattr(audio.info, "sample_rate", 0)
        channels = getattr(audio.info, "channels", 1)
        return float(duration), int(sample_rate), int(channels)
    except Exception as e:
        logger.warning(f"Mutagen inspection failed ({e}). Attempting fallback inspect.")
        raise ValueError(f"Invalid audio structure: {e}") from e


def inspect_audio_with_wave(file_path: Path) -> Tuple[float, int, int]:
    """
    Fallback inspector for WAV files using Python's standard wave library.
    """
    try:
        with wave.open(str(file_path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            channels = wf.getnchannels()
            duration = frames / float(rate) if rate > 0 else 0.0
            return duration, rate, channels
    except Exception as e:
        raise ValueError(f"Invalid WAV file: {e}") from e


async def validate_and_save_audio_upload(file: UploadFile) -> Path:
    """
    Stream-validates and safely saves an uploaded reference audio file.
    Enforces maximum size, content type/magic bytes, audio structure, and duration.
    Returns the absolute path to the safely saved temporary audio file.
    """
    settings = get_settings()

    # Create dedicated secure temp directory
    temp_dir = Path(tempfile.gettempdir()) / "vox_audio_uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)

    safe_id = uuid.uuid4().hex
    temp_dest = temp_dir / f"upload_{safe_id}.tmp"

    total_bytes = 0
    header_bytes = bytearray()

    try:
        with open(temp_dest, "wb") as f_out:
            while True:
                chunk = await file.read(64 * 1024)  # 64 KB chunk
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > settings.MAX_AUDIO_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Audio file is too large. Maximum allowed size is {settings.MAX_AUDIO_BYTES // (1024*1024)} MB.",
                    )
                if len(header_bytes) < 32:
                    header_bytes.extend(chunk[: 32 - len(header_bytes)])
                f_out.write(chunk)

        if total_bytes == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded audio file is empty.",
            )

        # Detect audio format
        detected_ext = detect_audio_format(bytes(header_bytes))
        if not detected_ext:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported or invalid audio format. Supported formats: WAV, MP3, OGG, FLAC, M4A.",
            )

        # Rename to verified extension
        verified_path = temp_dir / f"audio_{safe_id}{detected_ext}"
        shutil.move(temp_dest, verified_path)

        # Inspect duration and properties
        duration = 0.0
        sample_rate = 0
        channels = 1
        try:
            duration, sample_rate, channels = inspect_audio_with_mutagen(verified_path)
        except Exception:
            if detected_ext == ".wav":
                try:
                    duration, sample_rate, channels = inspect_audio_with_wave(verified_path)
                except Exception as e:
                    verified_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="The uploaded audio file is malformed or corrupted.",
                    ) from e
            else:
                verified_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Could not decode the uploaded audio file. Please ensure it is a valid audio file.",
                )

        if duration < settings.MIN_AUDIO_DURATION_SECONDS:
            verified_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Audio sample is too short ({duration:.1f}s). Must be at least {settings.MIN_AUDIO_DURATION_SECONDS}s.",
            )

        if duration > settings.MAX_AUDIO_DURATION_SECONDS:
            verified_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Audio sample is too long ({duration:.1f}s). Maximum allowed reference audio duration is {settings.MAX_AUDIO_DURATION_SECONDS}s.",
            )

        return verified_path

    except HTTPException:
        temp_dest.unlink(missing_ok=True)
        raise
    except Exception as e:
        temp_dest.unlink(missing_ok=True)
        logger.error(f"Unexpected error while processing audio upload: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to validate audio upload.",
        ) from e
