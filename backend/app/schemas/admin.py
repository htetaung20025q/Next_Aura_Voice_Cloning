from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class AdminLoginIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class AdminAuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    admin_user_id: Optional[int]
    action: str
    target_type: Optional[str]
    target_id: Optional[int]
    ip_address: Optional[str]
    details: Optional[str]
    created_at: datetime
