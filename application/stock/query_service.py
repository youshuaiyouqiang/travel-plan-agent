"""股票读侧查询服务——封装 StockDataSource 端口供 API 调用。

设计要点（AGENTS.md §8.3 application 不得 import infrastructure）：
- 构造函数依赖注入 ``data_source``（满足 ``StockDataSource`` 协议）
- API 层不直接持有 data_source 端口；通过本服务调用
- 每个方法捕获具体异常并保留异常链（AGENTS.md §5）
- 不做缓存（缓存由 cache_repository 写侧负责；读侧直连端口）
"""

from __future__ import annotations

import logging

from domain.stock.ports import StockDataSource

logger = logging.getLogger(__name__)


class StockQueryService:
    """股票读侧查询服务——大盘/情绪/板块/观察池/信号。"""

    def __init__(self, data_source: StockDataSource) -> None:
        """构造查询服务。

        Args:
            data_source: 实现 ``StockDataSource`` 协议的数据源（只读缓存）。
        """
        self._data = data_source

    async def get_market_snapshot(self, trade_date: str):
        """拉取大盘快照。"""
        try:
            return await self._data.get_market_snapshot(trade_date)
        except Exception as e:
            logger.error("get_market_snapshot failed date=%s: %s", trade_date, e)
            raise

    async def get_emotion_trend(self, end_date: str, days: int = 10):
        """拉取情绪多日趋势。"""
        if days <= 0 or days > 60:
            days = 10
        try:
            return await self._data.get_emotion_indicators_trend(end_date, days)
        except Exception as e:
            logger.error(
                "get_emotion_trend failed end_date=%s days=%d: %s",
                end_date,
                days,
                e,
            )
            raise

    async def get_sector_chart(self, end_date: str, days: int = 10):
        """拉取板块多日表现（多日序列）。"""
        if days <= 0 or days > 60:
            days = 10
        try:
            return await self._data.get_sector_history("", days)  # 全板块
        except Exception as e:
            logger.error(
                "get_sector_chart failed end_date=%s days=%d: %s",
                end_date,
                days,
                e,
            )
            raise

    async def get_watchlist_chart(self, end_date: str, days: int = 10):
        """拉取观察池多日趋势。"""
        try:
            watchlist = await self._data.get_watchlist()
            return watchlist
        except Exception as e:
            logger.error("get_watchlist_chart failed: %s", e)
            raise

    async def get_watchlist(self):
        """拉取当前观察池（活跃股票）。"""
        try:
            return await self._data.get_watchlist()
        except Exception as e:
            logger.error("get_watchlist failed: %s", e)
            raise

    async def get_signal_stocks(self, trade_date: str):
        """拉取新信号股。"""
        try:
            return await self._data.get_signal_stocks(trade_date)
        except Exception as e:
            logger.error("get_signal_stocks failed: %s", e)
            raise

    async def get_sector_rotation(self, trade_date: str):
        """拉取板块轮动表现。"""
        try:
            return await self._data.get_sector_rotation(trade_date)
        except Exception as e:
            logger.error("get_sector_rotation failed: %s", e)
            raise

    async def get_sector_leaders(self, sector_name: str):
        """拉取板块龙头。"""
        try:
            return await self._data.get_sector_leaders(sector_name)
        except Exception as e:
            logger.error("get_sector_leaders failed sector=%s: %s", sector_name, e)
            raise
