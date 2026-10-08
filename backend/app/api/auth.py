from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.config import get_settings
from app.models.user import User
from app.schemas.auth import TokenResponse, UserLoginIn, UserOut, UserRegisterIn
from app.schemas.voice import VoiceQuotaOut
from app.security.jwt import create_access_token
from app.security.password import hash_password, validate_password_strength, verify_password
from app.security.rate_limit import check_rate_limit
from app.services.quota import (
    PLANS,
    get_effective_plan,
    get_next_week_reset,
    get_usage_summary,
    utc_now,
)

router = APIRouter(prefix="/api", tags=["Authentication"])


def _build_user_out(user: User, db: Optional[Session] = None) -> UserOut:
    effective_plan = get_effective_plan(user)
    is_pro = effective_plan in ("weekly", "unlimited")

    if db is not None:
        summary = get_usage_summary(db, user)
        credits = summary["credits"]
        token_usage = summary["token_usage"]
        free_used = summary["free_generations_used"]
        free_limit = summary["free_generations_limit"]
    else:
        credits = None
        token_usage = 0
        free_used = 0
        free_limit = 1

    return UserOut(
        id=user.id,
        email=user.email,
        plan=effective_plan,
        is_admin=user.is_admin,
        is_pro=is_pro,
        subscription_active=is_pro,
        plan_active_from=user.plan_active_from,
        plan_active_until=user.plan_active_until,
        credits=credits,
        token_usage=token_usage,
        free_generations_used=free_used,
        free_generations_limit=free_limit,
        created_at=user.created_at,
    )


@router.post(
    "/auth/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
def register(
    data: UserRegisterIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    settings = get_settings()
    check_rate_limit(
        request=request,
        scope="register",
        max_requests=settings.RATE_LIMIT_REGISTER_MAX,
        window_seconds=settings.RATE_LIMIT_REGISTER_WINDOW_SECONDS,
    )

    valid, err_msg = validate_password_strength(data.password)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err_msg,
        )

    # Check if email is already in use
    existing_user = db.scalar(select(User).where(User.email == data.email))
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        )

    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        plan="free",
        is_admin=False,  # Explicitly prevent privilege escalation
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user_id=user.id)

    # Set secure HttpOnly cookie
    response.set_cookie(
        key="access_token",
        value=token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=bool(settings.COOKIE_SECURE),
        samesite=settings.COOKIE_SAMESITE,
    )

    user_out = _build_user_out(user, db)

    return TokenResponse(
        token=token,
        token_type="bearer",
        expires_in_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        user=user_out,
    )


@router.post(
    "/auth/login",
    response_model=TokenResponse,
    summary="Authenticate user and obtain access token",
)
def login(
    data: UserLoginIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    settings = get_settings()
    check_rate_limit(
        request=request,
        scope="login",
        max_requests=settings.RATE_LIMIT_LOGIN_MAX,
        window_seconds=settings.RATE_LIMIT_LOGIN_WINDOW_SECONDS,
        identifier=data.email,
    )

    user = db.scalar(select(User).where(User.email == data.email))
    now = utc_now()

    if user and user.locked_until and user.locked_until > now:
        remaining_secs = int((user.locked_until - now).total_seconds())
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account is temporarily locked due to repeated failed logins. Please try again in {remaining_secs // 60 + 1} minutes.",
        )

    if not user or not verify_password(data.password, user.password_hash):
        if user:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= settings.ADMIN_MAX_LOGIN_ATTEMPTS:
                user.locked_until = now + timedelta(minutes=settings.ADMIN_LOCKOUT_MINUTES)
            db.commit()

        import logging
        logging.getLogger("api.auth").warning(
            "Authentication failed for email: '%s' (user_found=%s, failed_attempts=%d)",
            data.email,
            user is not None,
            user.failed_login_attempts if user else 0,
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    # Reset failed attempts on successful login
    if user.failed_login_attempts > 0 or user.locked_until is not None:
        user.failed_login_attempts = 0
        user.locked_until = None
        db.commit()

    token = create_access_token(user_id=user.id)

    response.set_cookie(
        key="access_token",
        value=token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=bool(settings.COOKIE_SECURE),
        samesite=settings.COOKIE_SAMESITE,
    )

    user_out = _build_user_out(user, db)

    return TokenResponse(
        token=token,
        token_type="bearer",
        expires_in_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        user=user_out,
    )


@router.post(
    "/auth/logout",
    summary="Log out and clear session cookie",
)
def logout(response: Response):
    response.delete_cookie(key="access_token")
    return {"ok": True, "message": "Logged out successfully."}


@router.get(
    "/auth/me",
    response_model=UserOut,
    summary="Get current user profile, plan, credits, token usage, and pro subscription status",
)
def get_auth_me(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _build_user_out(user, db)


@router.get(
    "/me",
    response_model=VoiceQuotaOut,
    summary="Get current user profile, subscription status, credits, and generation usage",
)
def get_me(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    summary = get_usage_summary(db, user)
    plan_info = PLANS.get(summary["plan"], PLANS["free"])
    weekly_limit = plan_info["weekly_generations"]
    next_reset = get_next_week_reset()

    return VoiceQuotaOut(
        id=user.id,
        email=user.email,
        plan=summary["plan"],
        is_pro=summary["is_pro"],
        subscription_active=summary["is_pro"],
        used_generations=summary["used_generations"],
        weekly_generations=weekly_limit,
        weekly_generations_used=summary["used_generations"] if summary["generation_period"] == "weekly" else 0,
        weekly_generations_limit=weekly_limit,
        max_words=summary["max_words"],
        words_limit=summary["max_words"],
        credits=summary["credits"],
        token_usage=summary["token_usage"],
        generation_limit=summary["generation_limit"],
        generation_period=summary["generation_period"],
        free_generations_used=summary["free_generations_used"],
        free_generations_limit=summary["free_generations_limit"],
        active_from=user.plan_active_from,
        active_until=user.plan_active_until,
        resets_at=next_reset,
    )

