from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.purchase import PurchaseRequest
from app.models.user import User
from app.services.subscription import (
    add_months_utc,
    calculate_subscription_dates,
    cleanup_expired_subscriptions,
    get_effective_plan,
    get_subscription_status,
    make_aware,
)


def test_add_months_utc_accuracy():
    # Jan 31 + 1 month in non-leap year (2025) -> Feb 28
    d1 = datetime(2025, 1, 31, 12, 0, 0, tzinfo=timezone.utc)
    res1 = add_months_utc(d1, 1)
    assert res1.year == 2025
    assert res1.month == 2
    assert res1.day == 28

    # Jan 31 + 1 month in leap year (2024) -> Feb 29
    d2 = datetime(2024, 1, 31, 12, 0, 0, tzinfo=timezone.utc)
    res2 = add_months_utc(d2, 1)
    assert res2.year == 2024
    assert res2.month == 2
    assert res2.day == 29

    # Dec 15 + 2 months -> Feb 15 next year
    d3 = datetime(2025, 12, 15, 12, 0, 0, tzinfo=timezone.utc)
    res3 = add_months_utc(d3, 2)
    assert res3.year == 2026
    assert res3.month == 2
    assert res3.day == 15


def test_pending_to_approve_to_active(
    client: TestClient,
    regular_user: User,
    user_token: str,
    admin_token: str,
    db_session: Session,
):
    # 1. User submits a purchase request for Unlimited plan
    sub_res = client.post(
        "/api/purchases",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"plan": "unlimited", "payment_reference": "TXN-DURATION-3M"},
    )
    assert sub_res.status_code == 201
    req_id = sub_res.json()["id"]

    # 2. Admin approves for 3 months
    app_res = client.post(
        f"/api/admin/purchases/{req_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"duration_months": 3},
    )
    assert app_res.status_code == 200
    data = app_res.json()
    assert data["ok"] is True
    assert data["plan"] == "unlimited"
    assert data["duration_months"] == 3
    assert data["plan_active_from"] is not None
    assert data["plan_active_until"] is not None

    # 3. Verify user in database
    db_session.refresh(regular_user)
    assert regular_user.plan == "unlimited"
    assert regular_user.plan_active_from is not None
    assert make_aware(regular_user.plan_active_until) > datetime.now(timezone.utc)

    # 4. Check /api/me and /api/voice/quota reflect Unlimited plan
    me_res = client.get("/api/me", headers={"Authorization": f"Bearer {user_token}"})
    assert me_res.status_code == 200
    assert me_res.json()["plan"] == "unlimited"
    assert me_res.json()["weekly_generations"] is None  # Unlimited
    assert me_res.json()["active_until"] is not None


def test_pending_to_reject_unchanged_plan(
    client: TestClient,
    regular_user: User,
    user_token: str,
    admin_token: str,
    db_session: Session,
):
    # Ensure starting on free plan
    regular_user.plan = "free"
    regular_user.plan_active_until = None
    db_session.commit()

    # User submits purchase
    sub_res = client.post(
        "/api/purchases",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"plan": "weekly", "payment_reference": "TXN-REJECT-ME"},
    )
    assert sub_res.status_code == 201
    req_id = sub_res.json()["id"]

    # Admin rejects with reason
    rej_res = client.post(
        f"/api/admin/purchases/{req_id}/reject",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"reason": "Invalid payment slip transaction ID"},
    )
    assert rej_res.status_code == 200
    assert rej_res.json()["ok"] is True

    # Verify user's plan is STILL free
    db_session.refresh(regular_user)
    assert regular_user.plan == "free"
    assert regular_user.plan_active_until is None

    # Verify purchase record status is rejected with reason
    pur = db_session.get(PurchaseRequest, req_id)
    assert pur.status == "rejected"
    assert pur.rejection_reason == "Invalid payment slip transaction ID"


