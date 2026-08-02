"""股票数据源端口——领域层通过此端口访问数据，不直接 import akshare。

符合 AGENTS.md §8.1"端口先于实现"+ §2 "领域代码不得直接依赖具体 SDK"。
实现方可以是 akshare 客户端或测试 fake（tests/fixtures/stock.py）。
"""

from __future__ import annotations

from typing import Protocol

from domain.stock.models import (
    CorrelationResult,
    EmotionCycleSegment,
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
    async def get_emotion_cycles(
        self, end_date: str, lookback_days: int = 60
    ) -> list[EmotionCycleSegment]:
        """返回近 N 日的情绪周期段（峰谷检测，客观切分）。

        Task E：为 SKILL.md §三第 3 步"与上一轮退潮比"提供客观数据。
        不判定阶段方向——只提供峰/谷/首次修复日 + 涨停数，
        LLM 基于代码提供的周期段数据，对比"当前涨停数 vs 上一轮首次强修复涨停数"。

        Args:
            end_date: 截止交易日（YYYYMMDD）。
            lookback_days: 回看天数（默认 60）。

        Returns:
            EmotionCycleSegment 列表；历史数据不足或无峰谷模式时为空列表。
        """
        ...
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


class StockFetchLogPort(Protocol):
    """单股抓取日志端口（Task 20）——记录每只股每次抓取的状态。

    用途：
    - 写路径（fetcher）：每次抓取后 record_fetch 记录成功/失败
    - 读路径（fetcher 启动时）：is_recently_succeeded 判定是否跳过

    业务背景：
    - stock_daily_fetcher 对 99 只涨停股串行调 akshare，akshare 失败率
      高（1-2s/fail）→ 单日 warmup 容易只成功 80/99
    - 重启后若不查 log 会重抓全部 99 只；引入 TTL 内的 success 记录可
      让 fetcher 跳过已成功的 80 只，只重抓 19 只 → 节省 ~80% akshare
      调用，整体 warmup 从 ~3 分钟降到 ~36s

    边界（AGENTS.md §8.1）：
    - 端口输入/输出 DTO 由 domain 定义（trade_date / stock_code /
      table_name / status / within_seconds）；infrastructure 实现时
      不得暴露 SQLite / akshare 细节
    - 真实实现见 infrastructure.stock.cache_repository.CacheRepository
    - AkshareClient 复盘链路只读缓存，不调此端口

    Args/Returns 字段说明：
    - table_name: 当前仅 'stock_daily'；预留 multi-table 扩展
    - status: 'success' 或 'failed'（与 stock_fetch_log.status CHECK 对齐）
    - within_seconds: TTL 窗口（默认 24h = 86400s）
    """

    async def is_recently_succeeded(
        self,
        *,
        trade_date: str,
        stock_code: str,
        table_name: str,
        within_seconds: int,
    ) -> bool:
        """查询 (trade_date, stock_code, table_name) 是否在 TTL 内成功抓取。

        判定规则：
        - 无 log 行 → False（必须抓取）
        - status='failed' → False（即使在 TTL 内也允许重试）
        - status='success' 且 last_attempt_at 在 TTL 内 → True（跳过）
        - status='success' 但 last_attempt_at 超过 TTL → False（重抓）
        """

    async def record_fetch(
        self,
        *,
        trade_date: str,
        stock_code: str,
        table_name: str,
        status: str,
        error_message: str | None = None,
    ) -> None:
        """记录一次抓取结果（成功或失败）。

        行为：
        - INSERT OR REPLACE 语义：同 (date, code, table) 第二次写覆盖
        - status='success' 时 error_message 应为 None（清空旧错误）
        - last_attempt_at 自动取当前 UTC ISO8601 时间戳
        """
