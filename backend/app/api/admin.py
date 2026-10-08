import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_admin, get_db
from app.config import get_settings
from app.models.audit import AdminAuditLog
from app.models.purchase import PurchaseRequest
from app.models.user import User
from app.schemas.admin import AdminAuditLogOut
from app.schemas.purchase import (
    PurchaseApprovalResult,
    PurchaseApproveIn,
    PurchaseOut,
    PurchaseRejectIn,
)
from app.security.rate_limit import check_rate_limit
from app.services.audit import log_admin_action
from app.services.billing import approve_purchase_request, reject_purchase_request

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["Administrator"])


def get_client_ip(request: Request) -> str:
    return (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or (request.client.host if request.client else "127.0.0.1")
    )


@router.get(
    "/purchases",
    response_model=List[PurchaseOut],
    summary="List all user purchase requests with user email and duration metadata",
)
def list_purchases(
    request: Request,
    status_filter: Optional[str] = Query(None, alias="status"),
    admin: User = Depends(get_current_active_admin),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    check_rate_limit(
        request=request,
        scope="admin_api",
        max_requests=settings.RATE_LIMIT_ADMIN_MAX,
        window_seconds=settings.RATE_LIMIT_ADMIN_WINDOW_SECONDS,
        identifier=f"admin:{admin.id}",
    )

    query = select(PurchaseRequest).order_by(PurchaseRequest.created_at.desc())
    if status_filter:
        query = query.where(PurchaseRequest.status == status_filter)

    purchases = db.scalars(query).all()
    results: List[PurchaseOut] = []
    for p in purchases:
        item = PurchaseOut.model_validate(p)
        if p.user:
            item.user_email = p.user.email
        results.append(item)
    return results


@router.post(
    "/purchases/{request_id}/approve",
    response_model=PurchaseApprovalResult,
    summary="Approve a pending purchase request and activate subscriber plan for chosen duration",
)
def approve_purchase(
    request_id: int,
    request: Request,
    body: Optional[PurchaseApproveIn] = None,
    admin: User = Depends(get_current_active_admin),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    check_rate_limit(
        request=request,
        scope="admin_api",
        max_requests=settings.RATE_LIMIT_ADMIN_MAX,
        window_seconds=settings.RATE_LIMIT_ADMIN_WINDOW_SECONDS,
        identifier=f"admin:{admin.id}",
    )

    duration_months = body.duration_months if body else 1
    start_date = body.start_date if body else None

    client_ip = get_client_ip(request)
    approved = approve_purchase_request(
        db=db,
        request_id=request_id,
        admin_user_id=admin.id,
        duration_months=duration_months,
        start_date=start_date,
    )
    target_user = db.get(User, approved.user_id)

    log_admin_action(
        db=db,
        action="purchase_approved",
        admin_user_id=admin.id,
        target_type="purchase_request",
        target_id=approved.id,
        ip_address=client_ip,
        details={
            "user_id": approved.user_id,
            "plan": approved.plan,
            "amount_mmk": approved.amount_mmk,
            "duration_months": approved.duration_months,
            "payment_reference": approved.payment_reference,
            "plan_active_from": approved.plan_active_from.isoformat() if approved.plan_active_from else None,
            "plan_active_until": approved.plan_active_until.isoformat() if approved.plan_active_until else None,
        },
    )

    return PurchaseApprovalResult(
        ok=True,
        request_id=approved.id,
        user_id=approved.user_id,
        plan=approved.plan,
        duration_months=approved.duration_months,
        plan_active_from=approved.plan_active_from,
        plan_active_until=approved.plan_active_until,
        message=f"Purchase request #{approved.id} approved successfully for {approved.duration_months} month(s).",
    )


@router.post(
    "/purchases/{request_id}/reject",
    response_model=PurchaseApprovalResult,
    summary="Reject a pending purchase request",
)
def reject_purchase(
    request_id: int,
    request: Request,
    body: Optional[PurchaseRejectIn] = None,
    reason: Optional[str] = Query(None),
    admin: User = Depends(get_current_active_admin),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    check_rate_limit(
        request=request,
        scope="admin_api",
        max_requests=settings.RATE_LIMIT_ADMIN_MAX,
        window_seconds=settings.RATE_LIMIT_ADMIN_WINDOW_SECONDS,
        identifier=f"admin:{admin.id}",
    )

    effective_reason = (body.reason if body and body.reason else reason)
    client_ip = get_client_ip(request)
    rejected = reject_purchase_request(
        db=db,
        request_id=request_id,
        admin_user_id=admin.id,
        reason=effective_reason,
    )

    log_admin_action(
        db=db,
        action="purchase_rejected",
        admin_user_id=admin.id,
        target_type="purchase_request",
        target_id=rejected.id,
        ip_address=client_ip,
        details={
            "user_id": rejected.user_id,
            "plan": rejected.plan,
            "payment_reference": rejected.payment_reference,
            "reason": effective_reason,
        },
    )

    return PurchaseApprovalResult(
        ok=True,
        request_id=rejected.id,
        user_id=rejected.user_id,
        plan=rejected.plan,
        duration_months=None,
        plan_active_from=None,
        plan_active_until=None,
        message=f"Purchase request #{rejected.id} was rejected.",
    )


@router.get(
    "/audit-logs",
    response_model=List[AdminAuditLogOut],
    summary="List administrative audit log entries",
)
def list_audit_logs(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    admin: User = Depends(get_current_active_admin),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    check_rate_limit(
        request=request,
        scope="admin_api",
        max_requests=settings.RATE_LIMIT_ADMIN_MAX,
        window_seconds=settings.RATE_LIMIT_ADMIN_WINDOW_SECONDS,
        identifier=f"admin:{admin.id}",
    )

    logs = db.scalars(
        select(AdminAuditLog)
        .order_by(AdminAuditLog.created_at.desc())
        .limit(limit)
    ).all()

    return [AdminAuditLogOut.model_validate(log) for log in logs]
