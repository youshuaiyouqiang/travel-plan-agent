from __future__ import annotations

import logging

from fastapi import APIRouter

from application.dto.request import RegisterRequest, LoginRequest
from application.dto.response import AuthResponse
from application.exceptions import ValidationException, UnauthorizedException
from domain.user.auth.auth import UserStore
from domain.user.auth.token import generate_token

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])


def _get_user_store() -> UserStore:
    return UserStore()


@router.post("/register", response_model=AuthResponse)
async def register(req: RegisterRequest) -> AuthResponse:
    user_store = _get_user_store()
    try:
        user = user_store.create(req.username, req.password)
    except ValueError as e:
        raise ValidationException(str(e))
    token = generate_token(user.user_id)
    logger.info("User registered: user_id=%s username=%s", user.user_id, user.username)
    return AuthResponse(user_id=user.user_id, username=user.username, token=token)


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest) -> AuthResponse:
    user_store = _get_user_store()
    user = user_store.authenticate(req.username, req.password)
    if not user:
        raise UnauthorizedException("用户名或密码错误")
    token = generate_token(user.user_id)
    logger.info("User logged in: user_id=%s username=%s", user.user_id, user.username)
    return AuthResponse(user_id=user.user_id, username=user.username, token=token)
