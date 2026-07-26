"""集中式对象级授权服务。

设计要点：
- 所有 ``require_*`` 方法在资源不存在或不属于当前用户时统一抛
  :class:`NotFoundException`（→ 404），不泄漏资源存在性。
- 用户 ID 只能从服务端认证上下文传入，不信任客户端请求体中的 user_id。
- 行程所有权以 ``itineraries.user_id`` 为准；活动所有权经所属行程间接校验。
- 会话所有权委托 :class:`SessionService.require_owned`，保证与 Task 1 一致。
"""

from __future__ import annotations

from application.exceptions import NotFoundException
from application.session.service import SessionService
from domain.travel.itinerary.repository import ItineraryRepository
from domain.travel.itinerary.schema import Activity, Itinerary


class AuthorizationService:
    """对象级授权服务；无状态，可在 app.state 单例复用。"""

    def __init__(
        self,
        itinerary_repo: ItineraryRepository | None = None,
        session_service: SessionService | None = None,
    ) -> None:
        self._itineraries = itinerary_repo or ItineraryRepository()
        self._sessions = session_service or SessionService()

    # ------------------------------------------------------------------
    # 行程
    # ------------------------------------------------------------------

    def require_itinerary(self, *, user_id: str, itinerary_id: str) -> Itinerary:
        """校验 ``itinerary_id`` 属于 ``user_id``，返回行程对象。"""
        itin = self._itineraries.get_itinerary(itinerary_id)
        if itin is None or itin.user_id != user_id:
            raise NotFoundException("itinerary", itinerary_id)
        return itin

    # ------------------------------------------------------------------
    # 活动
    # ------------------------------------------------------------------

    def require_activity(
        self,
        *,
        user_id: str,
        itinerary_id: str,
        activity_id: int,
    ) -> Activity:
        """校验活动属于 ``itinerary_id`` 且该行程属于 ``user_id``。"""
        # 先校验行程所有权（不通过则 404，不泄漏行程存在性）
        self.require_itinerary(user_id=user_id, itinerary_id=itinerary_id)
        activity = self._itineraries.get_activity(activity_id)
        if activity is None:
            raise NotFoundException("activity", activity_id)
        # 活动经行程间接归属：通过 day_id 反查行程 ID 校验
        day_itinerary_id = self._itinerary_id_of_day(activity.day_id)
        if day_itinerary_id is None or day_itinerary_id != itinerary_id:
            raise NotFoundException("activity", activity_id)
        return activity

    def _itinerary_id_of_day(self, day_id: int) -> str | None:
        """通过 day_id 反查所属 itinerary_id；找不到返回 None。

        P2.6：原直接查询 ``itinerary_days`` 表的 SQL 已委托到
        ``ItineraryRepositoryPort.get_day_itinerary_id``，消除 application
        层对 infrastructure 的直接依赖。
        """
        return self._itineraries.get_day_itinerary_id(day_id)

    # ------------------------------------------------------------------
    # 会话
    # ------------------------------------------------------------------

    def require_session(self, *, user_id: str, session_id: str):
        """校验 ``session_id`` 属于 ``user_id``，返回 SessionRecord。"""
        return self._sessions.require_owned(user_id=user_id, session_id=session_id)
