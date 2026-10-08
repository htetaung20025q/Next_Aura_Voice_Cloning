import io
import os
import struct
import wave
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.services.style_presets import (
    CATEGORIES,
    STYLE_PRESETS,
    get_preset,
    get_preset_ids,
    list_categories,
    list_presets,
)
from app.services.voice_style_processor import voice_style_processor
from tests.conftest import create_mock_wav_bytes


def test_all_presets_load_correctly():
    """Verify that every style preset is properly defined with valid parameters."""
    preset_ids = get_preset_ids()
    assert len(preset_ids) >= 30, f"Expected at least 30 presets, found {len(preset_ids)}"

    for preset in STYLE_PRESETS:
        assert preset.id, "Preset must have a non-empty ID"
        assert preset.name, "Preset must have a non-empty name"
        assert preset.myanmar_name, f"Preset {preset.id} must have a Myanmar translation"
        assert preset.category in ["character", "horror", "story", "comedy", "cinematic", "environment"]
        assert 0.0 <= preset.default_intensity <= 1.0
        effect_obj = get_preset(preset.id)
        assert effect_obj is not None
        assert effect_obj.id == preset.id



def test_categories_listing():
    """Verify categories list contains all 6 required groupings."""
    cats = list_categories()
    cat_ids = [c.id for c in cats]
    expected = ["character", "horror", "story", "comedy", "cinematic", "environment"]
    for exp in expected:
        assert exp in cat_ids, f"Category {exp} missing from categories list"


def test_get_styles_api(client: TestClient):
    """Test GET /api/voice/styles returns all categories and presets."""
    res = client.get("/api/voice/styles")
    assert res.status_code == 200
    data = res.json()
    assert "categories" in data
    assert "presets" in data
    assert len(data["presets"]) == len(STYLE_PRESETS)
    assert len(data["categories"]) == len(CATEGORIES)


def test_get_single_style_preset_api(client: TestClient):
    """Test GET /api/voice/styles/{preset_id}."""
    res = client.get("/api/voice/styles/ghost")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == "ghost"
    assert "သရဲ" in data["myanmar_name"]

    # Invalid preset
    res_invalid = client.get("/api/voice/styles/non_existent_preset_xyz")
    assert res_invalid.status_code == 404


def test_apply_style_on_mock_audio_direct():
    """Test VoiceStyleProcessor directly on raw WAV bytes."""
    wav_bytes = create_mock_wav_bytes(duration_sec=1.5, sample_rate=24000)
    audio_id = voice_style_processor.register_audio(
        # create temp file
        _create_temp_wav(wav_bytes)
    )

    # Apply ghost style
    out_path, meta = asyncio_run(
        voice_style_processor.apply_style(
            audio_source=audio_id,
            style_id="ghost",
            intensity=0.8,
            audio_id=audio_id,
        )
    )

    assert out_path.exists()
    assert out_path.stat().st_size > 100
    assert meta["preset_id"] == "ghost"
    assert meta["intensity"] == 0.8
    assert meta["cached"] is False

    # Second call should be a cache hit
    out_path_cached, meta_cached = asyncio_run(
        voice_style_processor.apply_style(
            audio_source=audio_id,
            style_id="ghost",
            intensity=0.8,
            audio_id=audio_id,
        )
    )
    assert out_path_cached == out_path
    assert meta_cached["cached"] is True


def test_original_audio_remains_unchanged():
    """Verify that applying styles never modifies the original audio file."""
    wav_bytes = create_mock_wav_bytes(duration_sec=1.0, sample_rate=24000)
    temp_file = _create_temp_wav(wav_bytes)
    orig_size = os.path.getsize(temp_file)

    audio_id = voice_style_processor.register_audio(temp_file)
    orig_stored_path = voice_style_processor.get_audio_path(audio_id)
    assert orig_stored_path is not None
    orig_stored_size = orig_stored_path.stat().st_size

    # Apply multiple styles
    for style_name in ["deep", "robot", "villain", "demon", "megaphone"]:
        asyncio_run(
            voice_style_processor.apply_style(
                audio_source=audio_id,
                style_id=style_name,
                intensity=0.9,
                audio_id=audio_id,
            )
        )

    # Original audio file in store must remain exactly identical
    assert orig_stored_path.stat().st_size == orig_stored_size
    with open(orig_stored_path, "rb") as f:
        assert f.read() == wav_bytes


