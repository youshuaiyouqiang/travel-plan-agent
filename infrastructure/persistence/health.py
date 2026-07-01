from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class HealthStatus:
    status: str
    redis: str = "unknown"
    details: dict | None = None


def check_health() -> HealthStatus:
    checks = {
        "redis": _check_redis,
    }
    results = {}
    overall = "healthy"
    for name, check_fn in checks.items():
        try:
            check_fn()
            results[name] = "ok"
        except Exception as exc:
            results[name] = f"error: {exc}"
            overall = "degraded"
            logger.warning("Health check failed: %s - %s", name, exc)

    return HealthStatus(status=overall, **results, details=results)


def _check_redis() -> None:
    import redis
    from config import settings

    client = redis.Redis.from_url(settings.redis_url)
    client.ping()
