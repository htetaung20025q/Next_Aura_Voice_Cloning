from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserRegisterIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    email: EmailStr = Field(..., max_length=255)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.lower().strip()


class UserLoginIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    email: EmailStr = Field(..., max_length=255)
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.lower().strip()


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    plan: str
    is_admin: bool
    is_pro: bool = False
    subscription_active: bool = False
    plan_active_from: Optional[datetime] = None
    plan_active_until: Optional[datetime] = None
    credits: Optional[int] = None
    token_usage: int = 0
    free_generations_used: int = 0
    free_generations_limit: int = 1
    created_at: datetime


class UserProfileOut(UserOut):
    pass


class TokenResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    user: UserOut