def test_style_processing_on_silence_and_short_audio():
    """Verify DSP engine handles zero-amplitude silence and very short audio without NaN or crash."""
    for duration in [0.05, 0.2, 0.5, 1.0]:
        wav_bytes = create_mock_wav_bytes(duration_sec=duration, sample_rate=24000)
        temp_file = _create_temp_wav(wav_bytes)
        audio_id = voice_style_processor.register_audio(temp_file)

        for style in ["ghost", "robot", "demon", "radio", "underwater"]:
            out_path, meta = asyncio_run(
                voice_style_processor.apply_style(
                    audio_source=audio_id,
                    style_id=style,
                    intensity=0.85,
                )
            )
            assert out_path.exists()
            assert out_path.stat().st_size > 44


def test_apply_style_api_with_audio_id(client: TestClient, user_token: str):
    """Test POST /api/voice/style using audio_id."""
    # 1. Generate audio first
    gen_res = client.post(
        "/api/voice/generate",
        headers={"Authorization": f"Bearer {user_token}"},
        data={"text": "Test speech for voice style processing."},
    )
    assert gen_res.status_code == 200
    audio_id = gen_res.headers.get("X-Audio-Id")
    assert audio_id is not None

    # 2. Apply Ghost Style
    style_res = client.post(
        "/api/voice/style",
        headers={"Authorization": f"Bearer {user_token}"},
        data={
            "audio_id": audio_id,
            "style": "ghost",
            "intensity": "0.75",
        },
    )
    assert style_res.status_code == 200
    assert style_res.headers["content-type"].startswith("audio/")
    assert style_res.headers["X-Preset-Id"] == "ghost"
    assert style_res.headers["X-Styled-Audio"] == "true"
    assert float(style_res.headers["X-Intensity"]) == 0.75

    # 3. Apply Deep Voice style on the same audio without re-generating TTS
    style_res_2 = client.post(
        "/api/voice/style",
        headers={"Authorization": f"Bearer {user_token}"},
        data={
            "audio_id": audio_id,
            "style": "deep",
            "intensity": "0.85",
        },
    )
    assert style_res_2.status_code == 200
    assert style_res_2.headers["X-Preset-Id"] == "deep"


def test_apply_style_api_with_direct_file_upload(client: TestClient, user_token: str):
    """Test POST /api/voice/style with direct audio file upload."""
    wav_bytes = create_mock_wav_bytes(duration_sec=1.5, sample_rate=24000)
    files = {"audio_file": ("sample.wav", wav_bytes, "audio/wav")}
    data = {"style": "robot", "intensity": "0.8"}

    res = client.post(
        "/api/voice/style",
        headers={"Authorization": f"Bearer {user_token}"},
        data=data,
        files=files,
    )
    assert res.status_code == 200
    assert res.headers["X-Preset-Id"] == "robot"
    assert len(res.content) > 100


def test_reject_invalid_style_preset(client: TestClient, user_token: str):
    """Test rejection of non-existent style preset."""
    wav_bytes = create_mock_wav_bytes(duration_sec=1.0)
    files = {"audio_file": ("sample.wav", wav_bytes, "audio/wav")}
    data = {"style": "unsupported_alien_preset_xyz", "intensity": "0.8"}

    res = client.post(
        "/api/voice/style",
        headers={"Authorization": f"Bearer {user_token}"},
        data=data,
        files=files,
    )
    assert res.status_code == 400
    assert "Invalid style preset" in res.json()["detail"]


