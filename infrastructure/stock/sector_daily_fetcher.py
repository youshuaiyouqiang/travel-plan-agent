"""sector_daily_fetcher 模块——板块日线单日数据抓取。

设计要点（与 market_index_fetcher 同构，AGENTS.md §8.1 端口先于实现）：
- 复用 infrastructure.stock.akshare_client.fetch_sector_daily 拉数据
- 失败时包装为 AkshareFetchError，fetcher 捕获后 log warning 返回 0
- 仅用于"写路径"——不读缓存

边界：
- 复盘 Service 不得直接 import 此模块；只能通过 StockDataSource 端口读缓存
"""

from __future__ import annotations

import logging
from typing import Protocol

from domain.stock.models import SectorDaily
from infrastructure.stock.akshare_client import AkshareFetchError

logger = logging.getLogger(__name__)


class _SectorFetcherRepo(Protocol):
    """fetcher 运行时依赖（duck-type）— 只用写方法。"""

    def upsert_sector_daily(
        self, *, trade_date: str, rows: list[SectorDaily]
    ) -> None: ...


async def run(trade_date: str, repo: _SectorFetcherRepo) -> int:
    """抓取所有板块的当日涨跌幅并写入缓存。

    Args:
        trade_date: 交易日期（YYYYMMDD）。
        repo: 缓存仓储（duck-type 需具备 ``upsert_sector_daily`` 方法）。

    Returns:
        写入条数（板块数，约 100+）；akshare 失败 / 空数据时返回 0。
    """
    try:
        rows: list[SectorDaily] = await _fetch(trade_date)
    except AkshareFetchError as e:
        logger.warning(
            "sector_daily_fetcher.run: trade_date=%s err=%s",
            trade_date, e,
        )
        return 0
    except Exception as e:  # noqa: BLE001 — 边界 catch-all
        logger.warning(
            "sector_daily_fetcher.run: unexpected error trade_date=%s err=%s",
            trade_date, e,
        )
        return 0

    if not rows:
        logger.info(
            "sector_daily_fetcher.run: trade_date=%s no rows",
            trade_date,
        )
        return 0

    repo.upsert_sector_daily(trade_date=trade_date, rows=rows)
    logger.info(
        "sector_daily_fetcher.run: trade_date=%s count=%d",
        trade_date, len(rows),
    )
    return len(rows)


async def _fetch(trade_date: str) -> list[SectorDaily]:
    """懒加载 akshare_client 并调用 fetch_sector_daily。"""
    from infrastructure.stock.akshare_client import fetch_sector_daily

    return fetch_sector_daily(trade_date)
