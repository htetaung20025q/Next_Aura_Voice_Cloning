from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class PurchaseIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    plan: Literal["weekly", "unlimited"]
    payment_reference: str = Field(..., min_length=4, max_length=100)

    @field_validator("payment_reference")
    @classmethod
    def validate_payment_reference(cls, v: str) -> str:
        clean = v.strip()
        if len(clean) < 4:
            raise ValueError("Payment reference must be at least 4 characters.")
        return clean


class PurchaseApproveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    duration_months: int = Field(1, ge=1, le=120, description="Subscription duration in months (1-120)")
    start_date: Optional[datetime] = Field(None, description="Optional custom start date in UTC")


class PurchaseRejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Optional[str] = Field(None, max_length=500, description="Reason for rejecting the request")


class PurchaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    user_email: Optional[str] = None
    plan: str
    amount_mmk: int
    payment_reference: str
    status: str
    duration_months: Optional[int] = None
    plan_active_from: Optional[datetime] = None
    plan_active_until: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    created_at: datetime
    approved_by_user_id: Optional[int] = None
    approved_at: Optional[datetime] = None


class PurchaseApprovalResult(BaseModel):
    ok: bool
    request_id: int
    user_id: int
    plan: str
    duration_months: Optional[int] = None
    plan_active_from: Optional[datetime] = None
    plan_active_until: Optional[datetime] = None
    message: str