def test_intensity_bounds(client: TestClient, user_token: str):
    """Test intensity parameter validation."""
    wav_bytes = create_mock_wav_bytes(duration_sec=1.0)
    files = {"audio_file": ("sample.wav", wav_bytes, "audio/wav")}

    # Negative intensity
    res_neg = client.post(
        "/api/voice/style",
        headers={"Authorization": f"Bearer {user_token}"},
        data={"style": "deep", "intensity": "-0.5"},
        files=files,
    )
    assert res_neg.status_code == 400

    # Greater than 100
    files2 = {"audio_file": ("sample.wav", wav_bytes, "audio/wav")}
    res_high = client.post(
        "/api/voice/style",
        headers={"Authorization": f"Bearer {user_token}"},
        data={"style": "deep", "intensity": "150"},
        files=files2,
    )
    assert res_high.status_code == 400


def test_style_processing_does_not_consume_generation_quota(client: TestClient, user_token: str):
    """Applying styles to already generated audio must not count towards weekly or free generation quota."""
    # 1. Check initial quota
    q_initial = client.get("/api/voice/quota", headers={"Authorization": f"Bearer {user_token}"}).json()

    # 2. Perform 1 voice generation
    client.post(
        "/api/voice/generate",
        headers={"Authorization": f"Bearer {user_token}"},
        data={"text": "Quota test script."},
    )

    q_after_gen = client.get("/api/voice/quota", headers={"Authorization": f"Bearer {user_token}"}).json()
    assert q_after_gen["free_generations_used"] == q_initial["free_generations_used"] + 1

    # 3. Apply 5 different styles to the audio
    wav_bytes = create_mock_wav_bytes(duration_sec=1.0)
    for style in ["ghost", "deep", "robot", "villain", "radio"]:
        files = {"audio_file": ("sample.wav", wav_bytes, "audio/wav")}
        res = client.post(
            "/api/voice/style",
            headers={"Authorization": f"Bearer {user_token}"},
            data={"style": style, "intensity": "0.8"},
            files=files,
        )
        assert res.status_code == 200

    # 4. Quota must NOT have increased from styling!
    q_after_styles = client.get("/api/voice/quota", headers={"Authorization": f"Bearer {user_token}"}).json()
    assert q_after_styles["free_generations_used"] == q_after_gen["free_generations_used"]


def test_effects_api_json_endpoint(client: TestClient, user_token: str):
    """Test dedicated POST /api/voice/effects JSON endpoint."""
    # 1. Generate original voice audio
    gen_res = client.post(
        "/api/voice/generate",
        headers={"Authorization": f"Bearer {user_token}"},
        data={"text": "This is a voice generation for character effects endpoint testing."},
    )
    assert gen_res.status_code == 200
    audio_id = gen_res.headers.get("X-Audio-Id")
    assert audio_id is not None

    # 2. Call POST /api/voice/effects with JSON payload
    effect_res = client.post(
        "/api/voice/effects",
        headers={
            "Authorization": f"Bearer {user_token}",
            "Content-Type": "application/json",
        },
        json={
            "audio_id": audio_id,
            "preset": "ghost",
            "intensity": 70,
        },
    )
    assert effect_res.status_code == 200
    data = effect_res.json()
    assert data["audio_id"] == audio_id
    assert data["preset"] == "ghost"
    assert data["intensity"] == 0.7 or data["intensity"] == 70.0
    assert data["intensity_percent"] == 70
    assert "url" in data
    assert "/api/voice/audio/" in data["url"]
    assert "ghost" in data["url"]

    # 3. Verify the generated audio URL is accessible
    audio_url = data["url"]
    get_res = client.get(audio_url)
    assert get_res.status_code == 200
    assert get_res.headers["content-type"].startswith("audio/")
    assert len(get_res.content) > 100


