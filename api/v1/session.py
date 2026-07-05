from __future__ import annotations

import os
from datetime import datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from application.exceptions import (
    ConflictException,
    InternalException,
    NotFoundException,
    UnauthorizedException,
    ValidationException,
)
from application.dto.request import ConfirmPlanRequest, RevokeConfirmRequest

router = APIRouter(tags=["sessions"])
confirm_router = APIRouter(tags=["session-confirm"])


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


class CreateSessionResponse(BaseModel):
    session_id: str
    user_id: str


@router.post("")
async def create_session(request: Request) -> dict:
    """创建新会话。"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()
    session_id = os.urandom(8).hex()
    from infrastructure.persistence.session_repository import SessionRepository

    SessionRepository.create(session_id, user_id)
    return {"session_id": session_id, "user_id": user_id}


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
