from __future__ import annotations

from typing import Any

from domain.travel.itinerary.ports import (
    ItineraryRepositoryPort,
    get_default_itinerary_repository,
)
from domain.travel.itinerary.schema import Activity, DayPlan, Itinerary


class ItineraryRepository:
    """行程仓储；通过 ``ItineraryRepositoryPort`` 访问持久化层。

    P2.5：原直连 ``get_connection()`` 的 SQL 已下沉到
    ``infrastructure.persistence.repositories.itinerary.SqliteItineraryRepository``。
    本类只负责委托持久化操作，保持既有调用方的无参构造兼容。
    """

    def __init__(self, repository: ItineraryRepositoryPort | None = None) -> None:
        self._repository = repository or get_default_itinerary_repository()

    def create_itinerary(
        self,
        user_id: str,
        title: str,
        destination: str,
        start_date: str,
        end_date: str,
        session_id: str = "",
        budget: str = "",
        raw_content: str = "",
        status: str = "planning",
    ) -> Itinerary:
        return self._repository.create_itinerary(
            user_id=user_id,
            title=title,
            destination=destination,
            start_date=start_date,
            end_date=end_date,
            session_id=session_id,
            budget=budget,
            raw_content=raw_content,
            status=status,
        )

    def get_itinerary(self, itinerary_id: str) -> Itinerary | None:
        return self._repository.get_itinerary(itinerary_id)

    def list_itineraries(self, user_id: str) -> list[Itinerary]:
        return self._repository.list_itineraries(user_id)

    def list_itineraries_by_session_id(self, session_id: str) -> list[Itinerary]:
        return self._repository.list_itineraries_by_session_id(session_id)

    def update_itinerary(self, itinerary_id: str, **kwargs: object) -> bool:
        return self._repository.update_itinerary(itinerary_id, **kwargs)

    def delete_itinerary(self, itinerary_id: str) -> bool:
        return self._repository.delete_itinerary(itinerary_id)

    def add_day(
        self,
        itinerary_id: str,
        day_index: int,
        date: str = "",
        title: str = "",
        summary: str = "",
    ) -> DayPlan:
        return self._repository.add_day(
            itinerary_id=itinerary_id,
            day_index=day_index,
            date=date,
            title=title,
            summary=summary,
        )

    def add_activity(
        self,
        day_id: int,
        activity_index: int,
        time_slot: str = "",
        title: str = "",
        location: str = "",
        description: str = "",
        image_url: str = "",
        cost: float = 0.0,
        tips: str = "",
    ) -> Activity:
        return self._repository.add_activity(
            day_id=day_id,
            activity_index=activity_index,
            time_slot=time_slot,
            title=title,
            location=location,
            description=description,
            image_url=image_url,
            cost=cost,
            tips=tips,
        )

    def delete_activity(self, activity_id: int) -> bool:
        return self._repository.delete_activity(activity_id)

    def get_activity(self, activity_id: int) -> Activity | None:
        return self._repository.get_activity(activity_id)

    def get_day_itinerary_id(self, day_id: int) -> str | None:
        return self._repository.get_day_itinerary_id(day_id)

    def save_full_itinerary(self, itinerary: Itinerary) -> Itinerary:
        return self._repository.save_full_itinerary(itinerary)

    def create_share_link(self, itinerary_id: str, user_id: str, expires_at: str = "") -> str:
        return self._repository.create_share_link(itinerary_id, user_id, expires_at)

    def get_share_link(self, token: str) -> dict[str, Any] | None:
        return self._repository.get_share_link(token)

    def list_share_links(self, itinerary_id: str) -> list[dict[str, Any]]:
        return self._repository.list_share_links(itinerary_id)

    def delete_share_link(self, token: str) -> bool:
        return self._repository.delete_share_link(token)
