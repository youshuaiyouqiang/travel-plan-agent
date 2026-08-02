"""股票管线端口协议——供 application 层 pipeline 调用外部 fetcher。

设计要点（AGENTS.md §8.1 端口先于实现 + §8.3 禁止依赖方向）：
- Protocol 定义在 domain 层（aggregate 命名：stock_pipeline）
- infrastructure 层实现 Fetcher 协议；application 层只持有 Protocol
- 端口输入/输出类型由 domain 定义；不泄漏 akshare / SQLite 等细节

边界：
- ``application`` 不得 import ``infrastructure``（§8.3）
- 管线编排的"写路径"入口 fetcher 由组合根装配时通过 Fetcher 注入
"""

from __future__ import annotations

from typing import Any, Protocol


class CacheWritePort(Protocol):
    """缓存仓储写路径端口——pipeline 写入目标。"""

    def upsert_limit_stocks(
        self, *, trade_date: str, stocks: list[Any]
    ) -> None: ...

    # 读路径：stock_daily_fetcher / board_ladder_fetcher 需读当日涨停股列表
    # （fetcher 内部依赖 limit_stocks_daily 已写入的数据做聚合或逐股抓取）
    def select_limit_stocks(self, trade_date: str) -> list[Any]: ...

    # Task 13：大盘指数 fetcher 写路径（market_index_daily）
    def upsert_market_index(
        self, *, trade_date: str, indices: list[Any]
    ) -> None: ...

    # Task 12：情绪指标 fetcher 写路径（emotion_daily）
    # fetcher 一次写入一天一行（DTO 列表通常 1 个元素；扩展性预留多 segment）
    def upsert_emotion_daily(
        self, *, trade_date: str, rows: list[Any]
    ) -> None: ...

    # Task 14：板块日线 fetcher 写路径（sector_daily）
    # fetcher 一次写入一天多行（约 100+ 个板块，每板块一行）
    def upsert_sector_daily(
        self, *, trade_date: str, rows: list[Any]
    ) -> None: ...

    # Task A2：连板高度分层 fetcher 写路径（board_ladder_daily）
    # 由 limit_stocks_daily 聚合产生（无 akshare 调用），
    # 一次写入一天多行（每连板高度一条，约 1-10 条）
    def upsert_board_ladder(
        self, *, trade_date: str, rows: list[Any]
    ) -> None: ...


class Fetcher(Protocol):
    """Fetcher 端口——单次抓取+写入的执行单元。

    实现方在 infrastructure 层（如 LimitFetcherAdapter 包装
    limit_fetcher.run）。application 层 pipeline.run_morning /
    run_close 串行调用各 fetcher.run(trade_date, repo)。
    """

    name: str  # fetcher 名称（用于日志）

    async def run(self, *, trade_date: str, repo: CacheWritePort) -> int: ...


class CorrelationAnalyzer(Protocol):
    """庄股/抱团股相关性分析器端口——周复盘周五链式触发。"""

    name: str

    async def analyze(self, end_date: str, days: int) -> Any: ...


class AkshareClientPort(Protocol):
    """akshare 客户端端口——fetcher 需要 akshare 时通过此端口取数据。"""

    async def get_limit_stocks(self, trade_date: str) -> list[Any]: ...

    # Task 13：大盘指数 fetcher 通过此端口拉 3 个指数
    async def get_market_index(self, trade_date: str) -> list[Any]: ...

    # Task 12：情绪指标 fetcher 通过此端口拉市场活动统计
    # 返回的 DTO 由调用方（emotion_daily_fetcher）解析为 emotion_daily 字段
    async def fetch_emotion_daily(self, trade_date: str) -> Any: ...

    # Task 14：板块日线 fetcher 通过此端口拉所有板块涨跌幅
    # 返回的 list[SectorDaily] 由调用方（sector_daily_fetcher）直接写入 cache
    async def fetch_sector_daily(self, trade_date: str) -> list[Any]: ...

    # Task 15：个股 K 线 fetcher 通过此端口拉单只股的 K 线
    # 返回的 list[StockDaily] 由调用方（stock_daily_fetcher）写入选定 trade_date
    async def fetch_stock_daily(
        self, stock_code: str, trade_date: str
    ) -> list[Any]: ...
