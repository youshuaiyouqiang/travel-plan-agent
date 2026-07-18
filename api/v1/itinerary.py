from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from application.authz import AuthorizationService
from application.dto.request.itinerary import (
    CreateItineraryRequest,
    CreateShareLinkRequest,
    UpdateItineraryRequest,
)
from application.exceptions import (
    NotFoundException,
    UnauthorizedException,
)
from domain.travel.itinerary.repository import ItineraryRepository

logger = logging.getLogger(__name__)

router = APIRouter()

_itinerary_repo = ItineraryRepository()


def _get_authz_service(request: Request) -> AuthorizationService:
    """获取应用层 AuthorizationService；若未注入则按默认依赖构造一个。"""
    service = getattr(request.app.state, "authz_service", None)
    if service is None:
        service = AuthorizationService(itinerary_repo=_itinerary_repo)
        request.app.state.authz_service = service
    return service


@router.post("")
async def create_itinerary(req: CreateItineraryRequest, request: Request) -> dict:
    user_id: str | None = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    days_data = req.days
    if days_data:
        from domain.travel.itinerary.schema import Itinerary as Itin, DayPlan, Activity

        itin = Itin(
            user_id=user_id,
            session_id=req.session_id,
            title=req.title,
            destination=req.destination,
            start_date=req.start_date,
            end_date=req.end_date,
            budget=req.budget,
            raw_content=req.raw_content,
            status=req.status,
        )
        for di, day_data in enumerate(days_data):
            day = DayPlan(
                day_index=di,
                date=str(day_data.get("date", "")),
                title=str(day_data.get("title", "")),
                summary=str(day_data.get("summary", "")),
            )
            for ai, act_data in enumerate(day_data.get("activities", [])):
                act = Activity(
                    activity_index=ai,
                    time_slot=str(act_data.get("time_slot", "")),
                    title=str(act_data.get("title", "")),
                    location=str(act_data.get("location", "")),
                    description=str(act_data.get("description", "")),
                    image_url=str(act_data.get("image_url", "")),
                    cost=float(act_data.get("cost", 0)),
                    tips=str(act_data.get("tips", "")),
                )
                day.activities.append(act)
            itin.days.append(day)
        result = _itinerary_repo.save_full_itinerary(itin)
    else:
        result = _itinerary_repo.create_itinerary(
            user_id=user_id,
            title=req.title,
            destination=req.destination,
            start_date=req.start_date,
            end_date=req.end_date,
            session_id=req.session_id,
            budget=req.budget,
            raw_content=req.raw_content,
            status=req.status,
        )
    return result.to_dict()


@router.get("")
async def list_itineraries(request: Request) -> dict:
    user_id: str | None = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    items = _itinerary_repo.list_itineraries(user_id)
    seen_ids = {i.id for i in items}
    from infrastructure.persistence.database import get_connection

    conn = get_connection()
    session_rows = conn.execute(
        "SELECT DISTINCT session_id FROM tasks WHERE user_id = ? AND session_id != ''",
        (user_id,),
    ).fetchall()
    for row in session_rows:
        sid = row["session_id"]
        if not sid:
            continue
        session_itins = conn.execute(
            "SELECT * FROM itineraries WHERE session_id = ? ORDER BY updated_at DESC",
            (sid,),
        ).fetchall()
        for r in session_itins:
            from domain.travel.itinerary.schema import Itinerary

            itin = Itinerary.from_row(dict(r))
            if itin.id not in seen_ids:
                items.append(itin)
                seen_ids.add(itin.id)
    return {"itineraries": [i.to_list_dict() for i in items]}


@router.get("/{itinerary_id}")
async def get_itinerary(itinerary_id: str, request: Request) -> dict:
    user_id: str | None = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    authz = _get_authz_service(request)
    itin = authz.require_itinerary(user_id=user_id, itinerary_id=itinerary_id)
    return itin.to_dict()


@router.put("/{itinerary_id}")
async def update_itinerary(
    itinerary_id: str,
    req: UpdateItineraryRequest,
    request: Request,
) -> dict:
    user_id: str | None = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    authz = _get_authz_service(request)
    authz.require_itinerary(user_id=user_id, itinerary_id=itinerary_id)

    _itinerary_repo.update_itinerary(itinerary_id, **req.model_dump())
    updated = _itinerary_repo.get_itinerary(itinerary_id)
    return updated.to_dict()


@router.delete("/{itinerary_id}")
async def delete_itinerary(itinerary_id: str, request: Request) -> dict:
    user_id: str | None = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    authz = _get_authz_service(request)
    authz.require_itinerary(user_id=user_id, itinerary_id=itinerary_id)

    _itinerary_repo.delete_itinerary(itinerary_id)
    return {"detail": "已删除"}


@router.delete("/{itinerary_id}/activities/{activity_id}")
async def delete_activity(itinerary_id: str, activity_id: int, request: Request) -> dict:
    user_id: str | None = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    authz = _get_authz_service(request)
    authz.require_activity(
        user_id=user_id, itinerary_id=itinerary_id, activity_id=activity_id
    )

    _itinerary_repo.delete_activity(activity_id)
    return {"detail": "已删除"}


@router.post("/{itinerary_id}/share")
async def create_share_link(
    itinerary_id: str,
    req: CreateShareLinkRequest,
    request: Request,
) -> dict:
    user_id: str | None = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    authz = _get_authz_service(request)
    authz.require_itinerary(user_id=user_id, itinerary_id=itinerary_id)

    token = _itinerary_repo.create_share_link(itinerary_id, user_id, req.expires_at)
    return {"token": token, "itinerary_id": itinerary_id}


@router.get("/{itinerary_id}/shares")
async def list_share_links(itinerary_id: str, request: Request) -> dict:
    user_id: str | None = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    authz = _get_authz_service(request)
    authz.require_itinerary(user_id=user_id, itinerary_id=itinerary_id)

    links = _itinerary_repo.list_share_links(itinerary_id)
    return {"shares": links}


@router.delete("/{itinerary_id}/shares/{token}")
async def delete_share_link(itinerary_id: str, token: str, request: Request) -> dict:
    user_id: str | None = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    authz = _get_authz_service(request)
    authz.require_itinerary(user_id=user_id, itinerary_id=itinerary_id)

    _itinerary_repo.delete_share_link(token)
    return {"detail": "已删除"}
