from __future__ import annotations

import logging
import secrets
from typing import Literal

from fastapi import APIRouter, Response

from application.dto.request import RegisterRequest, LoginRequest
from application.dto.response import AuthResponse
from application.exceptions import ValidationException, UnauthorizedException
from domain.user.auth.auth import UserStore
from domain.user.auth.token import generate_token

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

# Cookie 属性：浏览器流程使用 Secure/HttpOnly/SameSite=Lax；CSRF cookie 可被 JS 读取。
# P0-1 修复：登录响应体不再返回 token，浏览器 JS 无法读取长期认证凭据。
# P0-2 修复：csrf_token cookie 使用独立的随机值，不再等于 auth_token，避免 HttpOnly 保护被绕过。
_COOKIE_PATH = "/"
_COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
_COOKIE_MAX_AGE = 86400 * 7  # 与 token 过期时间一致
_COOKIE_DOMAIN = "127.0.0.1"  # 明确设置 domain 支持 127.0.0.1 访问


def _generate_csrf_token() -> str:
    """生成独立的 CSRF 随机值；与认证 token 无关。"""
    return secrets.token_urlsafe(32)


def _set_auth_cookies(response: Response, token: str, *, secure: bool = True) -> None:
    """登录/注册成功后同时下发 ``auth_token`` 与 ``csrf_token`` cookie。

    - ``auth_token``：HttpOnly，前端 JS 不可读，浏览器自动随请求发送。
    - ``csrf_token``：非 HttpOnly，使用与 ``auth_token`` 不同的独立随机值；
      前端读取后通过 ``X-CSRF-Token`` header 回传，middleware 校验 header 与 cookie 是否匹配
      （double-submit 模式）。CSRF 值独立于 auth_token，确保 JS 无法通过 csrf cookie 反查 HttpOnly 认证 token。

    生产环境（HTTPS）应使用 ``Secure`` 标志；本地开发 (HTTP) 由调用方关闭。
    本任务默认开启 Secure，测试场景通过 ASGI transport 不受浏览器 Secure 限制。
    """
    csrf_value = _generate_csrf_token()
    response.set_cookie(
        key="auth_token",
        value=token,
        max_age=_COOKIE_MAX_AGE,
        path=_COOKIE_PATH,
        domain=_COOKIE_DOMAIN,
        httponly=True,
        secure=secure,
        samesite=_COOKIE_SAMESITE,
    )
    response.set_cookie(
        key="csrf_token",
        value=csrf_value,
        max_age=_COOKIE_MAX_AGE,
        path=_COOKIE_PATH,
        domain=_COOKIE_DOMAIN,
        httponly=False,
        secure=secure,
        samesite=_COOKIE_SAMESITE,
    )


def _get_user_store() -> UserStore:
    return UserStore()


@router.post("/register", response_model=AuthResponse)
async def register(req: RegisterRequest, response: Response) -> AuthResponse:
    user_store = _get_user_store()
    try:
        user = user_store.create(req.username, req.password)
    except ValueError as e:
        raise ValidationException(str(e)) from e
    token = generate_token(user.user_id)
    _set_auth_cookies(response, token)
    logger.info("User registered: user_id=%s username=%s", user.user_id, user.username)
    return AuthResponse(user_id=user.user_id, username=user.username)


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest, response: Response) -> AuthResponse:
    user_store = _get_user_store()
    user = user_store.authenticate(req.username, req.password)
    if not user:
        raise UnauthorizedException("用户名或密码错误")
    token = generate_token(user.user_id)
    _set_auth_cookies(response, token)
    logger.info("User logged in: user_id=%s username=%s", user.user_id, user.username)
    return AuthResponse(user_id=user.user_id, username=user.username)
