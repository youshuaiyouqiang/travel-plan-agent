"""庄股/抱团股识别服务——周复盘专用。

业务红线（AGENTS.md §3 + 计划文档 §6）：
- 日复盘模式调用 → 抛 ``ConflictException``（HTTP 409 / code=CORRELATION_WEEKLY_ONLY）
- 缓存未就绪（individual_stocks + clustered_groups 都空）→ 抛
  ``ConflictException``（HTTP 409 / code=CORRELATION_NOT_READY）
- 跨用户访问由 API 层处理；本服务只暴露给合法调用方
- 仅读 SQLite 缓存（不直连 akshare，复盘链路不发起外部请求）
"""

from __future__ import annotations

import logging

from application.exceptions.conflict import ConflictException
from domain.stock.ports import StockDataSource

logger = logging.getLogger(__name__)


class CorrelationService:
    """庄股/抱团股识别服务（周复盘专用）。"""

    def __init__(self, data_source: StockDataSource) -> None:
        """构造服务。

        Args:
            data_source: 实现 ``StockDataSource`` 协议的数据源。
        """
        self._data = data_source

    async def get_weekly_correlation(
        self, *, end_date: str, days: int = 7, mode: str = "weekly"
    ):
        """拉取周复盘庄股/抱团识别结果。

        Args:
            end_date: 截止交易日（YYYYMMDD）。
            days: 回溯天数（默认 7）。
            mode: 复盘模式；只接受 "weekly"，其余 → 409。

        Returns:
            ``CorrelationResult`` DTO。

        Raises:
            ConflictException: 当 ``mode != "weekly"`` 或缓存未就绪时。
        """
        if mode != "weekly":
            logger.info("correlation rejected: mode=%s (only weekly allowed)", mode)
            raise ConflictException(
                "庄股/抱团股识别仅在周复盘可用",
                details={"code": "CORRELATION_WEEKLY_ONLY"},
            )

        try:
            result = await self._data.get_correlation(end_date, days)
        except Exception as e:
            logger.error("get_correlation failed: %s", e)
            raise

        if not result.individual_stocks and not result.clustered_groups:
            logger.info(
                "correlation not ready: end_date=%s days=%d", end_date, days
            )
            raise ConflictException(
                "周复盘相关性数据尚未就绪，请等待周五收盘后任务完成",
                details={"code": "CORRELATION_NOT_READY"},
            )

        return result
