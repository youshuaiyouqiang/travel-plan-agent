"""emotion_daily_fetcher 模块——情绪指标单日数据抓取与加工。

设计要点（与 market_index_fetcher 同构，AGENTS.md §8.1 端口先于实现）：
- 复用 infrastructure.stock.akshare_client.fetch_emotion_daily 拉原始 5 字段
- 调用方需要传 limit_stocks_daily 已有数据（用于聚合 valid / broken_ratio /
  max_consecutive）；fetcher 通过 ``repo.select_limit_stocks`` 读取
- 调用方需要昨日 emotion_daily（用于算 volume_change_pct）；由
  SqliteStockDataSource.get_emotion_indicators_before 读取
- 失败时包装为 AkshareFetchError，fetcher 捕获后 log warning 返回 0
- 仅用于"写路径"——不读缓存（除必要的 limit_stocks_daily + 昨日 emotion_daily）

边界：
- 复盘 Service 不得直接 import 此模块；只能通过 StockDataSource 端口读缓存
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol

from domain.stock.heuristics import (
    calculate_broken_limit_ratio,
    count_valid_limit_ups,
    max_consecutive_boards,
)
from domain.stock.models import EmotionIndicators, EmotionRawData
from infrastructure.stock.akshare_client import AkshareFetchError

logger = logging.getLogger(__name__)


class _FetcherDeps(Protocol):
    """fetcher 运行时依赖（duck-type）— repo + data_source。"""

    def select_limit_stocks(self, trade_date: str) -> list[Any]: ...
    def upsert_emotion_daily(
        self, *, trade_date: str, rows: list[EmotionIndicators]
    ) -> None: ...

    async def get_emotion_indicators_before(
        self, trade_date: str
    ) -> EmotionIndicators | None: ...


async def run(trade_date: str, deps: _FetcherDeps) -> int:
    """抓取并加工指定日的 emotion_daily 指标，写入缓存。

    流程：
    1. 调 ``fetch_emotion_daily`` 拉原始 5 字段（akshare）
    2. 读 ``limit_stocks_daily`` 该日行，聚合 valid_count / max_boards
    3. 用 heuristics 算 broken_limit_ratio
    4. 读昨日 emotion_daily.total_volume 算 volume_change_pct
    5. 写入 emotion_daily（phase 3 字段留 None，留给 LLM 后置回填）

    Args:
        trade_date: 交易日期（YYYYMMDD）。
        deps: 依赖（必须满足 ``_FetcherDeps`` 协议）。

    Returns:
        写入条数（恒为 1 或 0）；akshare 失败 / 无 limit_stocks_daily 数据时返回 0。
    """
    try:
        raw: EmotionRawData = await _fetch(trade_date)
    except AkshareFetchError as e:
        logger.warning(
            "emotion_daily_fetcher.run: trade_date=%s err=%s",
            trade_date, e,
        )
        return 0
    except Exception as e:  # noqa: BLE001 — 边界 catch-all
        logger.warning(
            "emotion_daily_fetcher.run: unexpected error trade_date=%s err=%s",
            trade_date, e,
        )
        return 0

    # 二次加工：valid_count / max_boards（来自 limit_stocks_daily）
    # Task B：limit_stocks 为空（涨停数为 0 的冰点期）时仍写入——
    # 涨停数为 0 是有效数据（情绪冰点期），原代码直接 return 0 导致
    # 该日完全不写入 emotion_daily，复盘文无法判定冰点期
    limit_stocks = deps.select_limit_stocks(trade_date)
    if not limit_stocks:
        # 涨停股池为空 → valid_count=0, max_boards=0（冰点期）
        logger.info(
            "emotion_daily_fetcher.run: trade_date=%s no limit_stocks; "
            "write as ice_phase (valid=0, max_boards=0)",
            trade_date,
        )
        valid_count = 0
        max_boards = 0
    else:
        valid_count = count_valid_limit_ups(limit_stocks)
        max_boards = max_consecutive_boards(limit_stocks)
    broken_ratio = calculate_broken_limit_ratio(
        raw.limit_up_count, raw.broken_count
    )

    # 衍生字段：volume_change_pct（需昨日 emotion_daily）
    # Task B：当日或前日 total_volume=None 时 volume_change_pct=None
    yesterday = await deps.get_emotion_indicators_before(trade_date)
    volume_change_pct: float | None = None
    if (
        yesterday is not None
        and yesterday.total_volume is not None
        and yesterday.total_volume > 0
        and raw.total_volume is not None
    ):
        volume_change_pct = (
            (raw.total_volume - yesterday.total_volume) / yesterday.total_volume
        )

    # yesterday_limit_up_today_premium 暂留 None
    # （需 stock_daily fetcher 完成后基于个股 K 线计算）
    row = EmotionIndicators(
        trade_date=raw.trade_date,
        limit_up_count=raw.limit_up_count,
        limit_down_count=raw.limit_down_count,
        valid_limit_up_count=valid_count,
        broken_limit_ratio=broken_ratio,
        max_consecutive_boards=max_boards,
        yesterday_limit_up_today_premium=None,
        total_volume=raw.total_volume,
        volume_change_pct=volume_change_pct,
        phase=None,
        phase_confidence=None,
        phase_reason=None,
    )
    deps.upsert_emotion_daily(trade_date=trade_date, rows=[row])
    logger.info(
        "emotion_daily_fetcher.run: trade_date=%s limit_up=%d valid=%d max_boards=%d total_volume=%s",
        trade_date, raw.limit_up_count, valid_count, max_boards, raw.total_volume,
    )
    return 1


async def _fetch(trade_date: str) -> EmotionRawData:
    """懒加载 akshare_client 并调用 fetch_emotion_daily。

    Task 17：用 ``asyncio.to_thread`` 包装同步 akshare 调用，避免阻塞事件循环。
    """
    from infrastructure.stock.akshare_client import fetch_emotion_daily

    return await asyncio.to_thread(fetch_emotion_daily, trade_date)
