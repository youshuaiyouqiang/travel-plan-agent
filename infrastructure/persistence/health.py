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
    from config import settings

    results: dict[str, str] = {}
    overall = "healthy"

    # P2-14：检查 SQLite（主存储，必检）
    try:
        from infrastructure.persistence.database import get_connection

        conn = get_connection()
        conn.execute("SELECT 1").fetchone()
        results["sqlite"] = "ok"
    except Exception as exc:
        results["sqlite"] = f"error: {exc}"
        overall = "degraded"
        logger.warning("Health check failed: sqlite - %s", exc)

    # P2-14：仅当 session_backend == "redis" 时检查 Redis（与实际存储脱节修复）
    if settings.session_backend == "redis":
        try:
            _check_redis()
            results["redis"] = "ok"
        except Exception as exc:
            results["redis"] = f"error: {exc}"
            overall = "degraded"
            logger.warning("Health check failed: redis - %s", exc)
    else:
        results["redis"] = "skipped"

    return HealthStatus(status=overall, **results, details=results)


def _check_redis() -> None:
    import redis
    from config import settings

    client = redis.Redis.from_url(settings.redis_url)
    client.ping()
