"""Task 1 — 新闻来源管理员 API。

设计要点：
- 三个端点均要求单一系统管理员身份，由 ``app.state.admin_user_id`` 锚定。
- 管理员 ID 在启动期从 ``CLAW_ADMIN_USERNAME`` 解析，不从 HTTP 请求接收。
- 非管理员统一返回 403，不泄漏资源存在性。
- 审核请求使用 Pydantic v2 + ``Literal`` 限制 decision 合法值，非法值返回 422。
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from application.exceptions import ForbiddenException, UnauthorizedException
from application.news.models import Source, SourceAudit, SourceStatus
from application.news.source_service import SourceService

router = APIRouter(tags=["admin-news"])


class SourceReviewRequest(BaseModel):
    """管理员审核请求体。"""

    model_config = ConfigDict(extra="forbid")

    decision: Literal[
        "pending", "enabled", "lead_only", "rejected", "blocked", "needs_review"
    ]
    reason: str = Field(min_length=1, max_length=500)


def _require_admin(request: Request) -> str:
    """校验当前认证用户是启动期锚定的管理员；否则抛 403。"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()
    admin_user_id = getattr(request.app.state, "admin_user_id", None)
    if not admin_user_id or user_id != admin_user_id:
        raise ForbiddenException()
    return user_id


def _source_to_dict(source: Source) -> dict:
    return {
        "id": source.id,
        "name": source.name,
        "domain": source.domain,
        "tier": source.tier,
        "status": source.status,
        "ai_score": source.ai_score,
        "ai_reason": source.ai_reason,
        "created_at": source.created_at,
        "updated_at": source.updated_at,
    }


def _audit_to_dict(audit: SourceAudit) -> dict:
    return {
        "id": audit.id,
        "source_id": audit.source_id,
        "admin_id": audit.admin_id,
        "previous_status": audit.previous_status,
        "decision": audit.decision,
        "reason": audit.reason,
        "created_at": audit.created_at,
    }


@router.get("/sources")
async def list_sources(request: Request) -> dict:
    """列出所有新闻来源（含 pending/enabled/blocked 等全部状态）。"""
    _require_admin(request)
    service = SourceService()
    sources = service.list_all_sources()
    return {"items": [_source_to_dict(s) for s in sources]}


@router.post("/sources/{source_id}/review")
async def review_source(
    source_id: str, req: SourceReviewRequest, request: Request
) -> dict:
    """管理员审核来源：更新状态 + 写审计。"""
    admin_id = _require_admin(request)
    service = SourceService()
    reviewed = service.review_source(admin_id, source_id, req.decision, req.reason)
    return _source_to_dict(reviewed)


@router.get("/source-audits")
async def list_audits(request: Request) -> dict:
    """列出所有来源审核审计记录。"""
    _require_admin(request)
    service = SourceService()
    audits = service.list_audits()
    return {"items": [_audit_to_dict(a) for a in audits]}
