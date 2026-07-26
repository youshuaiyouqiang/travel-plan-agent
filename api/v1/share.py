from __future__ import annotations

from fastapi import APIRouter, Request

from application.exceptions import NotFoundException

router = APIRouter(tags=["shared"])


@router.get("/{token}")
async def get_shared_itinerary(token: str, request: Request) -> dict:
    # P3.3a：从组合根容器获取行程仓储，不再导入 domain.travel.itinerary.repository
    itinerary_repo = request.app.state.container.itinerary_repo
    link = itinerary_repo.get_share_link(token)
    if not link:
        raise NotFoundException("分享链接", token)
    itin = itinerary_repo.get_itinerary(link["itinerary_id"])
    if not itin:
        raise NotFoundException("行程", link["itinerary_id"])
    return {
        "itinerary": itin.to_dict(),
        "share_info": {
            "view_count": link["view_count"],
            "created_at": link["created_at"],
        },
    }
