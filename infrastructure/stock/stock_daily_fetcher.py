"""stock_daily_fetcher 模块——个股 K 线单日数据抓取。

设计要点（与 sector_daily_fetcher 同构，AGENTS.md §8.1 端口先于实现）：
- 复用 infrastructure.stock.akshare_client.fetch_stock_daily 拉单只股 K 线
- 数据源来自"同日" limit_stocks_daily（限同交易日涨停股，避免 N+1 akshare）
- 失败时包装为 AkshareFetchError，fetcher 捕获后 log warning 返回 0
- 仅用于"写路径"——不读缓存（除读 limit_stocks_daily 取股代码列表）

边界：
- 复盘 Service 不得直接 import 此模块；只能通过 StockDataSource 端口读缓存
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol

from domain.stock.models import StockDaily
from infrastructure.stock.akshare_client import AkshareFetchError

logger = logging.getLogger(__name__)


class _StockFetcherRepo(Protocol):
    """fetcher 运行时依赖（duck-type）。"""

    def select_limit_stocks(self, trade_date: str) -> list[Any]: ...
    def upsert_stock_daily(
        self, *, trade_date: str, rows: list[StockDaily]
    ) -> None: ...


async def run(trade_date: str, repo: _StockFetcherRepo) -> int:
    """抓取当日涨停股的 K 线并写入缓存。

    流程：
    1. 读 limit_stocks_daily(trade_date) → 涨停股代码列表
    2. 对每只股调 ``fetch_stock_daily(stock_code, trade_date)`` 拉 K 线
    3. 过滤出 ``trade_date`` 当日行，写入 stock_daily

    Args:
        trade_date: 交易日期（YYYYMMDD）。
        repo: 缓存仓储（duck-type 需具备 ``select_limit_stocks`` 和
            ``upsert_stock_daily`` 方法）。

    Returns:
        写入条数（涨停股数）；无涨停股 / 全部 akshare 失败时返回 0。
    """
    limit_stocks = repo.select_limit_stocks(trade_date)
    if not limit_stocks:
        logger.info(
            "stock_daily_fetcher.run: trade_date=%s no limit_stocks; skip",
            trade_date,
        )
        return 0

    written = 0
    today_rows: list[StockDaily] = []
    for s in limit_stocks:
        stock_code = s.stock_code
        try:
            rows = await _fetch(stock_code, trade_date)
        except AkshareFetchError as e:
            logger.warning(
                "stock_daily_fetcher.run: code=%s err=%s",
                stock_code, e,
            )
            continue
        except Exception as e:  # noqa: BLE001 — 边界 catch-all
            logger.warning(
                "stock_daily_fetcher.run: code=%s unexpected err=%s",
                stock_code, e,
            )
            continue
        # 仅保留当 trade_date 的行（akshare 返多日 K 线，截取当日）
        today_row = next((r for r in rows if r.trade_date == trade_date), None)
        if today_row is None:
            continue
        today_rows.append(today_row)

    if not today_rows:
        return 0

    repo.upsert_stock_daily(trade_date=trade_date, rows=today_rows)
    written = len(today_rows)
    logger.info(
        "stock_daily_fetcher.run: trade_date=%s count=%d",
        trade_date, written,
    )
    return written


async def _fetch(stock_code: str, trade_date: str) -> list[StockDaily]:
    """懒加载 akshare_client 并调用 fetch_stock_daily。

    Task 17：用 ``asyncio.to_thread`` 包装同步 akshare 调用，避免阻塞事件循环。
    99 只股票 × ~1s 的同步 IO 不能拖垮 uvicorn 的 startup 事件循环。
    """
    from infrastructure.stock.akshare_client import fetch_stock_daily

    return await asyncio.to_thread(fetch_stock_daily, stock_code, trade_date)
