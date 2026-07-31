"""股票数据源端口——领域层通过此端口访问数据，不直接 import akshare。

符合 AGENTS.md §8.1"端口先于实现"+ §2 "领域代码不得直接依赖具体 SDK"。
实现方可以是 akshare 客户端或测试 fake（tests/fixtures/stock.py）。
"""

from __future__ import annotations

from typing import Protocol

from domain.stock.models import (
    CorrelationResult,
    EmotionIndicators,
    MarketSnapshot,
    ResistantSector,
    SectorDaily,
    SectorDivergence,
    SectorHeatDistribution,
    SectorLeader,
    SectorPerformance,
    SignalStock,
    StockDaily,
    StrongRepairLeader,
    WatchlistStock,
    LimitStock,
)


class StockDataSource(Protocol):
    """股票数据源端口。"""

    async def get_market_snapshot(self, trade_date: str) -> MarketSnapshot: ...
    async def get_emotion_indicators(self, trade_date: str) -> EmotionIndicators: ...
    async def get_emotion_indicators_trend(
        self, end_date: str, days: int
    ) -> list[EmotionIndicators]: ...
    async def get_watchlist(self) -> list[WatchlistStock]: ...
    async def get_stock_daily(
        self, stock_code: str, days: int
    ) -> list[StockDaily]: ...
    async def get_signal_stocks(self, trade_date: str) -> list[SignalStock]: ...
    async def get_sector_rotation(self, trade_date: str) -> list[SectorPerformance]: ...
    async def get_sector_heat_distribution(
        self, trade_date: str
    ) -> list[SectorHeatDistribution]: ...
    async def get_strong_repair_leaders(self) -> list[StrongRepairLeader]: ...
    async def get_resistant_sectors(self, trade_date: str) -> list[ResistantSector]: ...
    async def get_sector_leaders(self, sector_name: str) -> list[SectorLeader]: ...
    async def get_sector_divergence(
        self, trade_date: str
    ) -> list[SectorDivergence]: ...
    async def get_correlation(
        self, end_date: str, days: int
    ) -> CorrelationResult: ...  # 周复盘专用
    async def get_sector_history(
        self, sector_name: str, days: int
    ) -> list[SectorDaily]: ...
    async def get_limit_stocks(self, trade_date: str) -> list[LimitStock]: ...
    # Task 10：启动期缓存回填的"是否已有数据"判定端口方法
    # SQL: SELECT 1 FROM limit_stocks_daily WHERE trade_date = ? LIMIT 1
    # 真实实现见 infrastructure.stock.sqlite_data_source.SqliteStockDataSource
    async def has_limit_stocks(self, trade_date: str) -> bool: ...
