"""BoardLadderFetcherAdapter——把 board_ladder_fetcher.run 适配为 Fetcher 协议。

设计要点（与 SectorDailyFetcherAdapter 同构，AGENTS.md §8.1）：
- domain/stock/pipeline_ports.Fetcher 协议的实现
- application 层 pipeline 通过 Fetcher 协议调用本适配器
- 本文件在 infrastructure 层；fetcher 内部不依赖 akshare（纯聚合）
"""

from __future__ import annotations

import logging

from domain.stock.pipeline_ports import CacheWritePort

logger = logging.getLogger(__name__)


class BoardLadderFetcherAdapter:
    """连板高度分层 fetcher 适配器——实现 Fetcher 协议。

    复用 infrastructure.stock.board_ladder_fetcher.run 的逻辑；
    从 limit_stocks_daily 聚合写入 board_ladder_daily 缓存。
    """

    name = "board_ladder_fetcher"

    def __init__(self, client: object | None = None) -> None:
        """构造适配器。

        Args:
            client: 保留参数为与其它 fetcher 适配器签名一致
                （本 fetcher 不调 akshare，client 不使用）。
        """
        self._client = client

    async def run(self, *, trade_date: str, repo: CacheWritePort) -> int:
        """从 limit_stocks_daily 聚合写入 board_ladder_daily。

        Args:
            trade_date: 交易日期（YYYYMMDD）。
            repo: 缓存仓储端口（实现 CacheWritePort + select_limit_stocks）。

        Returns:
            写入条数（连板高度档位数）；无涨停股时返回 0。
        """
        from infrastructure.stock.board_ladder_fetcher import run as fetcher_run

        return await fetcher_run(trade_date, repo)
