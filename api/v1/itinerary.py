from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from application.dto.request.itinerary import (
    CheckinActivityRequest,
    CompareItinerariesRequest,
    CreateItineraryRequest,
    CreateShareLinkRequest,
    UpdateActivityCostRequest,
    UpdateItineraryRequest,
)
from application.exceptions import (
    NotFoundException,
    UnauthorizedException,
    ValidationException,
)
from domain.travel.itinerary.repository import ItineraryRepository

logger = logging.getLogger(__name__)

router = APIRouter()

_itinerary_repo = ItineraryRepository()


def _user_owns_itinerary(user_id: str, itin) -> bool:
    """检查用户是否拥有该行程的所有权。"""
    if itin.user_id and itin.user_id == user_id:
        return True
    if itin.session_id:
        from infrastructure.persistence.database import get_connection

        conn = get_connection()
        row = conn.execute(
            "SELECT 1 FROM tasks WHERE user_id = ? AND session_id = ? LIMIT 1",
            (user_id, itin.session_id),
        ).fetchone()
        if row:
            return True
    if itin.user_id:
        from domain.user.auth.auth import UserStore

        us = UserStore()
        existing = us.get_by_id(itin.user_id)
        if not existing:
            return True
    return False


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


@router.post("/compare")
async def compare_itineraries(req: CompareItinerariesRequest, request: Request) -> dict:
    user_id: str | None = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    results = []
    for itin_id in req.ids:
        itin = _itinerary_repo.get_itinerary(str(itin_id))
        if not itin or not _user_owns_itinerary(user_id, itin):
            continue
        total_budget = sum(a.cost for d in itin.days for a in d.activities)
        total_actual = sum(a.actual_cost for d in itin.days for a in d.activities)
        results.append(
            {
                "id": itin.id,
                "title": itin.title,
                "destination": itin.destination,
                "start_date": itin.start_date,
                "end_date": itin.end_date,
                "budget_text": itin.budget,
                "budget_total": total_budget,
                "actual_total": total_actual,
                "days_count": len(itin.days),
                "activities_count": sum(len(d.activities) for d in itin.days),
                "days": [
                    {
                        "day_index": d.day_index,
                        "date": d.date,
                        "title": d.title,
                        "summary": d.summary,
                        "budget": sum(a.cost for a in d.activities),
                        "actual": sum(a.actual_cost for a in d.activities),
                        "activities": [
                            {
                                "time_slot": a.time_slot,
                                "title": a.title,
                                "location": a.location,
                                "cost": a.cost,
                                "actual_cost": a.actual_cost,
                            }
                            for a in d.activities
                        ],
                    }
                    for d in itin.days
                ],
            }
        )
    if len(results) < 2:
        raise ValidationException("有效行程不足2个")
    return {"itineraries": results}


@router.get("/{itinerary_id}")
async def get_itinerary(itinerary_id: str, request: Request) -> dict:
    user_id: str | None = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    itin = _itinerary_repo.get_itinerary(itinerary_id)
    if not itin:
        raise NotFoundException("行程", itinerary_id)
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

    itin = _itinerary_repo.get_itinerary(itinerary_id)
    if not itin or not _user_owns_itinerary(user_id, itin):
        raise NotFoundException("行程", itinerary_id)

    _itinerary_repo.update_itinerary(itinerary_id, **req.model_dump())
    updated = _itinerary_repo.get_itinerary(itinerary_id)
    return updated.to_dict()


@router.delete("/{itinerary_id}")
async def delete_itinerary(itinerary_id: str, request: Request) -> dict:
    user_id: str | None = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    itin = _itinerary_repo.get_itinerary(itinerary_id)
    if not itin or not _user_owns_itinerary(user_id, itin):
        raise NotFoundException("行程", itinerary_id)

    _itinerary_repo.delete_itinerary(itinerary_id)
    return {"detail": "已删除"}


