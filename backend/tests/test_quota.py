import pytest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.generation import Generation
from app.models.user import User
from app.services.quota import FREE_LIMIT_MESSAGE, GUEST_GENERATION_MESSAGE


def test_guest_generation_rejected_with_401(client: TestClient):
    """
    Guests cannot generate voice without authentication.
    Does not consume any free generation.
    """
    res = client.post(
        "/api/voice/generate",
        data={"text": "Guest attempting to generate voice."},
    )
    assert res.status_code == 401
    assert "sign in or create an account" in res.json()["detail"].lower()


def test_free_user_can_generate_exactly_once(client: TestClient, regular_user: User, user_token: str):
    """
    Authenticated free user is allowed exactly 1 lifetime generation (<= 100 words).
    Subsequent attempts return 402 Payment Required.
    """
    headers = {"Authorization": f"Bearer {user_token}"}

    # Generation 1: 30 words (Allowed)
    res1 = client.post(
        "/api/voice/generate",
        headers=headers,
        data={"text": "Hello world this is the single free voice generation allowed for this new user."},
    )
    assert res1.status_code == 200
    assert res1.headers["content-type"].startswith("audio/")

    # Check /api/me status
    me_res = client.get("/api/me", headers=headers)
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["plan"] == "free"
    assert me_data["used_generations"] == 1
    assert me_data["credits"] == 0
    assert me_data["free_generations_used"] == 1
    assert me_data["free_generations_limit"] == 1

    # Generation 2: Should be REJECTED with 402 Payment Required
    res2 = client.post(
        "/api/voice/generate",
        headers=headers,
        data={"text": "Attempting second generation on free plan."},
    )
    assert res2.status_code == 402
    assert "free generation has been used" in res2.json()["detail"].lower()


def test_free_user_word_limit_100_words(client: TestClient, regular_user: User, user_token: str):
    """
    Free plan limits input text to 100 words maximum.
    Rejected requests do not consume the user's free generation.
    """
    headers = {"Authorization": f"Bearer {user_token}"}

    # Free plan allows up to 100 words. Try sending 101 words.
    long_script = "word " * 101
    res = client.post(
        "/api/voice/generate",
        headers=headers,
        data={"text": long_script},
    )
    assert res.status_code == 400
    assert "allows up to 100 words" in res.json()["detail"]

    # Since the request was rejected before reservation, user still has their 1 free generation
    res_valid = client.post(
        "/api/voice/generate",
        headers=headers,
        data={"text": "Short valid text."},
    )
    assert res_valid.status_code == 200


def test_failed_generation_does_not_consume_free_quota(
    client: TestClient,
    regular_user: User,
    user_token: str,
    db_session: Session,
):
    """
    If voice generation fails unexpectedly, the reservation is released
    and the free generation is NOT consumed.
    """
    headers = {"Authorization": f"Bearer {user_token}"}

    from app.services.voxcpm import voice_service

    # Simulate generation failure
    with patch.object(voice_service, "generate", side_effect=RuntimeError("Synthesis GPU crash")):
        res = client.post(
            "/api/voice/generate",
            headers=headers,
            data={"text": "Testing failure release."},
        )
        assert res.status_code == 502

    # Check /api/me: user should still have 1 generation remaining!
    me_res = client.get("/api/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["free_generations_used"] == 0
    assert me_res.json()["credits"] == 1

    # Now a real attempt should succeed
    res_success = client.post(
        "/api/voice/generate",
        headers=headers,
        data={"text": "Successful retry attempt."},
    )
    assert res_success.status_code == 200


def test_weekly_subscriber_quota(client: TestClient, weekly_user: User):
    from app.security.jwt import create_access_token
    token = create_access_token(user_id=weekly_user.id)
    headers = {"Authorization": f"Bearer {token}"}

    # Weekly user can generate up to 6 times (up to 5000 words each)
    for i in range(6):
        res = client.post(
            "/api/voice/generate",
            headers=headers,
            data={"text": f"Weekly generation text {i}"},
        )
        assert res.status_code == 200

    # 7th generation is rejected with 429
    res7 = client.post(
        "/api/voice/generate",
        headers=headers,
        data={"text": "Weekly generation 7"},
    )
    assert res7.status_code == 429


def test_unlimited_subscriber_quota(client: TestClient, unlimited_user: User):
    from app.security.jwt import create_access_token
    token = create_access_token(user_id=unlimited_user.id)
    headers = {"Authorization": f"Bearer {token}"}

    # Unlimited user can generate more than 6 times without getting blocked
    for i in range(8):
        res = client.post(
            "/api/voice/generate",
            headers=headers,
            data={"text": f"Unlimited generation text {i}"},
        )
        assert res.status_code == 200


def test_concurrent_quota_reservation_race_condition(client: TestClient, regular_user: User, user_token: str):
    """
    Test that concurrent requests from a free user cannot exceed the 1 free generation limit.
    Database unique constraint guarantees exactly 1 success.
    """
    headers = {"Authorization": f"Bearer {user_token}"}

    def do_generate(idx: int):
        return client.post(
            "/api/voice/generate",
            headers=headers,
            data={"text": f"Concurrent test generation {idx}"},
        )

    # Launch 5 concurrent generation requests simultaneously
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(do_generate, i) for i in range(5)]
        results = [f.result() for f in futures]

    status_codes = [r.status_code for r in results]
    success_count = status_codes.count(200)
    payment_required_count = status_codes.count(402)

    # Exactly 1 request must succeed (the single lifetime free generation) and the rest must be rejected with 402
    assert success_count == 1
    assert payment_required_count == 4
    assert success_count + payment_required_count == 5