def test_presets_acoustic_distinctiveness():
    """
    Verify that key character presets produce distinct waveforms and audio characteristics
    and are not identical or simple trivial pitch shifts.
    Tested presets: Original, Ghost, Demon, Funny, Villain, Story Narrator, Horror Whisper, Robot, Radio, Cinematic.
    """
    # Create harmonic rich voice-like test signal (fundamental + formants + vibrato)
    sample_rate = 24000
    duration_sec = 1.0
    n_samples = int(sample_rate * duration_sec)
    import math

    t_samples = [i / sample_rate for i in range(n_samples)]
    raw_signal = [
        0.4 * math.sin(2.0 * math.pi * 220.0 * t)  # A3 fundamental
        + 0.25 * math.sin(2.0 * math.pi * 440.0 * t)  # 1st harmonic
        + 0.15 * math.sin(2.0 * math.pi * 880.0 * t)  # 2nd harmonic
        + 0.10 * math.sin(2.0 * math.pi * 1760.0 * t) # formant
        + 0.05 * math.sin(2.0 * math.pi * 3520.0 * t) # air
        for t in t_samples
    ]

    target_presets = [
        "ghost",
        "demon",
        "funny",
        "villain",
        "story_narrator",
        "horror_whisper",
        "robot",
        "radio",
        "cinematic",
    ]

    processed_waveforms = {"original": list(raw_signal)}

    for pid in target_presets:
        preset_obj = get_preset(pid)
        assert preset_obj is not None, f"Preset {pid} must exist"
        styled = preset_obj.process_effect(list(raw_signal), sample_rate, intensity=0.85)
        assert len(styled) > 0, f"Preset {pid} output must not be empty"
        # Verify no extreme clipping/NaN
        for s in styled:
            assert not math.isnan(s), f"Preset {pid} produced NaN"
            assert -1.05 <= s <= 1.05, f"Preset {pid} produced clipped sample: {s}"
        processed_waveforms[pid] = styled

    # Compare pair-wise mean absolute differences
    preset_keys = list(processed_waveforms.keys())
    for i in range(len(preset_keys)):
        for j in range(i + 1, len(preset_keys)):
            name_a = preset_keys[i]
            name_b = preset_keys[j]
            sig_a = processed_waveforms[name_a]
            sig_b = processed_waveforms[name_b]

            min_len = min(len(sig_a), len(sig_b))
            diffs = [abs(sig_a[k] - sig_b[k]) for k in range(min_len)]
            mean_diff = sum(diffs) / float(min_len)

            # Assert that presets are acoustically and mathematically distinct
            assert mean_diff > 0.03, (
                f"Presets '{name_a}' and '{name_b}' are too similar (mean absolute diff={mean_diff:.4f}). "
                f"They must have distinct DSP processing chains."
            )


def test_apply_style_on_non_riff_audio():
    """Verify that non-RIFF audio files (e.g. OGG, MP3) are decoded and processed without crashing on RIFF error."""
    import subprocess
    import tempfile
    wav_bytes = create_mock_wav_bytes(duration_sec=1.0, sample_rate=24000)
    temp_wav = _create_temp_wav(wav_bytes)

    # Encode to OGG container
    temp_ogg = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
    temp_ogg.close()
    subprocess.run([
        "gst-launch-1.0", "-q",
        "filesrc", f"location={temp_wav}",
        "!", "decodebin",
        "!", "audioconvert",
        "!", "vorbisenc",
        "!", "oggmux",
        "!", "filesink", f"location={temp_ogg.name}"
    ], capture_output=True)

    # Register non-RIFF audio
    audio_id = voice_style_processor.register_audio(temp_ogg.name)
    assert audio_id is not None

    # Apply hero style
    out_path, meta = asyncio_run(
        voice_style_processor.apply_style(
            audio_source=audio_id,
            style_id="hero",
            intensity=0.8,
            audio_id=audio_id,
        )
    )
    assert out_path.exists()
    assert out_path.stat().st_size > 44
    assert meta["preset_id"] == "hero"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_temp_wav(wav_bytes: bytes) -> str:
    import tempfile
    t = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    t.write(wav_bytes)
    t.close()
    return t.name


def asyncio_run(coro):
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

