from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.generation import Generation
from app.models.user import User

# Free plan: a single lifetime generation per registered user.
FREE_LIFETIME_GENERATIONS = 1
# "free_legacy" marks historical free rows created under the old weekly free policy
# (see migration 003). They still count as used free generations.
FREE_PLAN_KEYS = ("free", "free_legacy")
ACTIVE_GENERATION_STATUSES = ("completed", "reserved")
# A reservation older than this is treated as an abandoned request (e.g. server crash)
# and released, so it cannot permanently lock a user's free generation.
STALE_RESERVATION_MINUTES = 30

GUEST_GENERATION_MESSAGE = "Please sign in or create an account to generate voice."
FREE_LIMIT_MESSAGE = (
    "Your free generation has been used. Upgrade to a premium plan to continue generating."
)

PLANS: Dict[str, Dict] = {
    "free": {
        "name": "Free",
        "price": 0,
        "currency": "MMK",
        "max_words": 100,
        "weekly_generations": None,  # Free plan is limited by lifetime_generations instead
        "lifetime_generations": FREE_LIFETIME_GENERATIONS,
        "requires_login": True,
    },
    "weekly": {
        "name": "Weekly",
        "price": 25000,
        "currency": "MMK",
        "max_words": 5000,
        "weekly_generations": 6,
        "requires_login": True,
    },
    "unlimited": {
        "name": "Unlimited",
        "price": 50000,
        "currency": "MMK",
        "max_words": 5000,
        "weekly_generations": None,  # None = unlimited generations
        "requires_login": True,
    },
}


from app.services.subscription import (
    get_effective_plan,
    make_aware,
    utc_now,
)


def get_week_start(dt: Optional[datetime] = None) -> datetime:
    """
    Returns the UTC start of the current week (Monday 00:00:00.000000 UTC).
    """
    now = dt or utc_now()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start_of_day - timedelta(days=now.weekday())


def get_next_week_reset(dt: Optional[datetime] = None) -> datetime:
    """
    Returns the UTC timestamp of the upcoming reset (next Monday 00:00:00 UTC).
    """
    start = get_week_start(dt)
    return start + timedelta(days=7)


def count_weekly_generations(
    db: Session,
    user_id: Optional[int] = None,
    anonymous_id: Optional[str] = None,
    ip_abuse_hash: Optional[str] = None,
) -> int:
    """
    Accurately counts completed and currently active generation slots used in the current week.
    Crucial fix: Counts row count (generations used), NOT the sum of word counts!
    """
    week_start = get_week_start()
    query = select(func.count(Generation.id)).where(
        Generation.created_at >= week_start,
        Generation.status.in_(["completed", "reserved"]),
    )

    if user_id is not None:
        query = query.where(Generation.user_id == user_id)
        count = db.scalar(query) or 0
        return int(count)

    # For anonymous users: check both anonymous session identifier and IP abuse hash
    anon_match_conditions = []
    if anonymous_id:
        anon_match_conditions.append(Generation.anonymous_identifier == anonymous_id)
    if ip_abuse_hash:
        anon_match_conditions.append(Generation.anonymous_identifier == f"ip:{ip_abuse_hash}")

    from sqlalchemy import or_
    query = query.where(Generation.user_id.is_(None), or_(*anon_match_conditions))
    count = db.scalar(query) or 0
    return int(count)


def count_weekly_token_usage(
    db: Session,
    user_id: Optional[int] = None,
    anonymous_id: Optional[str] = None,
    ip_abuse_hash: Optional[str] = None,
) -> int:
    """
    Counts total words/tokens generated in the current weekly window from database truth.
    """
    week_start = get_week_start()
    query = select(func.coalesce(func.sum(Generation.word_count), 0)).where(
        Generation.created_at >= week_start,
        Generation.status.in_(["completed", "reserved"]),
    )

    if user_id is not None:
        query = query.where(Generation.user_id == user_id)
        tokens = db.scalar(query) or 0
        return int(tokens)

    anon_match_conditions = []
    if anonymous_id:
        anon_match_conditions.append(Generation.anonymous_identifier == anonymous_id)
    if ip_abuse_hash:
        anon_match_conditions.append(Generation.anonymous_identifier == f"ip:{ip_abuse_hash}")

    if not anon_match_conditions:
        return 0

    from sqlalchemy import or_
    query = query.where(Generation.user_id.is_(None), or_(*anon_match_conditions))
    tokens = db.scalar(query) or 0
    return int(tokens)


