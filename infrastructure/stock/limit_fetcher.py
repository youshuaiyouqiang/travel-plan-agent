"""涨停股池 fetcher——调用 akshare 写入 SQLite 缓存。

Task 3 写路径样本 fetcher。失败时不抛出（log warning + 返回 0），
确保调度器当日流程不被单点失败打断。

边界：
- 仅用于"写路径"，由调度器在交易日定时调用
- 不得被 review_service / application 层的任何代码直接 import
  （review_service 只能通过 StockDataSource 端口读缓存）
"""

from __future__ import annotations

import logging

from infrastructure.stock.akshare_client import AkshareFetchError, fetch_zt_pool
from infrastructure.stock.cache_repository import CacheRepository

logger = logging.getLogger(__name__)


async def run(trade_date: str, repo: CacheRepository) -> int:
    """抓取涨停股池并写入缓存。

    Args:
        trade_date: 交易日期（YYYYMMDD）。
        repo: 缓存仓储实例。

    Returns:
        写入条数。akshare 失败时返回 0，不抛出异常。
    """
    try:
        stocks = fetch_zt_pool(trade_date)
    except AkshareFetchError as e:
        logger.warning(
            "limit_fetcher failed: trade_date=%s err=%s", trade_date, e
        )
        return 0
    repo.upsert_limit_stocks(trade_date=trade_date, stocks=stocks)
    logger.info(
        "limit_fetcher done: trade_date=%s count=%d", trade_date, len(stocks)
    )
    return len(stocks)
