from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.purchase import PurchaseRequest
from app.models.user import User


def test_submit_valid_purchase(client: TestClient, regular_user: User, user_token: str):
    res = client.post(
        "/api/purchases",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"plan": "weekly", "payment_reference": "KBZ-PAY-TXN-123456"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["plan"] == "weekly"
    assert data["amount_mmk"] == 25000
    assert data["status"] == "pending"
    assert data["payment_reference"] == "KBZ-PAY-TXN-123456"


def test_submit_invalid_plan(client: TestClient, regular_user: User, user_token: str):
    res = client.post(
        "/api/purchases",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"plan": "free", "payment_reference": "KBZ-PAY-123456"},
    )
    assert res.status_code == 422


def test_submit_invalid_payment_ref(client: TestClient, regular_user: User, user_token: str):
    res = client.post(
        "/api/purchases",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"plan": "weekly", "payment_reference": "   "},
    )
    assert res.status_code == 422 or res.status_code == 400


def test_submit_duplicate_pending_payment_ref(client: TestClient, regular_user: User, user_token: str):
    client.post(
        "/api/purchases",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"plan": "weekly", "payment_reference": "UNIQUE-TXN-999"},
    )
    res = client.post(
        "/api/purchases",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"plan": "unlimited", "payment_reference": "UNIQUE-TXN-999"},
    )
    assert res.status_code == 409
    assert "already pending" in res.json()["detail"]


def test_admin_approve_purchase_success(
    client: TestClient,
    regular_user: User,
    user_token: str,
    admin_token: str,
    db_session: Session,
):
    # User submits purchase
    sub_res = client.post(
        "/api/purchases",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"plan": "weekly", "payment_reference": "APPROVED-TXN-777"},
    )
    req_id = sub_res.json()["id"]

    # Admin approves
    app_res = client.post(
        f"/api/admin/purchases/{req_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert app_res.status_code == 200
    assert app_res.json()["ok"] is True
    assert app_res.json()["plan"] == "weekly"

    # Verify user plan updated
    db_session.refresh(regular_user)
    assert regular_user.plan == "weekly"
    assert regular_user.plan_active_until is not None


def test_cannot_approve_already_approved_purchase(
    client: TestClient,
    regular_user: User,
    user_token: str,
    admin_token: str,
):
    sub_res = client.post(
        "/api/purchases",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"plan": "weekly", "payment_reference": "DOUBLE-APPROVE-111"},
    )
    req_id = sub_res.json()["id"]

    # First approval
    res1 = client.post(
        f"/api/admin/purchases/{req_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res1.status_code == 200

    # Second approval attempt must fail
    res2 = client.post(
        f"/api/admin/purchases/{req_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res2.status_code == 400
    assert "already 'approved'" in res2.json()["detail"]


def test_subscription_expiration_behavior(client: TestClient, regular_user: User, db_session: Session):
    from app.security.jwt import create_access_token
    token = create_access_token(user_id=regular_user.id)
    headers = {"Authorization": f"Bearer {token}"}

    # Set user plan to weekly, but active_until in past
    regular_user.plan = "weekly"
    regular_user.plan_active_until = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.commit()

    # /api/me should reflect dynamic fallback to Free plan
    me_res = client.get("/api/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["plan"] == "free"
    assert me_res.json()["max_words"] == 100
    assert me_res.json()["credits"] == 1