def count_free_generations_used(db: Session, user_id: int) -> int:
    """
    Counts the user's lifetime free generations (completed or in-flight).
    Failed generations are excluded, so they never consume the free quota.
    """
    query = select(func.count(Generation.id)).where(
        Generation.user_id == user_id,
        Generation.plan.in_(FREE_PLAN_KEYS),
        Generation.status.in_(ACTIVE_GENERATION_STATUSES),
    )
    return int(db.scalar(query) or 0)


def release_stale_reservations(db: Session, user_id: int) -> None:
    """Marks abandoned 'reserved' rows for this user as failed."""
    cutoff = utc_now() - timedelta(minutes=STALE_RESERVATION_MINUTES)
    result = db.execute(
        update(Generation)
        .where(
            Generation.user_id == user_id,
            Generation.status == "reserved",
            Generation.created_at < cutoff,
        )
        .values(status="failed")
    )
    if result.rowcount:
        db.commit()


def get_usage_summary(db: Session, user: Optional[User]) -> Dict[str, Any]:
    """
    Single source of truth for plan usage shown by /api/me, /api/auth/me and /api/voice/quota.
    Everything is derived from database records and server UTC time.
    """
    plan_name = get_effective_plan(user)
    plan_info = PLANS.get(plan_name, PLANS["free"])

    free_used = count_free_generations_used(db, user.id) if user else 0
    token_usage = count_weekly_token_usage(db=db, user_id=user.id) if user else 0

    if plan_name == "free":
        used = free_used
        limit: Optional[int] = FREE_LIFETIME_GENERATIONS
        period = "lifetime"
    else:
        used = count_weekly_generations(db=db, user_id=user.id) if user else 0
        limit = plan_info["weekly_generations"]
        period = "weekly" if limit is not None else "unlimited"

    credits = None if limit is None else max(0, limit - used)

    return {
        "plan": plan_name,
        "is_pro": plan_name in ("weekly", "unlimited"),
        "used_generations": min(used, limit) if limit is not None else used,
        "generation_limit": limit,
        "generation_period": period,
        "credits": credits,
        "token_usage": token_usage,
        "max_words": plan_info["max_words"],
        "free_generations_used": min(free_used, FREE_LIFETIME_GENERATIONS),
        "free_generations_limit": FREE_LIFETIME_GENERATIONS,
    }


def reserve_generation_quota(
    db: Session,
    user: Optional[User],
    anonymous_id: Optional[str],
    ip_abuse_hash: Optional[str],
    word_count: int,
) -> Tuple[Generation, str]:
    """
    Transaction-safe generation quota reservation.
    Atomically checks limits and creates a 'reserved' Generation record.

    Free plan race safety: the count check below is a fast path; the real guarantee is the
    partial unique index `uq_generations_free_once_per_user`, which allows at most one
    reserved/completed free row per user. A concurrent duplicate insert fails with
    IntegrityError and is reported as "free generation used".
    """
    # Guests cannot generate; they must register to use the free generation.
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=GUEST_GENERATION_MESSAGE,
        )

    plan_name = get_effective_plan(user)
    plan_config = PLANS.get(plan_name, PLANS["free"])

    release_stale_reservations(db, user.id)

    # 1. Free plan: one lifetime generation
    if plan_name == "free":
        if count_free_generations_used(db, user.id) >= FREE_LIFETIME_GENERATIONS:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=FREE_LIMIT_MESSAGE,
            )

    # 2. Enforce per-generation word count limit
    max_words = plan_config["max_words"]
    if word_count > max_words:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Your {plan_config['name']} plan allows up to {max_words:,} words per generation. Your script contains {word_count:,} words.",
        )

    # 3. Enforce weekly generation count limit (premium plans)
    limit = plan_config["weekly_generations"]
    if limit is not None:
        used_generations = count_weekly_generations(db=db, user_id=user.id)
        if used_generations >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Your {plan_config['name']} plan has reached its weekly limit of {limit} generations. Limits reset on Monday at 00:00 UTC.",
            )

    # 4. Create atomic reservation
    generation = Generation(
        user_id=user.id,
        anonymous_identifier=None,
        plan=plan_name,
        word_count=word_count,
        status="reserved",
        created_at=utc_now(),
    )
    db.add(generation)
    try:
        db.commit()
    except IntegrityError:
        # Another concurrent request already reserved this user's free generation.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=FREE_LIMIT_MESSAGE,
        )
    db.refresh(generation)

    return generation, plan_name


def complete_generation(db: Session, generation_id: int):
    """
    Marks a reserved generation as completed.
    """
    gen = db.get(Generation, generation_id)
    if gen:
        gen.status = "completed"
        db.commit()


def release_generation(db: Session, generation_id: int):
    """
    Marks a failed generation so the user is not charged for failed system attempts.
    """
    gen = db.get(Generation, generation_id)
    if gen:
        gen.status = "failed"
        db.commit()
