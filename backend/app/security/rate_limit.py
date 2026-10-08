import logging
import threading
import time
from collections import defaultdict, deque
from typing import Callable, Optional
from fastapi import HTTPException, Request, status

from app.config import get_settings

logger = logging.getLogger(__name__)


class InMemoryRateLimiter:
    """
    Thread-safe sliding window rate limiter for single-process / local development environments.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._history = defaultdict(deque)

    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> tuple[bool, int]:
        now = time.time()
        window_start = now - window_seconds
        with self._lock:
            q = self._history[key]
            # Evict timestamps older than window
            while q and q[0] <= window_start:
                q.popleft()

            if len(q) >= max_requests:
                # Calculate retry after
                retry_after = int(max(1, window_seconds - (now - q[0])))
                return False, retry_after

            q.append(now)
            return True, 0

    def reset(self, key: str):
        with self._lock:
            if key in self._history:
                del self._history[key]


class RedisRateLimiter:
    """
    Redis-backed sliding window rate limiter for distributed multi-worker production.
    """
    def __init__(self, redis_url: str):
        try:
            import redis
            self.client = redis.from_url(redis_url, decode_responses=True)
        except Exception as e:
            logger.warning(f"Could not connect to Redis for rate limiting ({e}). Falling back to in-memory.")
            self.client = None

    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> tuple[bool, int]:
        if not self.client:
            return True, 0
        try:
            now = time.time()
            window_start = now - window_seconds
            pipe = self.client.pipeline()
            # Remove old elements
            pipe.zremrangebyscore(key, 0, window_start)
            # Count elements in window
            pipe.zcard(key)
            # Add current element
            pipe.zadd(key, {str(now): now})
            # Set TTL on key
            pipe.expire(key, window_seconds + 5)
            results = pipe.execute()

            current_count = results[1]
            if current_count >= max_requests:
                return False, window_seconds
            return True, 0
        except Exception as e:
            logger.error(f"Redis rate limiter error: {e}")
            return True, 0  # Fail open safely


_memory_limiter = InMemoryRateLimiter()
_redis_limiter: Optional[RedisRateLimiter] = None


def get_limiter():
    global _redis_limiter
    settings = get_settings()
    if settings.REDIS_URL:
        if _redis_limiter is None:
            _redis_limiter = RedisRateLimiter(settings.REDIS_URL)
        if _redis_limiter.client is not None:
            return _redis_limiter
    return _memory_limiter


def check_rate_limit(
    request: Request,
    scope: str,
    max_requests: int,
    window_seconds: int,
    identifier: Optional[str] = None,
):
    """
    Evaluates rate limit for a given scope and client identifier.
    Raises HTTPException(429) if exceeded.
    """
    limiter = get_limiter()
    client_ip = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.client.host
        if request.client
        else "127.0.0.1"
    )
    key_id = identifier or client_ip
    key = f"rate_limit:{scope}:{key_id}"

    allowed, retry_after = limiter.is_allowed(key, max_requests, window_seconds)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please slow down and try again later.",
            headers={"Retry-After": str(retry_after)},
        )
