"""market_index_fetcher 模块——大盘指数单日数据抓取。

设计要点（与 limit_fetcher 同构，AGENTS.md §8.1 端口先于实现）：
- 复用 infrastructure.stock.akshare_client.fetch_market_index 拉数据
- 失败时包装为 AkshareFetchError，fetcher 捕获后 log warning 返回 0
- 仅用于"写路径"——不读缓存

边界：
- 复盘 Service 不得直接 import 此模块；只能通过 StockDataSource 端口读缓存
"""

from __future__ import annotations

import logging
from typing import Any

from domain.stock.models import MarketIndexRow
from infrastructure.stock.akshare_client import AkshareFetchError

logger = logging.getLogger(__name__)


async def run(trade_date: str, repo: Any) -> int:
    """抓取 3 个大盘指数（上证/深证/创业板）单日行并写入缓存。

    Args:
        trade_date: 交易日期（YYYYMMDD）。
        repo: 缓存仓储（duck-type 需具备 ``upsert_market_index`` 方法）。

    Returns:
        写入条数；akshare 失败时返回 0。
    """
    try:
        rows: list[MarketIndexRow] = await _fetch(trade_date)
    except AkshareFetchError as e:
        logger.warning(
            "market_index_fetcher.run: trade_date=%s err=%s",
            trade_date, e,
        )
        return 0
    except Exception as e:  # noqa: BLE001 — 边界 catch-all
        logger.warning(
            "market_index_fetcher.run: unexpected error trade_date=%s err=%s",
            trade_date, e,
        )
        return 0

    if not rows:
        logger.info(
            "market_index_fetcher.run: trade_date=%s no rows",
            trade_date,
        )
        return 0

    repo.upsert_market_index(trade_date=trade_date, indices=rows)
    logger.info(
        "market_index_fetcher.run: trade_date=%s count=%d",
        trade_date, len(rows),
    )
    return len(rows)


async def _fetch(trade_date: str) -> list[MarketIndexRow]:
    """懒加载 akshare_client 并调用 fetch_market_index。"""
    from infrastructure.stock.akshare_client import fetch_market_index

    return fetch_market_index(trade_date)
