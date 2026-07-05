from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


class RateLimiter:
    """Redis-based sliding window rate limiter.

    Falls back to in-memory rate limiting if Redis is unavailable.
    """

    def __init__(self, redis_url: str | None = None):
        self._redis = None
        self._redis_url = redis_url
        if redis_url:
            try:
                import redis
                self._redis = redis.from_url(redis_url)
                self._redis.ping()
                logger.info("Rate limiter: Redis connected at %s", redis_url)
            except Exception as e:
                logger.warning("Rate limiter: Redis connection failed (%s), falling back to in-memory", e)
                self._redis = None

        # In-memory fallback
        self._counters: dict[str, dict[str, float]] = {}
        self._window = 60
        self._last_cleanup = 0.0

    def is_allowed(self, key: str, limit: int, window: int = 60) -> tuple[bool, dict[str, int | float]]:
        """Check if a request is allowed under the rate limit.

        Returns (allowed, info) where info contains limit, remaining, reset.
        """
        if self._redis:
            return self._redis_is_allowed(key, limit, window)
        return self._memory_is_allowed(key, limit, window)

    def _redis_is_allowed(self, key: str, limit: int, window: int) -> tuple[bool, dict[str, int | float]]:
        """Redis sliding window implementation."""
        now = time.time()
        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(key, 0, now - window)
        pipe.zcard(key)
        pipe.zadd(key, {str(now): now})
        pipe.expire(key, window)
        results = pipe.execute()
        count = results[1]
        allowed = count < limit
        return allowed, {
            "limit": limit,
            "remaining": max(0, limit - count - 1),
            "reset": now + window,
        }

    def _memory_is_allowed(self, key: str, limit: int, window: int) -> tuple[bool, dict[str, int | float]]:
        """In-memory fallback implementation."""
        now = time.monotonic()
        self._cleanup(now, window)
        counter = self._counters.get(key)
        if counter is None or now - counter.get("window_start", 0) > window:
            self._counters[key] = {"count": 1, "window_start": now}
            return True, {"limit": limit, "remaining": limit - 1, "reset": now + window}
        counter["count"] += 1
        allowed = counter["count"] <= limit
        return allowed, {
            "limit": limit,
            "remaining": max(0, limit - counter["count"]),
            "reset": counter["window_start"] + window,
        }

    def _cleanup(self, now: float, window: int) -> None:
        """Clean up expired in-memory counters."""
        if now - self._last_cleanup < 300:
            return
        self._last_cleanup = now
        expired_keys = [
            k for k, v in self._counters.items()
            if now - v.get("window_start", 0) > window * 2
        ]
        for k in expired_keys:
            del self._counters[k]
