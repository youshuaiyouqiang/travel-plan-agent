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
