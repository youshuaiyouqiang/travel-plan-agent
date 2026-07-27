"""行程仓储端口。

P2.5 引入：将 ``itineraries`` / ``itinerary_days`` / ``itinerary_activities`` /
``shared_links`` 四张表的访问从 domain 层下沉到 infrastructure，领域层只消费此端口。

端口由消费方（domain）定义，由 ``infrastructure.persistence.repositories.itinerary``
提供 ``SqliteItineraryRepository`` 实现，在 ``init_db()`` 中装配默认实例。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:  # 避免循环导入；Protocol 仅用于静态类型检查
    from domain.travel.itinerary.schema import Activity, DayPlan, Itinerary


@runtime_checkable
class ItineraryRepositoryPort(Protocol):
    """行程与分享链接的读写端口。

    实现必须保证：
    - 所有 SQL 参数化；``update_itinerary`` 的字段白名单在实现层硬编码；
    - ``get_itinerary`` 同时加载 days 和 activities（聚合根完整加载）；
    - ``save_full_itinerary`` 创建行程 + 天数 + 活动后返回完整聚合根。
    """

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
        """创建行程行，返回 Itinerary 聚合（不含 days）。"""
        ...

    def get_itinerary(self, itinerary_id: str) -> Itinerary | None:
        """按 ID 加载行程聚合（含 days 与 activities）；不存在返回 None。"""
        ...

    def list_itineraries(self, user_id: str) -> list[Itinerary]:
        """列出用户全部行程（不含 days），按 updated_at 倒序。"""
        ...

    def list_itineraries_by_session_id(self, session_id: str) -> list[Itinerary]:
        """按 ``session_id`` 列出行程（不含 days），按 updated_at 倒序。

        P3.3b 引入：供 ``api/v1/itinerary.py`` 的 ``list_itineraries`` 路由
        查找用户会话关联的行程，避免 api 层直接查询 ``itineraries`` 表。
        """
        ...

    def update_itinerary(self, itinerary_id: str, **kwargs: object) -> bool:
        """按白名单字段更新行程；返回是否实际更新。"""
        ...

    def delete_itinerary(self, itinerary_id: str) -> bool:
        """删除行程行；返回是否删除成功。"""
        ...

    def add_day(
        self,
        itinerary_id: str,
        day_index: int,
        date: str = "",
        title: str = "",
        summary: str = "",
    ) -> DayPlan:
        """添加天数行，返回 DayPlan。"""
        ...

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
        """添加活动行，返回 Activity。"""
        ...

    def delete_activity(self, activity_id: int) -> bool:
        """删除活动行；返回是否删除成功。"""
        ...

    def get_activity(self, activity_id: int) -> Activity | None:
        """按 ID 查询活动；不存在返回 None。"""
        ...

    def get_day_itinerary_id(self, day_id: int) -> str | None:
        """按 day_id 反查所属 itinerary_id；找不到返回 None。

        P2.6 引入：供 ``AuthorizationService.require_activity`` 做对象级
        授权校验，避免 application 层直接查询 ``itinerary_days`` 表。
        """
        ...

    def save_full_itinerary(self, itinerary: Itinerary) -> Itinerary:
        """创建完整行程（行程 + 天数 + 活动），返回加载后的聚合根。"""
        ...

    def create_share_link(self, itinerary_id: str, user_id: str, expires_at: str = "") -> str:
        """创建分享链接，返回 token。"""
        ...

    def get_share_link(self, token: str) -> dict[str, Any] | None:
        """按 token 查询分享链接并递增 view_count；不存在返回 None。"""
        ...

    def list_share_links(self, itinerary_id: str) -> list[dict[str, Any]]:
        """列出行程的全部分享链接，按 created_at 倒序。"""
        ...

    def delete_share_link(self, token: str) -> bool:
        """删除分享链接；返回是否删除成功。"""
        ...

    # ── 方案确认（P3.3b 引入，供 ConfirmPlanService 使用）─────────

    def set_itinerary_confirmed_plan(self, *, itinerary_id: str, plan_type: str, now: str) -> None:
        """更新行程的 ``confirmed_plan`` 与 ``confirmed_at``。"""
        ...

    def clear_itinerary_confirmed_plan(self, itinerary_id: str) -> None:
        """清空行程的 ``confirmed_plan`` 与 ``confirmed_at``（置 NULL）。"""
        ...

    def find_itinerary_id_by_session(self, session_id: str) -> str | None:
        """按 ``session_id`` 查询最新行程 ID（ORDER BY created_at DESC LIMIT 1）。

        P3.3b 引入：供 ``ConfirmPlanService.get_confirm_status`` 查找关联行程，
        避免 api 层直接查询 ``itineraries`` 表。
        """
        ...

    def update_raw_content(self, itinerary_id: str, raw_content: str) -> bool:
        """更新行程的 ``raw_content`` 字段（用于保存多方案元数据）。

        P7 引入：供 ``domain.travel.tools.generate_itinerary_overview`` 在
        tool handler 中保存原始行程内容；替代之前直接 ``UPDATE itineraries``
        的内联 SQL。
        """
        ...


# ── 默认仓储装配（过渡方案，同 P2.1–P2.4）───────────────────

_default_repository: ItineraryRepositoryPort | None = None


def configure_default_itinerary_repository(repository: ItineraryRepositoryPort) -> None:
    """注册全局默认行程仓储（由组合根调用）。"""
    global _default_repository
    _default_repository = repository


def get_default_itinerary_repository() -> ItineraryRepositoryPort:
    """获取全局默认行程仓储；未配置时抛 RuntimeError。"""
    if _default_repository is None:
        raise RuntimeError(
            "ItineraryRepositoryPort 未配置：请在组合根调用 "
            "configure_default_itinerary_repository() 或显式注入 repository 参数。"
        )
    return _default_repository
