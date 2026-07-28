"""缓存仓储端口——application 层共享契约，infrastructure 层实现。

设计要点（AGENTS.md §8.1 端口先于实现 + §4 SQL 参数化）：
- 端口集中定义读写两侧的方法；避免 review_service / report_service
  各定义私有 Protocol 导致 infrastructure 实现要重复满足多份契约
- 表名由 infrastructure 层在内部白名单控制；application 层不感知表名
- 所有方法 ``*_date`` / ``user_id`` / ``stock_code`` 等都是 ? 占位符
  参数化的依据
"""

from __future__ import annotations

from typing import Any, Protocol

from domain.stock.models import ReviewReport


class CacheRepositoryPort(Protocol):
    """缓存仓储端口——读写两侧的完整契约。

    写侧（review_service 用）：
    - ``save_review_report``
    - ``add_watchlist_stock``
    - ``remove_watchlist_stock``

    读侧（report_service / API 用）：
    - ``select_review_report``
    - ``select_review_reports``
    """

    # ── 写侧：复盘文存档 ──────────────────────────────────

    async def save_review_report(
        self,
        *,
        user_id: str,
        trade_date: str,
        content: str,
        status: str,
        llm_metadata: dict[str, Any] | None = None,
    ) -> str:
        """保存复盘文到 review_reports 表，返回生成的 report_id。"""
        ...

    # ── 写侧：观察池 ──────────────────────────────────

    async def add_watchlist_stock(
        self, *, stock: Any
    ) -> None:
        """upsert 一只股票到 watchlist_stocks 表。"""
        ...

    async def remove_watchlist_stock(self, *, stock_code: str) -> int:
        """从 watchlist_stocks 表删除指定 stock_code；返回受影响行数。"""
        ...

    # ── 读侧：复盘文查询 ──────────────────────────────────

    async def select_review_report(
        self, *, report_id: str, user_id: str
    ) -> ReviewReport | None:
        """按 (report_id, user_id) 查询复盘文；不存在或所有权不匹配返回 None。"""
        ...

    async def select_review_reports(
        self, *, user_id: str, limit: int
    ) -> list[ReviewReport]:
        """列出某 user 的复盘文（按 trade_date DESC），限长。"""
        ...
