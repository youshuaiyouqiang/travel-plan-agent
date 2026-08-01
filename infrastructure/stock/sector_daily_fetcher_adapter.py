"""SectorDailyFetcherAdapter——把 sector_daily_fetcher.run 适配为 Fetcher 协议。

设计要点（与 MarketIndexFetcherAdapter 同构，AGENTS.md §8.1）：
- domain/stock/pipeline_ports.Fetcher 协议的实现
- application 层 pipeline 通过 Fetcher 协议调用本适配器
- 本文件在 infrastructure 层，可自由 import akshare / sqlite3
"""

from __future__ import annotations

import logging

from domain.stock.pipeline_ports import CacheWritePort

logger = logging.getLogger(__name__)


class SectorDailyFetcherAdapter:
    """板块日线 fetcher 适配器——实现 Fetcher 协议。

    复用 infrastructure.stock.sector_daily_fetcher.run 的逻辑；
    通过 akshare 拉数据，缓存到 CacheWritePort。
    """

    name = "sector_daily_fetcher"

    def __init__(self, client: object | None = None) -> None:
        """构造适配器。

        Args:
            client: 实现 AkshareClientPort 协议的 akshare 客户端。
                当前 fetcher 内部 lazy load 默认客户端，传 None 即可。
                保留参数为后续单测注入 fake 客户端留口子。
        """
        self._client = client

    async def run(self, *, trade_date: str, repo: CacheWritePort) -> int:
        """抓取所有板块的当日涨跌幅并写入缓存。

        Args:
            trade_date: 交易日期（YYYYMMDD）。
            repo: 缓存仓储端口（实现 CacheWritePort）。

        Returns:
            写入条数（板块数）；akshare 失败时返回 0。
        """
        from infrastructure.stock.sector_daily_fetcher import run as fetcher_run

        return await fetcher_run(trade_date, repo)
