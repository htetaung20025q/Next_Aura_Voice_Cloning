import io
import pytest
from fastapi.testclient import TestClient

from tests.conftest import create_mock_wav_bytes


def test_guest_cannot_generate_audio(client: TestClient):
    data = {
        "text": "Guest attempting to generate voice.",
    }
    res = client.post("/api/voice/generate", data=data)
    assert res.status_code == 401
    assert "sign in or create an account" in res.json()["detail"].lower()


def test_valid_wav_upload_generation(client: TestClient, user_token: str):
    wav_data = create_mock_wav_bytes(duration_sec=2.0)
    files = {"reference_audio": ("voice_sample.wav", wav_data, "audio/wav")}
    data = {
        "text": "Testing voice cloning with valid audio sample.",
        "ultimate_cloning": "true",
        "prompt_text": "Testing voice cloning reference transcript.",
        "cfg_value": "2.0",
    }
    res = client.post(
        "/api/voice/generate",
        headers={"Authorization": f"Bearer {user_token}"},
        data=data,
        files=files,
    )
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("audio/")


def test_reject_spoofed_text_file_as_audio(client: TestClient, user_token: str):
    fake_audio = b"This is not a real audio file, it is plain text."
    files = {"reference_audio": ("sample.wav", fake_audio, "audio/wav")}
    data = {
        "text": "Testing spoofed file rejection.",
        "ultimate_cloning": "true",
        "prompt_text": "Sample transcript.",
    }
    res = client.post(
        "/api/voice/generate",
        headers={"Authorization": f"Bearer {user_token}"},
        data=data,
        files=files,
    )
    assert res.status_code == 400
    assert "Unsupported or invalid audio format" in res.json()["detail"]


def test_reject_empty_audio_file(client: TestClient, user_token: str):
    files = {"reference_audio": ("empty.wav", b"", "audio/wav")}
    data = {
        "text": "Testing empty file rejection.",
        "ultimate_cloning": "true",
        "prompt_text": "Sample transcript.",
    }
    res = client.post(
        "/api/voice/generate",
        headers={"Authorization": f"Bearer {user_token}"},
        data=data,
        files=files,
    )
    assert res.status_code == 400


def test_ultimate_cloning_requires_reference_audio(client: TestClient, user_token: str):
    data = {
        "text": "Ultimate cloning without audio.",
        "ultimate_cloning": "true",
        "prompt_text": "Some transcript.",
    }
    res = client.post(
        "/api/voice/generate",
        headers={"Authorization": f"Bearer {user_token}"},
        data=data,
    )
    assert res.status_code == 400
    assert "requires an uploaded reference voice" in res.json()["detail"]


def test_ultimate_cloning_requires_prompt_transcript(client: TestClient, user_token: str):
    wav_data = create_mock_wav_bytes(duration_sec=2.0)
    files = {"reference_audio": ("sample.wav", wav_data, "audio/wav")}
    data = {
        "text": "Ultimate cloning without transcript.",
        "ultimate_cloning": "true",
        "prompt_text": "",
    }
    res = client.post(
        "/api/voice/generate",
        headers={"Authorization": f"Bearer {user_token}"},
        data=data,
        files=files,
    )
    assert res.status_code == 400
    assert "requires the reference transcript" in res.json()["detail"]
