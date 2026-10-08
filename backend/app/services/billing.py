from datetime import datetime, timedelta, timezone
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.purchase import PurchaseRequest
from app.models.user import User
from app.services.quota import PLANS, utc_now


def create_purchase_request(
    db: Session,
    user_id: int,
    plan: str,
    payment_reference: str,
) -> PurchaseRequest:
    """
    Validates and creates a new purchase request.
    Enforces server-side pricing and prevents duplicate pending requests.
    """
    if plan not in ("weekly", "unlimited"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid plan selected. Only 'weekly' and 'unlimited' plans can be purchased.",
        )

    clean_ref = payment_reference.strip()
    if len(clean_ref) < 4:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment reference is too short. Please provide a valid transaction ID.",
        )

    # Check for existing pending request with same reference or user pending request
    existing_ref = db.scalar(
        select(PurchaseRequest).where(
            PurchaseRequest.payment_reference == clean_ref,
            PurchaseRequest.status == "pending",
        )
    )
    if existing_ref:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A purchase request with this payment reference is already pending approval.",
        )

    # Limit active pending requests per user to 3 to prevent spam
    user_pending_count = db.scalar(
        select(PurchaseRequest).where(
            PurchaseRequest.user_id == user_id,
            PurchaseRequest.status == "pending",
        )
    )
    if user_pending_count:
        # Check count
        count = len(db.scalars(
            select(PurchaseRequest).where(
                PurchaseRequest.user_id == user_id,
                PurchaseRequest.status == "pending",
            )
        ).all())
        if count >= 3:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="You already have pending purchase requests awaiting review. Please wait for admin approval.",
            )

    price_mmk = PLANS[plan]["price"]

    purchase = PurchaseRequest(
        user_id=user_id,
        plan=plan,
        amount_mmk=price_mmk,
        payment_reference=clean_ref,
        status="pending",
        created_at=utc_now(),
    )
    db.add(purchase)
    db.commit()
    db.refresh(purchase)
    return purchase


from app.services.subscription import (
    calculate_subscription_dates,
    utc_now,
)


def approve_purchase_request(
    db: Session,
    request_id: int,
    admin_user_id: int,
    duration_months: int = 1,
    start_date: Optional[datetime] = None,
) -> PurchaseRequest:
    """
    Atomically approves a purchase request and activates the user's subscription
    for the specified duration (default: 1 month).
    """
    if duration_months < 1 or duration_months > 120:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subscription duration must be between 1 and 120 months.",
        )

    query = select(PurchaseRequest).where(PurchaseRequest.id == request_id)
    try:
        query = query.with_for_update()
    except Exception:
        pass

    purchase = db.scalar(query)
    if not purchase:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Purchase request not found.",
        )

    if purchase.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot approve request. Current status is already '{purchase.status}'.",
        )

    user_query = select(User).where(User.id == purchase.user_id)
    try:
        user_query = user_query.with_for_update()
    except Exception:
        pass

    user = db.scalar(user_query)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User associated with this purchase request was not found.",
        )

    now = utc_now()
    active_from, active_until = calculate_subscription_dates(
        duration_months=duration_months,
        start_date=start_date or now,
        current_active_until=user.plan_active_until if user.plan == purchase.plan else None,
    )

    # 1. Update user active plan and boundaries
    user.plan = purchase.plan
    user.plan_active_from = active_from
    user.plan_active_until = active_until
    user.updated_at = now

    # 2. Update purchase request audit trail
    purchase.status = "approved"
    purchase.duration_months = duration_months
    purchase.plan_active_from = active_from
    purchase.plan_active_until = active_until
    purchase.approved_by_user_id = admin_user_id
    purchase.approved_at = now

    db.commit()
    db.refresh(purchase)
    db.refresh(user)
    return purchase


def reject_purchase_request(
    db: Session,
    request_id: int,
    admin_user_id: int,
    reason: Optional[str] = None,
) -> PurchaseRequest:
    """
    Rejects a pending purchase request without modifying the user's active plan.
    """
    query = select(PurchaseRequest).where(PurchaseRequest.id == request_id)
    try:
        query = query.with_for_update()
    except Exception:
        pass

    purchase = db.scalar(query)
    if not purchase:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Purchase request not found.",
        )

    if purchase.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot reject request. Current status is '{purchase.status}'.",
        )

    now = utc_now()
    purchase.status = "rejected"
    purchase.rejection_reason = reason.strip() if reason else None
    purchase.approved_by_user_id = admin_user_id
    purchase.approved_at = now

    db.commit()
    db.refresh(purchase)
    return purchase