@router.patch("/{itinerary_id}/activities/{activity_id}/checkin")
async def checkin_activity(
    itinerary_id: str,
    activity_id: int,
    req: CheckinActivityRequest,
    request: Request,
) -> dict:
    user_id: str | None = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    itin = _itinerary_repo.get_itinerary(itinerary_id)
    if not itin or not _user_owns_itinerary(user_id, itin):
        raise NotFoundException("行程", itinerary_id)

    activity = _itinerary_repo.get_activity(activity_id)
    if not activity:
        raise NotFoundException("活动", activity_id)

    if req.checked_in:
        _itinerary_repo.check_in_activity(activity_id)
    else:
        _itinerary_repo.uncheck_activity(activity_id)
    updated = _itinerary_repo.get_activity(activity_id)
    return updated.to_dict()


@router.delete("/{itinerary_id}/activities/{activity_id}")
async def delete_activity(itinerary_id: str, activity_id: int, request: Request) -> dict:
    user_id: str | None = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    itin = _itinerary_repo.get_itinerary(itinerary_id)
    if not itin or not _user_owns_itinerary(user_id, itin):
        raise NotFoundException("行程", itinerary_id)

    _itinerary_repo.delete_activity(activity_id)
    return {"detail": "已删除"}


@router.patch("/{itinerary_id}/activities/{activity_id}/cost")
async def update_activity_cost(
    itinerary_id: str,
    activity_id: int,
    req: UpdateActivityCostRequest,
    request: Request,
) -> dict:
    user_id: str | None = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    itin = _itinerary_repo.get_itinerary(itinerary_id)
    if not itin or not _user_owns_itinerary(user_id, itin):
        raise NotFoundException("行程", itinerary_id)

    _itinerary_repo.update_actual_cost(activity_id, req.actual_cost)
    updated = _itinerary_repo.get_activity(activity_id)
    return updated.to_dict()


@router.get("/{itinerary_id}/expense-summary")
async def expense_summary(itinerary_id: str, request: Request) -> dict:
    user_id: str | None = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    itin = _itinerary_repo.get_itinerary(itinerary_id)
    if not itin or not _user_owns_itinerary(user_id, itin):
        raise NotFoundException("行程", itinerary_id)

    total_budget = 0.0
    total_actual = 0.0
    day_summaries = []
    for day in itin.days:
        day_budget = sum(a.cost for a in day.activities)
        day_actual = sum(a.actual_cost for a in day.activities)
        total_budget += day_budget
        total_actual += day_actual
        day_summaries.append(
            {
                "day_index": day.day_index,
                "date": day.date,
                "title": day.title,
                "budget": day_budget,
                "actual": day_actual,
                "activities": [
                    {
                        "id": a.id,
                        "title": a.title,
                        "budget": a.cost,
                        "actual": a.actual_cost,
                        "checked_in": a.checked_in,
                    }
                    for a in day.activities
                ],
            }
        )
    budget_str = itin.budget or ""
    budget_num = 0.0
    for seg in budget_str.replace("约", "").replace("元", "").replace("/人", "").replace(",", "").split():
        try:
            budget_num = float(seg)
            break
        except ValueError:
            continue
    return {
        "itinerary_id": itinerary_id,
        "title": itin.title,
        "budget_text": itin.budget,
        "budget_total": budget_num or total_budget,
        "actual_total": total_actual,
        "remaining": (budget_num or total_budget) - total_actual,
        "days": day_summaries,
    }


@router.post("/{itinerary_id}/share")
async def create_share_link(
    itinerary_id: str,
    req: CreateShareLinkRequest,
    request: Request,
) -> dict:
    user_id: str | None = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    itin = _itinerary_repo.get_itinerary(itinerary_id)
    if not itin or not _user_owns_itinerary(user_id, itin):
        raise NotFoundException("行程", itinerary_id)

    token = _itinerary_repo.create_share_link(itinerary_id, user_id, req.expires_at)
    return {"token": token, "itinerary_id": itinerary_id}


@router.get("/{itinerary_id}/shares")
async def list_share_links(itinerary_id: str, request: Request) -> dict:
    user_id: str | None = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    links = _itinerary_repo.list_share_links(itinerary_id)
    return {"shares": links}


@router.delete("/{itinerary_id}/shares/{token}")
async def delete_share_link(itinerary_id: str, token: str, request: Request) -> dict:
    user_id: str | None = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    _itinerary_repo.delete_share_link(token)
    return {"detail": "已删除"}
