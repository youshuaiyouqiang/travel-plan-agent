from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from application.authz import AuthorizationService
from application.exceptions import (
    UnauthorizedException,
    ValidationException,
)
from application.dto.request import ConfirmPlanRequest, RevokeConfirmRequest
from application.session.confirm_plan_service import ConfirmPlanService
from application.session.schema import UserSessionMode
from application.session.service import SessionService

router = APIRouter(tags=["sessions"])
confirm_router = APIRouter(tags=["session-confirm"])


def _get_session_service(request: Request) -> SessionService:
    """获取应用层 SessionService；若未注入则使用默认可锁定 Agent 构造一个。"""
    service = getattr(request.app.state, "session_service", None)
    if service is None:
        service = SessionService()
        request.app.state.session_service = service
    return service


def _get_authz_service(request: Request) -> AuthorizationService:
    """获取应用层 AuthorizationService；若未注入则按默认依赖构造一个。"""
    service = getattr(request.app.state, "authz_service", None)
    if service is None:
        service = AuthorizationService(session_service=_get_session_service(request))
        request.app.state.authz_service = service
    return service


def _get_confirm_plan_service(request: Request) -> ConfirmPlanService:
    """从组合根容器获取方案确认协调服务。

    P3.3b：原路由内 ``from infrastructure.persistence.database import get_connection``
    的裸 SQL 已下沉到 ``ConfirmPlanService``（协调 SessionRepositoryPort 与
    ItineraryRepositoryPort）。兼容未设置 container 的测试（回退到默认装配）。
    """
    container = getattr(request.app.state, "container", None)
    if container is not None and container.confirm_plan_service is not None:
        return container.confirm_plan_service
    service = getattr(request.app.state, "confirm_plan_service", None)
    if service is not None:
        return service
    return ConfirmPlanService()


def _session_to_payload(record) -> dict:
    """将 SessionRecord 序列化为统一响应的 data 字段。"""
    return {
        "session_id": record.session_id,
        "user_id": record.user_id,
        "mode": record.mode,
        "locked_agent_id": record.locked_agent_id,
        "news_id": record.news_id,
    }


# ── 会话管理（/sessions） ──────────────────────────────────────────


@router.get("")
async def list_sessions(request: Request) -> dict:
    """列出用户的所有会话。"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()
    agent = request.app.state.agent
    sessions = agent.list_user_sessions(user_id)
    return {"sessions": sessions}


class CreateSessionRequest(BaseModel):
    """创建会话请求；用户 API 只允许 yunhe_default 或 agent_locked。"""

    model_config = ConfigDict(extra="forbid")
    mode: UserSessionMode = Field(default="yunhe_default", description="会话模式")
    locked_agent_id: str | None = Field(default=None, description="agent_locked 模式下锁定的 Agent ID")


@router.post("", status_code=201)
async def create_session(request: Request, req: CreateSessionRequest | None = None) -> dict:
    """创建新会话。

    - 不传 body 时按 ``yunhe_default`` 模式创建（向后兼容旧前端）。
    - ``mode=agent_locked`` 必须搭配 ``locked_agent_id``，且该 Agent 必须可用。
    - 用户 API 不接受 ``news_analysis_locked``；该模式仅由新闻分析服务内部创建。
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    body = req or CreateSessionRequest()
    service = _get_session_service(request)
    record = service.create(
        user_id=user_id,
        mode=body.mode,
        locked_agent_id=body.locked_agent_id,
    )
    return {
        "code": 0,
        "message": "success",
        "data": _session_to_payload(record),
    }


class UpdateSessionModeRequest(BaseModel):
    """更新会话模式请求；用户 API 只允许 yunhe_default 或 agent_locked。"""

    model_config = ConfigDict(extra="forbid")
    mode: UserSessionMode = Field(description="目标会话模式")
    locked_agent_id: str | None = Field(default=None, description="agent_locked 模式下锁定的 Agent ID")


@router.patch("/{session_id}/mode")
async def update_session_mode(session_id: str, req: UpdateSessionModeRequest, request: Request) -> dict:
    """更新会话模式。

    - 用户 API 不接受 ``news_analysis_locked``（由 Literal 类型守护）。
    - 会话不属于当前用户时统一返回 404，避免泄漏存在性。
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    service = _get_session_service(request)
    record = service.update_mode(
        user_id=user_id,
        session_id=session_id,
        mode=req.mode,
        locked_agent_id=req.locked_agent_id,
    )
    return {
        "code": 0,
        "message": "success",
        "data": _session_to_payload(record),
    }


@router.delete("/{session_id}")
async def delete_session(session_id: str, request: Request) -> dict:
    """删除指定会话。"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()
    agent = request.app.state.agent
    agent.delete_session(session_id, user_id=user_id)
    return {"detail": "已删除"}


@router.get("/{session_id}/messages")
async def get_session_messages(session_id: str, request: Request) -> dict:
    """获取会话消息列表。"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()
    agent = request.app.state.agent
    snapshot = agent.snapshot_session(session_id)
    if not snapshot:
        return {"messages": []}
    return {"messages": snapshot.get("turns", [])}


# ── 方案确认/撤销（/session） ─────────────────────────────────────


@confirm_router.post("/{session_id}/confirm-plan")
async def confirm_plan(
    session_id: str,
    req: ConfirmPlanRequest,
    request: Request,
) -> dict:
    """确认方案 —— 并发安全设计（幂等 + 409 冲突）。"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    # 对象级授权：会话不属于当前用户统一 404，不泄漏存在性
    _get_authz_service(request).require_session(user_id=user_id, session_id=session_id)

    plan_type = req.plan_type.strip()
    itinerary_id = req.itinerary_id.strip()
    if plan_type not in ("sightseeing", "budget"):
        raise ValidationException("plan_type 必须为 sightseeing 或 budget")

    # P3.3b：原裸 SQL 下沉到 ConfirmPlanService.confirm_plan
    service = _get_confirm_plan_service(request)
    return service.confirm_plan(
        session_id=session_id,
        plan_type=plan_type,
        itinerary_id=itinerary_id,
    )


@confirm_router.post("/{session_id}/revoke-confirm")
async def revoke_confirm(
    session_id: str,
    req: RevokeConfirmRequest,
    request: Request,
) -> dict:
    """撤销确认 —— 恢复所有按钮为可点击态。"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    # 对象级授权：会话不属于当前用户统一 404，不泄漏存在性
    _get_authz_service(request).require_session(user_id=user_id, session_id=session_id)

    itinerary_id = req.itinerary_id.strip()

    # P3.3b：原裸 SQL 下沉到 ConfirmPlanService.revoke_confirm
    service = _get_confirm_plan_service(request)
    return service.revoke_confirm(session_id=session_id, itinerary_id=itinerary_id)


@confirm_router.get("/{session_id}/confirm-status")
async def get_confirm_status(session_id: str, request: Request) -> dict:
    """查询会话的方案确认状态。"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    # 对象级授权：会话不属于当前用户统一 404，不泄漏存在性
    _get_authz_service(request).require_session(user_id=user_id, session_id=session_id)

    # P3.3b：原裸 SQL 下沉到 ConfirmPlanService.get_confirm_status
    service = _get_confirm_plan_service(request)
    return service.get_confirm_status(session_id)
