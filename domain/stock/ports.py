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

    # Task 13：大盘指数数据回填"是否已有数据"判定端口方法
    # SQL: SELECT 1 FROM market_index_daily WHERE trade_date = ? LIMIT 1
    # 真实实现见 infrastructure.stock.sqlite_data_source.SqliteStockDataSource
    async def has_market_index(self, trade_date: str) -> bool: ...

    # Task 12：情绪指标数据回填"是否已有数据"判定端口方法
    # SQL: SELECT 1 FROM emotion_daily WHERE trade_date = ? LIMIT 1
    # 真实实现见 infrastructure.stock.sqlite_data_source.SqliteStockDataSource
    async def has_emotion_daily(self, trade_date: str) -> bool: ...

    # Task 14：板块日线数据回填"是否已有数据"判定端口方法
    # SQL: SELECT 1 FROM sector_daily WHERE trade_date = ? LIMIT 1
    # 真实实现见 infrastructure.stock.sqlite_data_source.SqliteStockDataSource
    async def has_sector_daily(self, trade_date: str) -> bool: ...

    # Task 15：个股 K 线数据回填"是否已有数据"判定端口方法
    # SQL: SELECT 1 FROM stock_daily WHERE trade_date = ? LIMIT 1
    # 真实实现见 infrastructure.stock.sqlite_data_source.SqliteStockDataSource
    async def has_stock_daily(self, trade_date: str) -> bool: ...

    # Task 18：非交易日复盘回退——查询缓存中最近一个有数据的交易日
    # SQL: SELECT MAX(trade_date) FROM market_index_daily
    # 取大盘指数表（最可靠的"当天有市"信号：每天 3 行=3 个指数）
    # 不取 limit_stocks_daily（可能为空：当日无涨停）
    # 不取 emotion_daily（fetcher 失败时也为空）
    # 返回 str（YYYYMMDD）或 None（缓存完全为空）
    # 真实实现见 infrastructure.stock.sqlite_data_source.SqliteStockDataSource
    async def get_latest_trade_date_with_data(self) -> str | None: ...

    # Task 19：行数对齐判定——避免"99 → 80"的部分缺失被永久化
    # SQL: SELECT COUNT(*) FROM limit_stocks_daily WHERE trade_date = ?
    # 返回该日 limit_stocks 表的实际行数（含未达涨停的失败/重抓等所有行）
    # 0 = 该日无涨停股或完全空；≥1 = 有 N 条记录
    # 真实实现见 infrastructure.stock.sqlite_data_source.SqliteStockDataSource
    async def count_limit_stocks(self, trade_date: str) -> int: ...

    # Task 19：行数对齐判定——stock_daily K 线行数
    # SQL: SELECT COUNT(*) FROM stock_daily WHERE trade_date = ?
    # 用于与 count_limit_stocks 比对：n_stock < n_limit 即"部分缺失"
    # 真实实现见 infrastructure.stock.sqlite_data_source.SqliteStockDataSource
    async def count_stock_daily(self, trade_date: str) -> int: ...
