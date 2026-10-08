from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User
from app.security.jwt import create_access_token


def test_register_success(client: TestClient, db_session: Session):
    response = client.post(
        "/api/auth/register",
        json={"email": "newuser@example.com", "password": "SecurePassword123!"},
    )
    assert response.status_code == 201
    data = response.json()
    assert "token" in data
    assert data["user"]["email"] == "newuser@example.com"
    assert data["user"]["plan"] == "free"
    assert data["user"]["is_admin"] is False

    # Verify user in database
    user = db_session.scalar(select(User).where(User.email == "newuser@example.com"))
    assert user is not None
    assert user.is_admin is False


def test_register_duplicate_email(client: TestClient, regular_user: User):
    response = client.post(
        "/api/auth/register",
        json={"email": regular_user.email, "password": "AnotherPassword123!"},
    )
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


def test_register_weak_password(client: TestClient):
    response = client.post(
        "/api/auth/register",
        json={"email": "weak@example.com", "password": "123"},
    )
    assert response.status_code == 422 or response.status_code == 400


def test_register_prevents_privilege_escalation(client: TestClient, db_session: Session):
    # Attempt to send is_admin=True in payload
    response = client.post(
        "/api/auth/register",
        json={"email": "hacker@example.com", "password": "Password123!", "is_admin": True, "plan": "unlimited"},
    )
    # Extra fields forbidden by Pydantic schema
    assert response.status_code == 422


def test_login_success(client: TestClient, regular_user: User):
    response = client.post(
        "/api/auth/login",
        json={"email": regular_user.email, "password": "Password123!"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert data["user"]["email"] == regular_user.email


def test_login_invalid_password(client: TestClient, regular_user: User):
    response = client.post(
        "/api/auth/login",
        json={"email": regular_user.email, "password": "WrongPassword!"},
    )
    assert response.status_code == 401
    assert "Invalid email or password." in response.json()["detail"]


def test_login_invalid_email(client: TestClient):
    response = client.post(
        "/api/auth/login",
        json={"email": "nonexistent@example.com", "password": "Password123!"},
    )
    assert response.status_code == 401
    assert "Invalid email or password." in response.json()["detail"]


def test_me_endpoint_authenticated(client: TestClient, regular_user: User, user_token: str):
    response = client.get(
        "/api/me",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == regular_user.email
    assert data["plan"] == "free"
    assert data["used_generations"] == 0
    assert data["max_words"] == 100
    assert data["credits"] == 1
    assert data["token_usage"] == 0
    assert data["free_generations_used"] == 0
    assert data["free_generations_limit"] == 1


def test_me_endpoint_unauthorized(client: TestClient):
    response = client.get("/api/me")
    assert response.status_code == 401


def test_me_endpoint_expired_token(client: TestClient, regular_user: User):
    # Generate token expired 1 hour ago
    expired_token = create_access_token(
        user_id=regular_user.id,
        expires_delta=timedelta(hours=-1),
    )
    response = client.get(
        "/api/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401


def test_auth_me_endpoint_success(client: TestClient, regular_user: User, user_token: str):
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == regular_user.id
    assert data["email"] == regular_user.email
    assert data["plan"] == "free"
    assert data["is_admin"] is False
    assert data["is_pro"] is False
    assert data["subscription_active"] is False
    assert data["credits"] == 1
    assert data["token_usage"] == 0
    assert data["free_generations_used"] == 0
    assert data["free_generations_limit"] == 1


def test_auth_me_credits_and_token_usage_calculation(client: TestClient, db_session: Session, regular_user: User, user_token: str):
    from app.models.generation import Generation
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    gen = Generation(
        user_id=regular_user.id,
        plan="free",
        word_count=80,
        status="completed",
        created_at=now,
    )
    db_session.add(gen)
    db_session.commit()

    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["credits"] == 0  # 1 - 1 = 0 remaining
    assert data["free_generations_used"] == 1
    assert data["token_usage"] == 80


def test_auth_me_endpoint_unauthorized(client: TestClient):
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_auth_me_pro_active(client: TestClient, weekly_user: User):
    token = create_access_token(user_id=weekly_user.id)
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == weekly_user.email
    assert data["plan"] == "weekly"
    assert data["is_pro"] is True
    assert data["subscription_active"] is True
    assert data["plan_active_until"] is not None


def test_auth_me_expired_subscription_returns_free(client: TestClient, db_session: Session):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    expired_user = User(
        email="expired_pro@example.com",
        password_hash="hashed_pw",
        plan="weekly",
        plan_active_from=now - timedelta(days=40),
        plan_active_until=now - timedelta(days=10),
        is_admin=False,
    )
    db_session.add(expired_user)
    db_session.commit()
    db_session.refresh(expired_user)

    token = create_access_token(user_id=expired_user.id)
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    # Dynamic calculation evaluates as free / non-pro
    assert data["plan"] == "free"
    assert data["is_pro"] is False
    assert data["subscription_active"] is False


def test_admin_endpoint_forbidden_for_regular_user(client: TestClient, user_token: str):
    response = client.get(
        "/api/admin/purchases",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert response.status_code == 403
    assert "Administrator privileges required" in response.json()["detail"]


def test_admin_endpoint_allowed_for_admin(client: TestClient, admin_token: str):
    response = client.get(
        "/api/admin/purchases",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_logout(client: TestClient):
    response = client.post("/api/auth/logout")
    assert response.status_code == 200
    assert response.json()["ok"] is True

