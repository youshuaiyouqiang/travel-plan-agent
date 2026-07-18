from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from application.authz import AuthorizationService
from application.exceptions import (
    ConflictException,
    InternalException,
    NotFoundException,
    UnauthorizedException,
    ValidationException,
)
from application.dto.request import ConfirmPlanRequest, RevokeConfirmRequest
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

    from infrastructure.persistence.database import get_connection

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT confirmed_plan FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            raise NotFoundException("session", session_id)

        current = row["confirmed_plan"]
        # 幂等：已确认同一个方案
        if current == plan_type:
            return {"message": "already confirmed", "plan_type": plan_type, "itinerary_id": itinerary_id}

        # 冲突：已确认不同方案
        if current is not None and current != "":
            raise ConflictException(
                "已确认其他方案，如需更换请先撤销",
                details={
                    "current_confirmed": current,
                    "hint": "调用 POST /api/session/{session_id}/revoke-confirm 撤销后重新选择",
                },
            )

        # 更新确认状态
        now = datetime.now().isoformat()
        conn.execute(
            "UPDATE sessions SET confirmed_plan = ?, confirmed_at = ? WHERE session_id = ?",
            (plan_type, now, session_id),
        )
        if itinerary_id:
            conn.execute(
                "UPDATE itineraries SET confirmed_plan = ?, confirmed_at = ? WHERE id = ?",
                (plan_type, now, itinerary_id),
            )
        conn.commit()
        return {"confirmed_plan": plan_type, "itinerary_id": itinerary_id, "confirmed_at": now}
    except (NotFoundException, ConflictException, ValidationException):
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise InternalException(str(e))


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

    from infrastructure.persistence.database import get_connection

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT confirmed_plan FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if not row or not row["confirmed_plan"]:
            raise NotFoundException("确认记录", session_id)

        conn.execute(
            "UPDATE sessions SET confirmed_plan = NULL, confirmed_at = NULL WHERE session_id = ?",
            (session_id,),
        )
        if itinerary_id:
            conn.execute(
                "UPDATE itineraries SET confirmed_plan = NULL, confirmed_at = NULL WHERE id = ?",
                (itinerary_id,),
            )
        conn.commit()
        return {"message": "确认已撤销，可重新选择方案"}
    except NotFoundException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise InternalException(str(e))


@confirm_router.get("/{session_id}/confirm-status")
async def get_confirm_status(session_id: str, request: Request) -> dict:
    """查询会话的方案确认状态。"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    # 对象级授权：会话不属于当前用户统一 404，不泄漏存在性
    _get_authz_service(request).require_session(user_id=user_id, session_id=session_id)

    from infrastructure.persistence.database import get_connection

    conn = get_connection()
    row = conn.execute(
        "SELECT confirmed_plan, confirmed_at FROM sessions WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if not row:
        raise NotFoundException("session", session_id)

    # 查找关联的 itinerary_id
    itinerary_row = conn.execute(
        "SELECT id FROM itineraries WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
        (session_id,),
    ).fetchone()

    result: dict = {
        "confirmed_plan": row["confirmed_plan"] if row["confirmed_plan"] else None,
        "confirmed_at": row["confirmed_at"] if row["confirmed_at"] else None,
    }
    if itinerary_row:
        result["itinerary_id"] = itinerary_row["id"]
    return result
