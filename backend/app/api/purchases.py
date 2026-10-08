from typing import Dict, List
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.config import get_settings
from app.models.purchase import PurchaseRequest
from app.models.user import User
from app.schemas.purchase import PurchaseIn, PurchaseOut
from app.schemas.voice import PlanDetail
from app.security.rate_limit import check_rate_limit
from app.services.billing import create_purchase_request
from app.services.quota import PLANS

router = APIRouter(prefix="/api", tags=["Purchases & Plans"])


@router.get(
    "/plans",
    response_model=Dict[str, PlanDetail],
    summary="Get available voice studio subscription plans and pricing",
)
def get_plans():
    return {k: PlanDetail(**v) for k, v in PLANS.items()}


@router.post(
    "/purchases",
    response_model=PurchaseOut,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a premium plan purchase request with payment reference",
)
def submit_purchase(
    data: PurchaseIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    check_rate_limit(
        request=request,
        scope="purchase_submit",
        max_requests=settings.RATE_LIMIT_PURCHASE_MAX,
        window_seconds=settings.RATE_LIMIT_PURCHASE_WINDOW_SECONDS,
        identifier=f"user:{user.id}",
    )

    purchase = create_purchase_request(
        db=db,
        user_id=user.id,
        plan=data.plan,
        payment_reference=data.payment_reference,
    )

    return PurchaseOut.model_validate(purchase)


@router.get(
    "/purchases/my",
    response_model=List[PurchaseOut],
    summary="Get current user's purchase requests",
)
def get_my_purchases(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    purchases = db.scalars(
        select(PurchaseRequest)
        .where(PurchaseRequest.user_id == user.id)
        .order_by(PurchaseRequest.created_at.desc())
    ).all()
    return [PurchaseOut.model_validate(p) for p in purchases]
