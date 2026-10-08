import os
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.models.user import User


def test_admin_endpoint_unauthorized_for_anonymous(client: TestClient):
    res = client.get("/api/admin/purchases")
    assert res.status_code == 401


def test_admin_endpoint_forbidden_for_regular_user(client: TestClient, user_token: str):
    res = client.get(
        "/api/admin/purchases",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert res.status_code == 403
    assert "Administrator privileges required" in res.json()["detail"]


def test_admin_endpoint_accessible_by_admin(client: TestClient, admin_token: str):
    res = client.get(
        "/api/admin/purchases",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_tampered_jwt_token_rejected(client: TestClient):
    res = client.get(
        "/api/me",
        headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.signature"},
    )
    assert res.status_code == 401


def test_production_config_fails_fast_on_weak_secret_key():
    with pytest.raises(ValidationError) as exc:
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="change-this-in-production",
            ADMIN_PASSWORD="super-strong-admin-pass-999!",
            ALLOWED_ORIGINS=["https://vox.example.com"],
        )
    assert "CRITICAL SECURITY CONFIGURATION ERROR: SECRET_KEY" in str(exc.value)


def test_production_config_fails_fast_on_default_admin_password():
    with pytest.raises(ValidationError) as exc:
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="a-very-strong-and-long-secret-key-for-prod-32-chars-min",
            ADMIN_PASSWORD="change-me",
            ALLOWED_ORIGINS=["https://vox.example.com"],
        )
    assert "CRITICAL SECURITY CONFIGURATION ERROR: ADMIN_PASSWORD" in str(exc.value)


def test_production_config_fails_fast_on_wildcard_cors():
    with pytest.raises(ValidationError) as exc:
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="a-very-strong-and-long-secret-key-for-prod-32-chars-min",
            ADMIN_PASSWORD="super-strong-admin-pass-999!",
            ALLOWED_ORIGINS=["*"],
        )
    assert "CRITICAL SECURITY CONFIGURATION ERROR: ALLOWED_ORIGINS" in str(exc.value)


def test_health_live_and_ready(client: TestClient):
    live_res = client.get("/health/live")
    assert live_res.status_code == 200
    assert live_res.json()["status"] == "alive"

    ready_res = client.get("/health/ready")
    assert ready_res.status_code == 200
    assert ready_res.json()["status"] == "ready"


def test_rate_limiter_blocks_excessive_requests(client: TestClient):
    from app.security.rate_limit import check_rate_limit, get_limiter
    limiter = get_limiter()
    # Test checking limit directly: 3 max allowed
    key = "test_custom_limiter_key"
    assert limiter.is_allowed(key, max_requests=3, window_seconds=60)[0] is True
    assert limiter.is_allowed(key, max_requests=3, window_seconds=60)[0] is True
    assert limiter.is_allowed(key, max_requests=3, window_seconds=60)[0] is True
    # 4th request must be rejected
    allowed, retry_after = limiter.is_allowed(key, max_requests=3, window_seconds=60)
    assert allowed is False
    assert retry_after > 0
