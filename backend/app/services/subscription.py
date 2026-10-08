import calendar
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.user import User

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    """Returns current UTC timestamp with timezone information."""
    return datetime.now(timezone.utc)


def make_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensures datetime object is timezone-aware in UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def add_months_utc(start_dt: datetime, months: int) -> datetime:
    """
    Accurately adds integer months to a UTC datetime, handling month-end boundaries
    (e.g., Jan 31 + 1 month -> Feb 28 in non-leap year, Feb 29 in leap year).
    """
    if months <= 0:
        raise ValueError("Duration in months must be a positive integer.")

    start_aware = make_aware(start_dt)
    new_year = start_aware.year + (start_aware.month + months - 1) // 12
    new_month = (start_aware.month + months - 1) % 12 + 1
    max_days = calendar.monthrange(new_year, new_month)[1]
    new_day = min(start_aware.day, max_days)
    return start_aware.replace(year=new_year, month=new_month, day=new_day)


def calculate_subscription_dates(
    duration_months: int,
    start_date: Optional[datetime] = None,
    current_active_until: Optional[datetime] = None,
) -> Tuple[datetime, datetime]:
    """
    Calculates the exact (plan_active_from, plan_active_until) for a subscription.
    If the user already has an active future expiration, extends from that future expiration date.
    Otherwise, starts from `start_date` (or `utc_now()`).
    """
    now = utc_now()
    current_until_aware = make_aware(current_active_until)

    if current_until_aware and current_until_aware > now:
        # Extend from current active expiration
        active_from = now
        active_until = add_months_utc(current_until_aware, duration_months)
    else:
        active_from = make_aware(start_date) if start_date else now
        active_until = add_months_utc(active_from, duration_months)

    return active_from, active_until


def get_effective_plan(user: Optional[User]) -> str:
    """
    Determines the active effective plan for a user dynamically using server-side UTC time.
    If a premium subscription (weekly or unlimited) has expired or is missing active_until,
    it automatically and immediately falls back to 'free'.
    Administrators always possess active plan access.
    """
    if user is None:
        return "free"

    # Administrators always maintain active access
    if getattr(user, "is_admin", False):
        return user.plan if user.plan in ("weekly", "unlimited") else "unlimited"

    if user.plan in ("weekly", "unlimited"):
        active_until = make_aware(user.plan_active_until)
        now = utc_now()
        if active_until is None or active_until <= now:
            return "free"
        return user.plan

    return "free"


def get_subscription_status(user: Optional[User]) -> Dict[str, Any]:
    """
    Returns full structured subscription status for user profile / quotas.
    """
    if user is None:
        return {
            "plan": "free",
            "effective_plan": "free",
            "is_active": False,
            "is_expired": False,
            "plan_active_from": None,
            "plan_active_until": None,
            "remaining_seconds": 0,
            "remaining_days": 0,
        }

    now = utc_now()
    active_from = make_aware(user.plan_active_from)
    active_until = make_aware(user.plan_active_until)
    effective_plan = get_effective_plan(user)
    is_premium = user.plan in ("weekly", "unlimited")
    is_active = effective_plan != "free"
    is_expired = is_premium and (active_until is None or active_until <= now)

    remaining_seconds = 0
    remaining_days = 0
    if active_until and active_until > now:
        remaining_seconds = int((active_until - now).total_seconds())
        remaining_days = max(0, int(remaining_seconds // 86400))

    return {
        "plan": user.plan,
        "effective_plan": effective_plan,
        "is_active": is_active,
        "is_expired": is_expired,
        "plan_active_from": active_from,
        "plan_active_until": active_until,
        "remaining_seconds": remaining_seconds,
        "remaining_days": remaining_days,
    }


def cleanup_expired_subscriptions(db: Session) -> int:
    """
    Maintenance cleanup job to explicitly update expired user plan columns to 'free'.
    Note: Real-time authorization & quota checking uses `get_effective_plan()`,
    so correctness is always guaranteed regardless of when cleanup runs.
    """
    now = utc_now()
    stmt = (
        update(User)
        .where(
            User.plan.in_(["weekly", "unlimited"]),
            User.plan_active_until.is_not(None),
            User.plan_active_until <= now,
        )
        .values(plan="free", updated_at=now)
    )
    result = db.execute(stmt)
    db.commit()
    count = result.rowcount
    if count > 0:
        logger.info("Cleaned up %d expired user subscriptions to free plan.", count)
    return count
