from __future__ import annotations

import logging
import time

from fastapi import Request
from fastapi.responses import JSONResponse

from config import settings
from domain.shared.cache.ports import NullRateLimiter, RateLimitPort
from domain.user.auth.token import verify_token

logger = logging.getLogger(__name__)

_PUBLIC_PATHS = {"/api/auth/register", "/api/auth/login", "/api/news/trending", "/api/health", "/api/health/metrics", "/api/shared", "/api/v1/auth/register", "/api/v1/auth/login", "/api/v1/news/trending", "/api/v1/health", "/api/v1/health/metrics", "/api/v1/shared", "/health", "/metrics", "/docs", "/openapi.json", "/redoc"}
_PUBLIC_PREFIXES = ("/docs", "/openapi.json", "/redoc", "/api/auth", "/api/v1/auth", "/api/shared", "/api/v1/shared")

# Task 4: 不安全方法（非 GET/HEAD/OPTIONS）使用 cookie 认证时必须携带匹配的 CSRF header
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_CSRF_HEADER = "X-CSRF-Token"
_AUTH_COOKIE = "auth_token"
_CSRF_COOKIE = "csrf_token"

_rate_counters: dict[str, dict[str, float]] = {}
_RATE_WINDOW = 60
_RATE_MAX_REQUESTS = settings.rate_limit_rpm
_RATE_CLEANUP_INTERVAL = 300
_last_rate_cleanup = 0.0


def _resolve_rate_limiter(request: Request) -> RateLimitPort:
    """从 ``app.state`` 取得组合根注册的限流器；未注册时回退到 ``NullRateLimiter``。

    P7 引入：``api/middleware`` 不再直接 import ``infrastructure.cache``。
    限流器实例在 ``app.py`` 的 ``build_container()`` 中创建并放入
    ``app.state.rate_limiter``；中间件只消费 ``RateLimitPort`` 端口。
    """
    limiter = getattr(request.app.state, "rate_limiter", None)
    if limiter is None:
        return NullRateLimiter()
    return limiter


def _make_rate_key(user_id: str, ip: str, path: str) -> str:
    prefix = path.split("/api/")[-1].split("/")[0] if "/api/" in path else path.strip("/")
    return f"{user_id}:{ip}:{prefix}"


def _cleanup_rate_counters(now: float) -> None:
    global _last_rate_cleanup
    if now - _last_rate_cleanup < _RATE_CLEANUP_INTERVAL:
        return
    _last_rate_cleanup = now
    expired_keys = [k for k, v in _rate_counters.items() if now - v.get("window_start", 0) > _RATE_WINDOW * 2]
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


def _enforce_rate_limit(
    request: Request, user_id: str, client_ip: str, path: str
) -> JSONResponse | None:
    """根据 ``app.state.rate_limiter`` 端口执行限流；超限返回 429 响应。

    P7 引入：限流器从 ``app.state`` 获取，不再 import ``infrastructure``。
    未配置限流器时回退到 ``NullRateLimiter``（始终放行）。
    """
    rate_limiter = _resolve_rate_limiter(request)
    rate_key = _make_rate_key(user_id, client_ip, path)
    if rate_limiter is not None and not isinstance(rate_limiter, NullRateLimiter):
        allowed, _info = rate_limiter.is_allowed(
            rate_key, _RATE_MAX_REQUESTS, _RATE_WINDOW
        )
        if not allowed:
            return JSONResponse(
                status_code=429, content={"detail": "请求过于频繁，请稍后再试"}
            )
        return None
    # NullRateLimiter 视为未配置；继续走本地内存计数（向后兼容）
    if not _check_rate(user_id, client_ip, path):
        return JSONResponse(
            status_code=429, content={"detail": "请求过于频繁，请稍后再试"}
        )
    return None


def _extract_bearer_token(request: Request) -> str | None:
    """从 Authorization 头提取 Bearer token；其他形式返回 None。"""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header.removeprefix("Bearer ").strip()
    return None


def _extract_cookie_token(request: Request) -> str | None:
    """从 ``auth_token`` cookie 提取 token。"""
    return request.cookies.get(_AUTH_COOKIE)


def _csrf_check_passes(request: Request) -> bool:
    """对 cookie 认证的不安全方法做 double-submit CSRF 校验。

    - 安全方法（GET/HEAD/OPTIONS）：不需要 CSRF header
    - 不安全方法：``X-CSRF-Token`` header 必须存在且等于 ``csrf_token`` cookie 值
    - Bearer 模式：不调用此函数，天然免疫 CSRF
    """
    if request.method in _SAFE_METHODS:
        return True
    cookie_csrf = request.cookies.get(_CSRF_COOKIE)
    header_csrf = request.headers.get(_CSRF_HEADER)
    if not cookie_csrf or not header_csrf:
        return False
    return cookie_csrf == header_csrf


async def auth_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)
    path = request.url.path
    if (
        path in _PUBLIC_PATHS
        or path.startswith("/api/auth")
        or path.startswith("/api/shared")
    ):
        return await call_next(request)
    if any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES):
        return await call_next(request)

    # 优先 Bearer token（非浏览器客户端）
    bearer_token = _extract_bearer_token(request)
    cookie_token = _extract_cookie_token(request)

    if bearer_token is not None:
        user_id = verify_token(bearer_token)
        if user_id:
            request.state.user_id = user_id
            request.state.auth_method = "bearer"
            client_ip = request.client.host if request.client else "unknown"
            rate_block = _enforce_rate_limit(request, user_id, client_ip, path)
            if rate_block is not None:
                return rate_block
            return await call_next(request)
        return JSONResponse(status_code=401, content={"detail": "未登录或登录已过期"})

    # 浏览器流程：cookie + CSRF
    if cookie_token:
        if not _csrf_check_passes(request):
            return JSONResponse(status_code=401, content={"detail": "CSRF 校验失败"})
        user_id = verify_token(cookie_token)
        if user_id:
            request.state.user_id = user_id
            request.state.auth_method = "cookie"
            client_ip = request.client.host if request.client else "unknown"
            rate_block = _enforce_rate_limit(request, user_id, client_ip, path)
            if rate_block is not None:
                return rate_block
            return await call_next(request)
        return JSONResponse(status_code=401, content={"detail": "未登录或登录已过期"})

    return JSONResponse(status_code=401, content={"detail": "未登录或登录已过期"})


async def rate_limit_middleware(request: Request, call_next):
    """兼容旧限流器（如果配置了 _rate_limiter）。"""
    return await call_next(request)
