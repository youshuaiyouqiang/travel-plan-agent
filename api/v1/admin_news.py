"""Task 1 — 新闻来源管理员 API。

设计要点：
- 端点均要求单一系统管理员身份，由 ``app.state.admin_user_id`` 锚定。
- 管理员 ID 在启动期从 ``YUNHE_ADMIN_USERNAME`` 解析，不从 HTTP 请求接收。
- 非管理员统一返回 403，不泄漏资源存在性。
- 审核请求使用 Pydantic v2 + ``Literal`` 限制 decision 合法值，非法值返回 422。
- 内置白名单注册 (``register-builtin``) 同样只允许管理员调用。
- ``source-inits`` 端点用于查询"系统初始化事件"，与审核审计语义不同。
"""

from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from application.exceptions import ForbiddenException, UnauthorizedException
from application.news.models import (
    NewsSourceInit,
    Source,
    SourceAudit,
)
from application.news.source_service import BUILTIN_WHITELIST, SourceService

router = APIRouter(tags=["admin-news"])


class SourceReviewRequest(BaseModel):
    """管理员审核请求体。"""

    model_config = ConfigDict(extra="forbid")

    decision: Literal[
        "pending", "enabled", "lead_only", "rejected", "blocked", "needs_review"
    ]
    reason: str = Field(min_length=1, max_length=500)


class BuiltinSourceRegisterRequest(BaseModel):
    """管理员注册内置白名单来源请求体。"""

    model_config = ConfigDict(extra="forbid")

    domain: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=128)
    tier: Literal["mainstream", "aggregator", "official"]
    init_reason: str = Field(default="产品内置白名单", min_length=1, max_length=500)


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
    """将 Source 序列化为 API 响应；``ai_subscores`` 解析为对象供前端使用。"""
    raw_subscores = source.ai_subscores or "{}"
    try:
        subscores = json.loads(raw_subscores)
    except json.JSONDecodeError:
        subscores = {}
    return {
        "id": source.id,
        "name": source.name,
        "domain": source.domain,
        "tier": source.tier,
        "status": source.status,
        "scoring_mode": source.scoring_mode,
        "ai_score": source.ai_score,
        "ai_reason": source.ai_reason,
        "ai_subscores": subscores,
        "created_at": source.created_at,
        "updated_at": source.updated_at,
    }


def _audit_to_dict(audit: SourceAudit, source_name: str, source_domain: str) -> dict:
    """把 SourceAudit 序列化为 API 响应；JOIN 来源的 name/domain 一起返回。

    设计要点：
    - 前端需要看到"被审核的来源是哪一家"，否则审计列表无法解读。
    - 一次批量取 source_id → (name, domain) 映射，由调用方注入，避免 N+1。
    - 来源被删除时（极少见）回退空串，但保留审计本身。
    """
    return {
        "id": audit.id,
        "source_id": audit.source_id,
        "source_name": source_name,
        "source_domain": source_domain,
        "admin_id": audit.admin_id,
        "previous_status": audit.previous_status,
        "decision": audit.decision,
        "reason": audit.reason,
        "created_at": audit.created_at,
    }


def _init_to_dict(init: NewsSourceInit, domain: str) -> dict:
    """把 init 事件与所属来源的 domain 拼好；domain 由调用方 JOIN 出来。"""
    return {
        "id": init.id,
        "source_id": init.source_id,
        "domain": domain,
        "tier": init.tier,
        "scoring_mode": init.scoring_mode,
        "init_at": init.init_at,
        "init_reason": init.init_reason,
    }


@router.get("/sources")
async def list_sources(request: Request) -> dict:
    """列出所有新闻来源（含 pending/enabled/blocked 等全部状态）。"""
    _require_admin(request)
    service = SourceService()
    sources = service.list_all_sources()
    return {"items": [_source_to_dict(s) for s in sources]}


@router.post("/sources/register-builtin")
async def register_builtin_source(
    req: BuiltinSourceRegisterRequest, request: Request
) -> dict:
    """管理员注册内置白名单来源；幂等。"""
    _require_admin(request)
    service = SourceService()
    source = service.register_builtin_whitelist(
        domain=req.domain,
        name=req.name,
        tier=req.tier,
        init_reason=req.init_reason,
    )
    return _source_to_dict(source)


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
    """列出所有来源审核审计记录；JOIN 来源名/域。"""
    _require_admin(request)
    service = SourceService()
    audits = service.list_audits()
    # 批量 JOIN：source_id → (name, domain)，避免每条审计都查一次
    sources = service.list_all_sources()
    name_by_id = {s.id: s.name for s in sources}
    domain_by_id = {s.id: s.domain for s in sources}
    items = [
        _audit_to_dict(
            a,
            name_by_id.get(a.source_id, ""),
            domain_by_id.get(a.source_id, ""),
        )
        for a in audits
    ]
    return {"items": items}


@router.get("/source-inits")
async def list_source_inits(request: Request) -> dict:
    """列出所有来源初始化事件（内置白名单等非审核动作）。"""
    _require_admin(request)
    service = SourceService()
    inits = service.list_inits()
    # JOIN domain：批量取 source_id → domain 映射，避免 N+1
    sources = service.list_all_sources()
    domain_by_id = {s.id: s.domain for s in sources}
    items = [_init_to_dict(i, domain_by_id.get(i.source_id, "")) for i in inits]
    return {"items": items}


__all__ = [
    "router",
    "BUILTIN_WHITELIST",
]
