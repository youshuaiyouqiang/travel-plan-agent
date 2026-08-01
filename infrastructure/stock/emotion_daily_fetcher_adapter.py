"""EmotionDailyFetcherAdapter——把 emotion_daily_fetcher.run 适配为 Fetcher 协议。

设计要点（与 MarketIndexFetcherAdapter 同构，AGENTS.md §8.1）：
- domain/stock/pipeline_ports.Fetcher 协议的实现
- application 层 pipeline 通过 Fetcher 协议调用本适配器
- 本文件在 infrastructure 层，可自由 import akshare / sqlite3

特殊性：
- emotion_daily_fetcher.run 需要除 CacheWritePort 之外的依赖
  （select_limit_stocks + get_emotion_indicators_before）
- 构造时注入 data_source（必须满足 StockDataSource 协议的相关方法）
- run 时把 (repo, data_source) 组合成 fetcher 的 _FetcherDeps
"""

from __future__ import annotations

import logging
from typing import Any

from domain.stock.pipeline_ports import CacheWritePort

logger = logging.getLogger(__name__)


class _FetcherDepsBundle:
    """把 repo + data_source 组合成 fetcher 期望的 deps。

    ``repo`` 实际是 ``CacheRepository``（具备 select_limit_stocks /
    upsert_emotion_daily 等方法），但 CacheWritePort 协议只声明了
    upsert_* 写方法，故此处的 repo 用 Any 避免 mypy 误报。
    """

    def __init__(self, repo: Any, data_source: Any) -> None:
        self._repo = repo
        self._data_source = data_source

    def select_limit_stocks(self, trade_date: str) -> list[Any]:
        return self._repo.select_limit_stocks(trade_date)  # type: ignore[attr-defined]

    def upsert_emotion_daily(
        self, *, trade_date: str, rows: list[Any]
    ) -> None:
        self._repo.upsert_emotion_daily(trade_date=trade_date, rows=rows)  # type: ignore[attr-defined]

    async def get_emotion_indicators_before(
        self, trade_date: str
    ) -> Any:
        return await self._data_source.get_emotion_indicators_before(trade_date)


class EmotionDailyFetcherAdapter:
    """情绪指标 fetcher 适配器——实现 Fetcher 协议。"""

    name = "emotion_daily_fetcher"

    def __init__(self, client: object | None = None, data_source: Any | None = None) -> None:
        """构造适配器。

        Args:
            client: 实现 AkshareClientPort 协议的 akshare 客户端。
                当前 fetcher 内部 lazy load 默认客户端，传 None 即可。
            data_source: 实现 StockDataSource 协议的数据源（用于读昨日
                emotion_daily）；必填。
        """
        self._client = client
        self._data_source = data_source

    async def run(self, *, trade_date: str, repo: CacheWritePort) -> int:
        """抓取并加工 emotion_daily 指标写入缓存。

        Args:
            trade_date: 交易日期（YYYYMMDD）。
            repo: 缓存仓储端口（实现 CacheWritePort）。

        Returns:
            写入条数（恒为 1 或 0）；akshare 失败 / 无 limit_stocks_daily 时返回 0。
        """
        from infrastructure.stock.emotion_daily_fetcher import run as fetcher_run

        deps = _FetcherDepsBundle(repo=repo, data_source=self._data_source)
        return await fetcher_run(trade_date, deps)
