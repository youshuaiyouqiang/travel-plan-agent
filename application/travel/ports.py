"""旅行草稿与存档仓储端口。

P2.6 引入：将 ``travel_drafts`` / ``travel_archives`` 两张表的访问从
application 层下沉到 infrastructure，应用层只消费此端口。

端口由消费方（application）定义，由 ``infrastructure.persistence.travel_repository``
提供 ``TravelRepository`` 实现，在 ``init_db()`` 中装配默认实例。
测试可用 fake 实现替代，不创建 SQLite 文件。

注意：旅行草稿模型（``TravelDraft`` / ``TravelArchive``）当前定义在
``application/travel/models.py``，故端口也放在 application 层。后续若将模型
迁至 domain 层，端口应同步迁移至 ``domain/travel/ports.py``。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:  # 避免循环导入；Protocol 仅用于静态类型检查
    from application.travel.models import TravelArchive, TravelDraft


@runtime_checkable
class TravelRepositoryPort(Protocol):
    """旅行草稿与存档的读写端口。

    实现必须保证：
    - 所有 SQL 参数化；
    - ``insert_draft`` / ``insert_archive`` / ``update_draft_plan`` 各自独立提交；
    - ``plan_json`` 以 JSON 文本存储，``manual_edit_fields`` 以排序数组的 JSON 存储。
    """

    def insert_draft(self, draft: TravelDraft) -> None:
        """插入草稿行。"""
        ...

    def get_draft(self, draft_id: str) -> TravelDraft | None:
        """按 ID 查询草稿；不存在返回 None。"""
        ...

    def mark_draft_read_only(self, draft_id: str, updated_at: str) -> None:
        """标记草稿为只读（确认后调用）。"""
        ...

    def update_draft_plan(
        self,
        draft_id: str,
        plan_json: str,
        manual_edit_fields: str,
        updated_at: str,
    ) -> None:
        """更新草稿的 plan 与 manual_edit_fields。"""
        ...

    def insert_archive(self, archive: TravelArchive) -> None:
        """插入存档行。"""
        ...

    def get_archive(self, archive_id: str) -> TravelArchive | None:
        """按 ID 查询存档；不存在返回 None。"""
        ...


# ── 默认仓储装配（过渡方案，同 P2.1–P2.5）───────────────────

_default_repository: TravelRepositoryPort | None = None


def configure_default_travel_repository(repository: TravelRepositoryPort) -> None:
    """注册全局默认旅行仓储（由组合根调用）。"""
    global _default_repository
    _default_repository = repository


def get_default_travel_repository() -> TravelRepositoryPort:
    """获取全局默认旅行仓储；未配置时抛 RuntimeError。"""
    if _default_repository is None:
        raise RuntimeError(
            "TravelRepositoryPort 未配置：请在组合根调用 "
            "configure_default_travel_repository() 或显式注入 repository 参数。"
        )
    return _default_repository
