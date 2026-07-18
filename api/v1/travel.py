"""Task 2 — 旅行草稿编辑 API。

路由前缀由 ``api/v1/__init__.py`` 挂载为 ``/travel``。

端点：
- ``POST /drafts`` 创建草稿
- ``PATCH /drafts/{draft_id}/activities/{activity_id}`` 手工编辑活动（保护字段不被 Agent 覆盖）
- ``POST /drafts/{draft_id}/refresh-preview`` 刷新预览（唯一调用外部 provider 的入口）
- ``POST /drafts/{draft_id}/refresh-apply`` 应用用户勾选的变更 ID

业务红线：Agent 不能覆盖手动编辑字段；行程外部信息仅在用户点击"更新信息"时查询。
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from application.dto.request.travel import (
    CreateDraftRequest,
    EditActivityRequest,
    RefreshApplyRequest,
)
from application.exceptions import UnauthorizedException
from application.travel.service import TravelService

router = APIRouter(tags=["travel"])


def _get_travel_service(request: Request) -> TravelService:
    """获取应用层 TravelService；若未注入则构造一个默认实例。"""
    service = getattr(request.app.state, "travel_service", None)
    if service is None:
        service = TravelService()
        request.app.state.travel_service = service
    return service


def _draft_to_payload(draft) -> dict:
    """将 TravelDraft 序列化为统一响应的 data 字段。"""
    return {
        "id": draft.id,
        "user_id": draft.user_id,
        "session_id": draft.session_id,
        "plan": draft.plan,
        "manual_edit_fields": sorted(draft.manual_edit_fields),
        "is_read_only": draft.is_read_only,
        "source_archive_id": draft.source_archive_id,
    }


@router.post("/drafts", status_code=201)
async def create_draft(req: CreateDraftRequest, request: Request) -> dict:
    """创建新的旅行草稿。"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()
    service = _get_travel_service(request)
    draft = service.save_draft(user_id, req.session_id, req.plan)
    return {"code": 0, "message": "success", "data": _draft_to_payload(draft)}


@router.patch("/drafts/{draft_id}/activities/{activity_id}")
async def patch_activity(
    draft_id: str,
    activity_id: str,
    req: EditActivityRequest,
    request: Request,
) -> dict:
    """手工编辑活动字段；被编辑字段记入 manual_edit_fields，保护其不被 Agent 覆盖。

    不属于该用户的草稿统一返回 404，避免泄漏存在性。
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()
    service = _get_travel_service(request)
    draft = service.edit_activity(
        user_id,
        draft_id,
        activity_id,
        title=req.title,
        time_slot=req.time_slot,
        location=req.location,
        note=req.note,
    )
    return {"code": 0, "message": "success", "data": _draft_to_payload(draft)}


@router.post("/drafts/{draft_id}/refresh-preview")
async def refresh_preview(draft_id: str, request: Request) -> dict:
    """刷新预览：唯一调用外部 provider 的入口。

    本期返回空变更列表；外部 provider（路线/天气/地点）接入在后续任务完成。
    所有刷新必须经此端点，不得在其他端点内直接访问外部信息。
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()
    service = _get_travel_service(request)
    draft = service.require_owned_draft(user_id, draft_id)
    return {
        "code": 0,
        "message": "success",
        "data": {"draft_id": draft.id, "changes": []},
    }


@router.post("/drafts/{draft_id}/refresh-apply")
async def refresh_apply(
    draft_id: str, req: RefreshApplyRequest, request: Request
) -> dict:
    """应用用户勾选的刷新变更。

    仅接收用户在冲突界面勾选的变更 ID；本期 change_ids 为空，外部接入在后续任务完成。
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()
    service = _get_travel_service(request)
    draft = service.require_owned_draft(user_id, draft_id)
    return {"code": 0, "message": "success", "data": _draft_to_payload(draft)}
