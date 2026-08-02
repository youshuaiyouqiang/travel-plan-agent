"""limit_broken_fetcher 模块——炸板股池 fetcher（独立于涨停 fetcher）。

设计要点（与 limit_fetcher 同构，AGENTS.md §3 / §6）：
- 调用 ``akshare.stock_zt_pool_dtgc_em(date=...)`` 拉炸板股池（接受日期参数）
- akshare 函数与 fetch_zt_pool 互补：
  - ``stock_zt_pool_em``：当日封死涨停股（含连板）
  - ``stock_zt_pool_dtgc_em``：当日封板后开板的炸板股
- 失败时包装为 AkshareFetchError，fetcher 捕获后 log warning + 返回 0
- 仅用于"写路径"——不读缓存
- 不得被 review_service / application 层直接 import
- 只能通过 Fetcher 协议注入 pipeline

边界：
- limit_stocks_daily 表 (trade_date, stock_code) 复合主键：upsert 语义为覆盖
- LimitStock.limit_type='broken'（与 'up' / 'down' 并列枚举）
"""
from __future__ import annotations

import logging

from infrastructure.stock.akshare_client import AkshareFetchError, fetch_zt_pool_dtgc

logger = logging.getLogger(__name__)


async def run(trade_date: str, repo) -> int:
    """抓取炸板股池并写入缓存。

    Args:
        trade_date: 交易日期（YYYYMMDD）。
        repo: 缓存仓储实例（满足 CacheWritePort 协议）。

    Returns:
        写入条数。akshare 失败时返回 0，不抛出异常。
    """
    try:
        stocks = fetch_zt_pool_dtgc(trade_date)
    except AkshareFetchError as e:
        logger.warning(
            "limit_broken_fetcher failed: trade_date=%s err=%s",
            trade_date, e,
        )
        return 0
    repo.upsert_limit_stocks(trade_date=trade_date, stocks=stocks)
    logger.info(
        "limit_broken_fetcher done: trade_date=%s count=%d",
        trade_date, len(stocks),
    )
    return len(stocks)
