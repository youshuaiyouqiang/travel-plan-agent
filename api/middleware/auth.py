from __future__ import annotations

import logging
import time

from fastapi import Request
from fastapi.responses import JSONResponse

from config import settings
from domain.user.auth.token import verify_token
from infrastructure.cache.rate_limit import RateLimiter

logger = logging.getLogger(__name__)

_PUBLIC_PATHS = {"/api/auth/register", "/api/auth/login", "/api/trending", "/health", "/metrics", "/api/shared"}
_PUBLIC_PREFIXES = ("/api/album/",)

_rate_counters: dict[str, dict[str, float]] = {}
_RATE_WINDOW = 60
_RATE_MAX_REQUESTS = settings.rate_limit_rpm
_RATE_CLEANUP_INTERVAL = 300
_last_rate_cleanup = 0.0

# Initialize Redis-based rate limiter if redis URL is configured
_rate_limiter: RateLimiter | None = None
if settings.redis_url:
    _rate_limiter = RateLimiter(redis_url=settings.redis_url)


def _make_rate_key(user_id: str, ip: str, path: str) -> str:
    prefix = path.split("/api/")[-1].split("/")[0] if "/api/" in path else path.strip("/")
    return f"{user_id}:{ip}:{prefix}"


def _cleanup_rate_counters(now: float) -> None:
    global _last_rate_cleanup
    if now - _last_rate_cleanup < _RATE_CLEANUP_INTERVAL:
        return
    _last_rate_cleanup = now
    expired_keys = [
        k for k, v in _rate_counters.items()
        if now - v.get("window_start", 0) > _RATE_WINDOW * 2
    ]
    for k in expired_keys:
        del _rate_counters[k]


def _check_rate(user_id: str, ip: str, path: str) -> bool:
    now = time.monotonic()
    _cleanup_rate_counters(now)
    key = _make_rate_key(user_id, ip, path)
    counter = _rate_counters.get(key)
    if counter is None or now - counter.get("window_start", 0) > _RATE_WINDOW:
        _rate_counters[key] = {"count": 1, "window_start": now}
        return True
    counter["count"] += 1
    return counter["count"] <= _RATE_MAX_REQUESTS


async def auth_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)
    path = request.url.path
    if path.startswith("/debug") or path in _PUBLIC_PATHS or path.startswith("/api/auth") or path.startswith("/api/shared"):
        return await call_next(request)
    if any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES):
        return await call_next(request)
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip() if auth_header.startswith("Bearer ") else ""
    if token:
        user_id = verify_token(token)
        if user_id:
            request.state.user_id = user_id
            client_ip = request.client.host if request.client else "unknown"
            rate_key = _make_rate_key(user_id, client_ip, path)
            if _rate_limiter:
                allowed, _info = _rate_limiter.is_allowed(rate_key, _RATE_MAX_REQUESTS, _RATE_WINDOW)
                if not allowed:
                    return JSONResponse(status_code=429, content={"detail": "请求过于频繁，请稍后再试"})
            elif not _check_rate(user_id, client_ip, path):
                return JSONResponse(status_code=429, content={"detail": "请求过于频繁，请稍后再试"})
            return await call_next(request)
    return JSONResponse(status_code=401, content={"detail": "未登录或登录已过期"})


async def rate_limit_middleware(request: Request, call_next):
    """兼容旧限流器（如果配置了 _rate_limiter）。"""
    return await call_next(request)