def test_expired_subscription_automatically_treated_as_free(
    client: TestClient,
    regular_user: User,
    user_token: str,
    db_session: Session,
):
    # Manually set user to expired weekly plan
    now = datetime.now(timezone.utc)
    regular_user.plan = "weekly"
    regular_user.plan_active_from = now - timedelta(days=40)
    regular_user.plan_active_until = now - timedelta(days=10)
    db_session.commit()

    # 1. Test get_effective_plan() service
    assert get_effective_plan(regular_user) == "free"

    # 2. Test get_subscription_status() service
    status = get_subscription_status(regular_user)
    assert status["is_active"] is False
    assert status["is_expired"] is True
    assert status["effective_plan"] == "free"

    # 3. Test /api/me API
    me_res = client.get("/api/me", headers={"Authorization": f"Bearer {user_token}"})
    assert me_res.status_code == 200
    assert me_res.json()["plan"] == "free"
    assert me_res.json()["max_words"] == 100
    assert me_res.json()["credits"] == 1

    # 4. Test /api/voice/quota API
    quota_res = client.get("/api/voice/quota", headers={"Authorization": f"Bearer {user_token}"})
    assert quota_res.status_code == 200
    assert quota_res.json()["plan"] == "free"
    assert quota_res.json()["words_limit"] == 100


def test_duplicate_approval_blocked(
    client: TestClient,
    regular_user: User,
    user_token: str,
    admin_token: str,
):
    sub_res = client.post(
        "/api/purchases",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"plan": "weekly", "payment_reference": "TXN-NO-DUP"},
    )
    req_id = sub_res.json()["id"]

    # First approval -> 200 OK
    res1 = client.post(
        f"/api/admin/purchases/{req_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"duration_months": 1},
    )
    assert res1.status_code == 200

    # Second approval -> 400 Bad Request
    res2 = client.post(
        f"/api/admin/purchases/{req_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"duration_months": 2},
    )
    assert res2.status_code == 400
    assert "already 'approved'" in res2.json()["detail"]


def test_non_admin_approval_blocked(
    client: TestClient,
    regular_user: User,
    user_token: str,
):
    sub_res = client.post(
        "/api/purchases",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"plan": "weekly", "payment_reference": "TXN-FORBIDDEN"},
    )
    req_id = sub_res.json()["id"]

    # Regular user attempting admin approval -> 403 Forbidden
    res = client.post(
        f"/api/admin/purchases/{req_id}/approve",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"duration_months": 1},
    )
    assert res.status_code == 403
    assert "Administrator privileges required" in res.json()["detail"]


def test_invalid_duration_rejected(
    client: TestClient,
    regular_user: User,
    user_token: str,
    admin_token: str,
):
    sub_res = client.post(
        "/api/purchases",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"plan": "weekly", "payment_reference": "TXN-BAD-DUR"},
    )
    req_id = sub_res.json()["id"]

    # Duration = 0
    res_zero = client.post(
        f"/api/admin/purchases/{req_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"duration_months": 0},
    )
    assert res_zero.status_code == 422 or res_zero.status_code == 400

    # Duration = -5
    res_neg = client.post(
        f"/api/admin/purchases/{req_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"duration_months": -5},
    )
    assert res_neg.status_code == 422 or res_neg.status_code == 400

    # Duration = 999
    res_huge = client.post(
        f"/api/admin/purchases/{req_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"duration_months": 999},
    )
    assert res_huge.status_code == 422 or res_huge.status_code == 400


def test_cleanup_expired_subscriptions_job(db_session: Session):
    now = datetime.now(timezone.utc)
    user_exp = User(
        email="expired_user_test@example.com",
        password_hash="fakehash",
        plan="weekly",
        plan_active_from=now - timedelta(days=60),
        plan_active_until=now - timedelta(days=1),
        created_at=now - timedelta(days=60),
        updated_at=now - timedelta(days=60),
    )
    user_act = User(
        email="active_user_test@example.com",
        password_hash="fakehash",
        plan="weekly",
        plan_active_from=now,
        plan_active_until=now + timedelta(days=30),
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([user_exp, user_act])
    db_session.commit()

    cleaned = cleanup_expired_subscriptions(db_session)
    assert cleaned >= 1

    db_session.refresh(user_exp)
    db_session.refresh(user_act)
    assert user_exp.plan == "free"
    assert user_act.plan == "weekly"
