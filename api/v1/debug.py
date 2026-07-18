from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from application.authz import AuthorizationService
from application.exceptions import UnauthorizedException

router = APIRouter(tags=["debug"])

logger = logging.getLogger(__name__)


def _get_authz_service(request: Request) -> AuthorizationService:
    """获取应用层 AuthorizationService；若未注入则按默认依赖构造一个。"""
    service = getattr(request.app.state, "authz_service", None)
    if service is None:
        service = AuthorizationService()
        request.app.state.authz_service = service
    return service


def _require_user(request: Request) -> str:
    """从认证上下文取得 user_id；未认证抛 401。"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()
    return user_id


@router.get("/trace/{session_id}")
async def latest_trace(session_id: str, request: Request) -> dict:
    """返回会话最近一次 trace；仅会话所有者可访问。"""
    user_id = _require_user(request)
    _get_authz_service(request).require_session(user_id=user_id, session_id=session_id)
    agent = request.app.state.agent
    logger.debug("API /debug/trace request: session_id=%s", session_id)
    return {"trace": agent.latest_trace(session_id)}


@router.get("/session/{session_id}")
async def session_snapshot(session_id: str, request: Request) -> dict:
    """返回会话快照；仅会话所有者可访问。"""
    user_id = _require_user(request)
    _get_authz_service(request).require_session(user_id=user_id, session_id=session_id)
    agent = request.app.state.agent
    logger.debug("API /debug/session request: session_id=%s user_id=%s", session_id, user_id)
    return {
        "session": agent.snapshot_session(session_id),
        "task": agent.snapshot_task(session_id, user_id=user_id),
    }


@router.get("/mcp")
async def mcp_snapshot(request: Request) -> dict:
    """返回 MCP 服务器列表；需要登录，但不绑定具体资源。"""
    _require_user(request)
    agent = request.app.state.agent
    logger.debug("API /debug/mcp request")
    return {"servers": agent.list_mcp_servers()}


@router.get("/mcp/select")
async def mcp_selection(query: str, request: Request) -> dict:
    """MCP 工具检索；需要登录，但不绑定具体资源。"""
    _require_user(request)
    agent = request.app.state.agent
    logger.debug("API /debug/mcp/select request: query=%s", query)
    return {"items": agent.select_mcp_tools(query, limit=4)}


@router.get("/task/{session_id}")
async def task_snapshot(session_id: str, request: Request) -> dict:
    """返回会话任务快照；仅会话所有者可访问。"""
    user_id = _require_user(request)
    _get_authz_service(request).require_session(user_id=user_id, session_id=session_id)
    agent = request.app.state.agent
    logger.debug("API /debug/task request: session_id=%s user_id=%s", session_id, user_id)
    return {"task": agent.snapshot_task(session_id, user_id=user_id)}
