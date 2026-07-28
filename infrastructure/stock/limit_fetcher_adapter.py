"""LimitFetcherAdapter——把 limit_fetcher.run 适配为 Fetcher 协议。

设计要点（AGENTS.md §8.1 端口先于实现）：
- domain/stock/pipeline_ports.Fetcher 协议的实现
- application 层 pipeline 通过 Fetcher 协议调用本适配器
- 本文件在 infrastructure 层，可自由 import akshare / sqlite3
"""

from __future__ import annotations

import logging

from domain.stock.pipeline_ports import AkshareClientPort, CacheWritePort

logger = logging.getLogger(__name__)


class LimitFetcherAdapter:
    """涨停股池 fetcher 适配器——实现 Fetcher 协议。

    复用 infrastructure.stock.limit_fetcher.run 的逻辑；
    通过 akshare 客户端拉数据，缓存到 CacheWritePort。
    """

    name = "limit_fetcher"

    def __init__(self, client: AkshareClientPort) -> None:
        """构造适配器。

        Args:
            client: 实现 AkshareClientPort 协议的 akshare 客户端。
        """
        self._client = client

    async def run(
        self, *, trade_date: str, repo: CacheWritePort
    ) -> int:
        """抓取涨停股池并写入缓存。

        Args:
            trade_date: 交易日期（YYYYMMDD）。
            repo: 缓存仓储端口（实现 CacheWritePort）。

        Returns:
            写入条数；akshare 失败时返回 0。
        """
        try:
            stocks = await self._client.get_limit_stocks(trade_date)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "LimitFetcherAdapter failed: trade_date=%s err=%s",
                trade_date,
                e,
            )
            return 0
        repo.upsert_limit_stocks(trade_date=trade_date, stocks=stocks)
        logger.info(
            "LimitFetcherAdapter done: trade_date=%s count=%d",
            trade_date,
            len(stocks),
        )
        return len(stocks)
