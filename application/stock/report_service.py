"""复盘文存档与查询服务。

设计要点（AGENTS.md §4 + §8 端口先于实现）：
- 构造依赖注入 ``cache_repo``（满足 ``CacheRepositoryPort`` 协议，
  共享于 ``application.stock.cache_repository_port``）
- 查询方法（get / list）严格做所有权判定；跨用户访问返回 None
  （API 层把 None 翻译为 404，符合"对象级未授权 = 404，不返回 403"红线）
- 列表默认按 trade_date DESC 排序
- 列表限长 100，避免拉取过大
"""

from __future__ import annotations

import logging

from application.stock.cache_repository_port import CacheRepositoryPort
from domain.stock.models import ReviewReport

logger = logging.getLogger(__name__)

_LIST_LIMIT_MAX = 100
_LIST_LIMIT_DEFAULT = 20


class ReportService:
    """复盘文存档/查询服务——应用层封装仓储端口。"""

    def __init__(self, cache_repo: CacheRepositoryPort) -> None:
        """构造服务。

        Args:
            cache_repo: 实现 ``CacheRepositoryPort`` 协议的仓储。
        """
        self._cache = cache_repo

    async def get_report(
        self, *, report_id: str, requester_id: str
    ) -> ReviewReport | None:
        """按 (report_id, requester_id) 查询复盘文。

        跨用户访问返回 None；API 层翻译为 404（不暴露存在性）。
        """
        if not report_id or not requester_id:
            return None
        try:
            return await self._cache.select_review_report(
                report_id=report_id, user_id=requester_id
            )
        except Exception as e:
            logger.error("get_report failed: %s", e)
            raise

    async def list_reports(
        self, *, requester_id: str, limit: int = _LIST_LIMIT_DEFAULT
    ) -> list[ReviewReport]:
        """列出某 user 的复盘文（按 trade_date DESC）。

        Args:
            requester_id: 当前用户 ID（所有权过滤）。
            limit: 返回上限（默认 20，上限 100）。

        Returns:
            ``ReviewReport`` DTO 列表；无数据时为空列表。
        """
        if not requester_id:
            return []
        bounded_limit = min(max(1, limit), _LIST_LIMIT_MAX)
        try:
            return await self._cache.select_review_reports(
                user_id=requester_id, limit=bounded_limit
            )
        except Exception as e:
            logger.error("list_reports failed: %s", e)
            raise
