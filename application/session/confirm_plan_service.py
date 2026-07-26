"""方案确认应用服务 — 跨 session 与 itinerary 聚合的协调逻辑。

P3.3b 引入：将原 ``api/v1/session.py`` 中 confirm-plan / revoke-confirm /
confirm-status 三个路由的裸 SQL 与业务判定（幂等、冲突 409、404 语义）收敛到此。

设计要点：
- ``SessionRepositoryPort`` 提供 ``sessions.confirmed_plan`` 读写；
- ``ItineraryRepositoryPort`` 提供 ``itineraries.confirmed_plan`` 读写与按
  ``session_id`` 反查行程；
- 事务边界：原路由在单连接内同时更新 sessions 与 itineraries 后统一 commit。
  P3.3b 后端口方法各自提交，sessions 的确认状态是唯一真源；itineraries 的
  ``confirmed_plan`` 仅作展示镜像，失败不影响会话确认语义（与 P2 既有取舍一致）。
- 异常映射：``NotFoundException``（会话/确认记录不存在）→ 404；
  ``ConflictException``（已确认其他方案）→ 409。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from application.exceptions import ConflictException, NotFoundException
from domain.travel.itinerary.ports import (
    ItineraryRepositoryPort,
    get_default_itinerary_repository,
)
from domain.user.session.ports import (
    SessionRepositoryPort,
    get_default_session_repository,
)


class ConfirmPlanService:
    """方案确认 / 撤销 / 查询的协调服务。

    无状态，可在 ``app.state`` 单例复用。端口未显式注入时回退到全局默认仓储
    （由 ``init_db()`` 装配），保持与既有 ``SessionService`` / ``ItineraryRepository``
    无参构造一致的兼容语义。
    """

    def __init__(
        self,
        session_repo: SessionRepositoryPort | None = None,
        itinerary_repo: ItineraryRepositoryPort | None = None,
    ) -> None:
        self._sessions = session_repo or get_default_session_repository()
        self._itineraries = itinerary_repo or get_default_itinerary_repository()

    def confirm_plan(
        self,
        *,
        session_id: str,
        plan_type: str,
        itinerary_id: str,
    ) -> dict[str, Any]:
        """确认方案 — 幂等 + 409 冲突。

        - 会话不存在 → ``NotFoundException``（404）
        - 已确认同一方案 → 幂等返回 ``already confirmed``
        - 已确认不同方案 → ``ConflictException``（409）
        - 否则更新 ``sessions.confirmed_plan``；若提供 ``itinerary_id`` 同步更新
          ``itineraries.confirmed_plan``。
        """
        record = self._sessions.get_confirmed_plan(session_id)
        if record is None:
            raise NotFoundException("session", session_id)

        current = record.get("confirmed_plan")
        # 幂等：已确认同一个方案
        if current == plan_type:
            return {
                "message": "already confirmed",
                "plan_type": plan_type,
                "itinerary_id": itinerary_id,
            }

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
        self._sessions.set_confirmed_plan(session_id=session_id, plan_type=plan_type, now=now)
        if itinerary_id:
            self._itineraries.set_itinerary_confirmed_plan(
                itinerary_id=itinerary_id, plan_type=plan_type, now=now
            )
        return {"confirmed_plan": plan_type, "itinerary_id": itinerary_id, "confirmed_at": now}

    def revoke_confirm(self, *, session_id: str, itinerary_id: str) -> dict[str, Any]:
        """撤销确认 — 恢复所有按钮为可点击态。

        - 会话无确认记录 → ``NotFoundException``（404）
        - 否则清空 ``sessions.confirmed_plan``；若提供 ``itinerary_id`` 同步清空
          ``itineraries.confirmed_plan``。
        """
        record = self._sessions.get_confirmed_plan(session_id)
        if record is None or not record.get("confirmed_plan"):
            raise NotFoundException("确认记录", session_id)

        self._sessions.clear_confirmed_plan(session_id)
        if itinerary_id:
            self._itineraries.clear_itinerary_confirmed_plan(itinerary_id)
        return {"message": "确认已撤销，可重新选择方案"}

    def get_confirm_status(self, session_id: str) -> dict[str, Any]:
        """查询会话的方案确认状态。

        - 会话不存在 → ``NotFoundException``（404）
        - 否则返回 ``confirmed_plan`` / ``confirmed_at``，并附加关联的
          ``itinerary_id``（按 ``session_id`` 反查最新行程）。
        """
        record = self._sessions.get_confirmed_plan(session_id)
        if record is None:
            raise NotFoundException("session", session_id)

        result: dict[str, Any] = {
            "confirmed_plan": record.get("confirmed_plan"),
            "confirmed_at": record.get("confirmed_at"),
        }
        itinerary_id = self._itineraries.find_itinerary_id_by_session(session_id)
        if itinerary_id:
            result["itinerary_id"] = itinerary_id
        return result


__all__ = ["ConfirmPlanService"]
