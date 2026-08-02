"""stock_daily_fetcher 模块——个股 K 线单日数据抓取。

设计要点（与 sector_daily_fetcher 同构，AGENTS.md §8.1 端口先于实现）：
- 复用 infrastructure.stock.akshare_client.fetch_stock_daily 拉单只股 K 线
- 数据源来自"同日" limit_stocks_daily（限同交易日涨停股，避免 N+1 akshare）
- 失败时包装为 AkshareFetchError，fetcher 捕获后 log warning 返回 0
- 仅用于"写路径"——不读缓存（除读 limit_stocks_daily 取股代码列表）

Task 20：
- 引入 stock_fetch_log（CacheRepository.record_fetch / is_recently_succeeded）
- 抓取前先查 log，若 TTL 内已 success 则跳过 akshare 调用
- 抓取后写 log（success / failed）
- 业务收益：99 股 80 已成功 → 重启后只重抓 19 只，warmup 耗时从
  ~3 分钟降到 ~36s（避免 akshare 高失败率拖累事件循环）

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


# TTL 默认值（秒）——24 小时内已成功的抓取视为有效，无需重抓
_DEFAULT_FETCH_LOG_TTL_SECONDS = 86400


class _StockFetcherRepo(Protocol):
    """fetcher 运行时依赖（duck-type）。"""

    def select_limit_stocks(self, trade_date: str) -> list[Any]: ...
    def upsert_stock_daily(
        self, *, trade_date: str, rows: list[StockDaily]
    ) -> None: ...
    # Task 20：单股抓取日志
    def record_fetch(
        self,
        *,
        trade_date: str,
        stock_code: str,
        table_name: str,
        status: str,
        error_message: str | None = None,
    ) -> None: ...
    def is_recently_succeeded(
        self,
        *,
        trade_date: str,
        stock_code: str,
        table_name: str,
        within_seconds: int,
    ) -> bool: ...


async def run(
    trade_date: str,
    repo: _StockFetcherRepo,
    *,
    fetch_log_ttl_seconds: int = _DEFAULT_FETCH_LOG_TTL_SECONDS,
) -> int:
    """抓取当日涨停股的 K 线并写入缓存。

    流程（Task 20 修订）：
    1. 读 limit_stocks_daily(trade_date) → 涨停股代码列表
    2. 对每只股先查 stock_fetch_log → TTL 内已 success 则跳过
    3. 否则调 ``fetch_stock_daily(stock_code, trade_date)`` 拉 K 线
    4. 过滤出 ``trade_date`` 当日行，写入 stock_daily
    5. 抓取成功/失败都更新 stock_fetch_log（供下次 warmup 复用）

    Args:
        trade_date: 交易日期（YYYYMMDD）。
        repo: 缓存仓储（duck-type 需具备 select_limit_stocks、
            upsert_stock_daily、record_fetch、is_recently_succeeded）。
        fetch_log_ttl_seconds: Task 20 新增。stock_fetch_log 中 success
            记录的 TTL 窗口（秒）；超过 TTL 视为失效，需重抓。
            默认 86400（24h）。设为 0 关闭 log 优化（每只都重抓）。

    Returns:
        写入条数（实际抓取且当日有 K 线的股数）；
        无涨停股 / 全部失败 / log 全 skip 时返回 0。
    """
    limit_stocks = repo.select_limit_stocks(trade_date)
    if not limit_stocks:
        logger.info(
            "stock_daily_fetcher.run: trade_date=%s no limit_stocks; skip",
            trade_date,
        )
        return 0

    # Task 20：TTL=0 表示关闭 log 优化（每只都重抓）
    log_enabled = fetch_log_ttl_seconds > 0

    written = 0
    skipped = 0
    failed = 0
    today_rows: list[StockDaily] = []
    total = len(limit_stocks)
    # 聚合进度：每抓完 10 只输出一次，避免每只都刷一行
    _progress_step = max(1, min(10, total // 10 or 1))
    for idx, s in enumerate(limit_stocks, start=1):
        stock_code = s.stock_code

        # Task 20：log 优化——TTL 内已 success → 跳过 akshare
        if log_enabled and repo.is_recently_succeeded(
            trade_date=trade_date,
            stock_code=stock_code,
            table_name="stock_daily",
            within_seconds=fetch_log_ttl_seconds,
        ):
            skipped += 1
            logger.debug(
                "stock_daily_fetcher: skip code=%s (log success within %ds)",
                stock_code, fetch_log_ttl_seconds,
            )
            continue

        try:
            rows = await _fetch(stock_code, trade_date)
        except AkshareFetchError as e:
            logger.warning(
                "stock_daily_fetcher.run: code=%s err=%s",
                stock_code, e,
            )
            failed += 1
            # Task 20：失败也记 log（status=failed），下次 warmup 允许重试
            if log_enabled:
                repo.record_fetch(
                    trade_date=trade_date,
                    stock_code=stock_code,
                    table_name="stock_daily",
                    status="failed",
                    error_message=str(e),
                )
            continue
        except Exception as e:  # noqa: BLE001 — 边界 catch-all
            logger.warning(
                "stock_daily_fetcher.run: code=%s unexpected err=%s",
                stock_code, e,
            )
            failed += 1
            if log_enabled:
                repo.record_fetch(
                    trade_date=trade_date,
                    stock_code=stock_code,
                    table_name="stock_daily",
                    status="failed",
                    error_message=str(e),
                )
            continue
        # 仅保留当 trade_date 的行（akshare 返多日 K 线，截取当日）
        today_row = next((r for r in rows if r.trade_date == trade_date), None)
        if today_row is None:
            # akshare 返回了多日但当日无行——视为软失败
            failed += 1
            if log_enabled:
                repo.record_fetch(
                    trade_date=trade_date,
                    stock_code=stock_code,
                    table_name="stock_daily",
                    status="failed",
                    error_message="akshare returned no row for trade_date",
                )
            continue
        today_rows.append(today_row)
        # Task 20：抓取成功记 log
        if log_enabled:
            repo.record_fetch(
                trade_date=trade_date,
                stock_code=stock_code,
                table_name="stock_daily",
                status="success",
            )
        # 聚合进度：每 _progress_step 只输出一次（避免每只刷一行）
        if idx % _progress_step == 0 or idx == total:
            logger.info(
                "stock_daily_fetcher progress: %d/%d (written=%d skipped=%d failed=%d)",
                idx, total, written, skipped, failed,
            )

    if today_rows:
        repo.upsert_stock_daily(trade_date=trade_date, rows=today_rows)
        written = len(today_rows)

    logger.info(
        "stock_daily_fetcher.run: trade_date=%s total=%d written=%d skipped=%d failed=%d",
        trade_date, total, written, skipped, failed,
    )
    return written


async def _fetch(stock_code: str, trade_date: str) -> list[StockDaily]:
    """懒加载 akshare_client 并调用 fetch_stock_daily。

    Task 17：用 ``asyncio.to_thread`` 包装同步 akshare 调用，避免阻塞事件循环。
    99 只股票 × ~1s 的同步 IO 不能拖垮 uvicorn 的 startup 事件循环。
    """
    from infrastructure.stock.akshare_client import fetch_stock_daily

    return await asyncio.to_thread(fetch_stock_daily, stock_code, trade_date)
