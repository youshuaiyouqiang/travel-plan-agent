"""emotion_daily_fetcher 模块——情绪指标单日数据抓取与加工。

设计要点（与 market_index_fetcher 同构，AGENTS.md §8.1 端口先于实现）：
- 复用 infrastructure.stock.akshare_client.fetch_emotion_daily 拉原始字段
  （Task E 扩展：含 adv/decl_count）
- 调用方需要传 limit_stocks_daily 已有数据（用于聚合 valid / broken_ratio /
  max_consecutive）；fetcher 通过 ``repo.select_limit_stocks`` 读取
- 调用方需要昨日 emotion_daily（用于算 volume_change_pct）；由
  SqliteStockDataSource.get_emotion_indicators_before 读取
- Task E 新增：调 fetch_top20_volume_stocks（强度维度）+
  get_emotion_indicators_trend（高度/持续性维度）+
  select_stock_daily（韧性维度）
- 失败时包装为 AkshareFetchError，fetcher 捕获后 log warning 返回 0
- 仅用于"写路径"——不读缓存（除必要的 limit_stocks_daily + 昨日 emotion_daily +
  历史趋势 + 今日 stock_daily）

边界：
- 复盘 Service 不得直接 import 此模块；只能通过 StockDataSource 端口读缓存
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol

from domain.stock.emotion_dimensions import (
    compute_authenticity_level,
    compute_breadth_level,
    compute_height_level,
    compute_limit_up_percentile,
    compute_market_style,
    compute_rebound_success_ratio,
    compute_resilience_level,
    compute_strength_level,
    compute_trend,
)
from domain.stock.heuristics import (
    calculate_broken_limit_ratio,
    count_valid_limit_ups,
    max_consecutive_boards,
)
from domain.stock.models import EmotionIndicators, EmotionRawData, StockDaily, Top20VolumeSnapshot
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

    # Task E：6 维度计算所需的历史数据
    async def get_emotion_indicators_trend(
        self, end_date: str, days: int
    ) -> list[EmotionIndicators]: ...

    def select_stock_daily(self, trade_date: str) -> list[StockDaily]: ...


async def run(trade_date: str, deps: _FetcherDeps) -> int:
    """抓取并加工指定日的 emotion_daily 指标，写入缓存。

    流程：
    1. 调 ``fetch_emotion_daily`` 拉原始字段（akshare）— 含 adv/decl_count
    2. 读 ``limit_stocks_daily`` 该日行，聚合 valid_count / max_boards
    3. 用 heuristics 算 broken_limit_ratio
    4. 读昨日 emotion_daily.total_volume 算 volume_change_pct
    5. Task E：调 ``fetch_top20_volume_stocks`` 拉强度数据
    6. Task E：读历史 emotion_daily 趋势算 height_level / trend_5d / trend_20d
    7. Task E：读今日 stock_daily 算韧性（断板反包）
    8. Task E：调 6 维度计算函数，填入 EmotionIndicators 的 18 个新字段
    9. 写入 emotion_daily（phase 3 字段留 None）

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
        # 修复：limit_up_count / broken_count / top_board_leaders 都跟着置默认
        db_limit_up_count = 0
        db_broken_count = 0
        top_board_leaders: list[str] = []
    else:
        valid_count = count_valid_limit_ups(limit_stocks)
        max_boards = max_consecutive_boards(limit_stocks)
        # 修复：原 fetcher 用 akshare 实时截面的"涨停"/"炸板"（不接日期，永远是今天）
        # 来算 broken_ratio，导致每个历史日的 limit_up_count / broken_count
        # 都被错写成"今日"。此处改用 limit_stocks_daily 聚合的真实值。
        db_limit_up_count = sum(
            1 for s in limit_stocks if s.limit_type == "up"
        )
        db_broken_count = sum(
            1 for s in limit_stocks if s.limit_type == "broken"
        )
        # 修复：max_consecutive_boards 对应股票代码列表（并列龙头都要列出）。
        top_board_leaders = sorted({
            s.stock_code
            for s in limit_stocks
            if s.consecutive_boards == max_boards and max_boards > 0
        })
    # 当 db 真实数据可计算时优先覆盖 akshare 实时截面（akshare 接口不接受日期，
    # 原写法对历史日天然失效）；db 一行都没有才退回 akshare。
    effective_limit_up_count = (
        db_limit_up_count if db_limit_up_count > 0 else raw.limit_up_count
    )
    effective_broken_count = (
        db_broken_count if (db_limit_up_count + db_broken_count) > 0
        else raw.broken_count
    )
    broken_ratio = calculate_broken_limit_ratio(
        effective_limit_up_count, effective_broken_count
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

    # ── Task E：6 维度情绪观察框架计算 ──────────────────────

    # 维度 2：广度（从 raw.adv_count/decl_count）
    breadth_level = compute_breadth_level(raw.adv_count, raw.decl_count)
    adv_decl_ratio: float | None = None
    if raw.decl_count > 0:
        adv_decl_ratio = raw.adv_count / raw.decl_count
    elif raw.adv_count > 0:
        adv_decl_ratio = 999.0  # 下跌为 0（全涨）

    # 维度 3：强度（从 fetch_top20_volume_stocks）
    # 失败时降级为 None，不影响其他维度
    top20_snapshot = await _fetch_top20(trade_date)
    strength_level: str | None = None
    market_style: str | None = None
    top20_avg_chg: float | None = None
    top20_up_count: int | None = None
    top20_limit_up_count: int | None = None
    if top20_snapshot is not None:
        top20_avg_chg = top20_snapshot.avg_chg
        top20_up_count = top20_snapshot.up_count
        top20_limit_up_count = top20_snapshot.limit_up_count
        strength_level = compute_strength_level(
            top20_snapshot.avg_chg, top20_snapshot.up_count
        )

    # 维度 1 + 6：高度 + 持续性（从历史 emotion_daily 趋势）
    # 取近 21 日（含今日可能已写入的重跑场景，过滤今日）
    history = await deps.get_emotion_indicators_trend(trade_date, 21)
    history_excl_today = [h for h in history if h.trade_date != trade_date]
    # history 是 DESC（新→旧），compute_trend 需要 ASC（旧→新）
    history_asc = list(reversed(history_excl_today))

    # 高度：基于近 20 日涨停数分位数
    history_limit_ups = [h.limit_up_count for h in history_asc]
    percentile = compute_limit_up_percentile(
        raw.limit_up_count, history_limit_ups
    )
    height_level = compute_height_level(percentile)

    # 强度 + 高度组合 → 市场风格
    if strength_level is not None:
        market_style = compute_market_style(strength_level, height_level)

    # 持续性：近 5 日 / 20 日涨停数趋势
    trend_5d = compute_trend(
        [h.limit_up_count for h in history_asc[:5]]
    )
    trend_20d = compute_trend(
        [h.limit_up_count for h in history_asc[:20]]
    )

    # 维度 5：真实度（从 broken_limit_ratio）
    authenticity_level = compute_authenticity_level(broken_ratio)

    # 维度 4：韧性（断板反包——需昨日 limit_stocks + 今日 stock_daily）
    # 降级策略：昨日数据缺失或 stock_daily 为空时，韧性字段保持 None
    resilience_result = _compute_resilience(
        trade_date, yesterday, deps
    )

    # yesterday_limit_up_today_premium 暂留 None
    # （需 stock_daily fetcher 完成后基于个股 K 线计算）
    row = EmotionIndicators(
        trade_date=raw.trade_date,
        # 修复：优先用 limit_stocks_daily 聚合的真实涨停数，akshare 实时截面
        # 不接日期，对历史日天然失效。
        limit_up_count=effective_limit_up_count,
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
        # 修复：把"最高板龙头"股票代码填入 DTO，前端可单独列表展示
        top_board_leaders=top_board_leaders,
        # Task E v023：6 维度字段
        adv_count=raw.adv_count,
        decl_count=raw.decl_count,
        adv_decl_ratio=adv_decl_ratio,
        breadth_level=breadth_level,
        top20_volume_avg_chg=top20_avg_chg,
        top20_volume_up_count=top20_up_count,
        top20_volume_limit_up_count=top20_limit_up_count,
        strength_level=strength_level,
        market_style=market_style,
        board_break_total_count=resilience_result["board_break_total_count"],
        board_break_rebound_count=resilience_result["board_break_rebound_count"],
        rebound_success_ratio=resilience_result["rebound_success_ratio"],
        top5d_avg_chg=None,  # 需 5 日个股 K 线，暂不计算
        resilience_level=resilience_result["resilience_level"],
        authenticity_level=authenticity_level,
        height_level=height_level,
        trend_5d=trend_5d,
        trend_20d=trend_20d,
    )
    deps.upsert_emotion_daily(trade_date=trade_date, rows=[row])
    logger.info(
        "emotion_daily_fetcher.run: trade_date=%s limit_up=%d valid=%d "
        "max_boards=%d leaders=%s total_volume=%s height=%s breadth=%s "
        "strength=%s resilience=%s authenticity=%s trend_5d=%s "
        "trend_20d=%s style=%s",
        trade_date, effective_limit_up_count, valid_count, max_boards,
        top_board_leaders,
        raw.total_volume, height_level, breadth_level, strength_level,
        resilience_result["resilience_level"], authenticity_level,
        trend_5d, trend_20d, market_style,
    )
    return 1


def _compute_resilience(
    trade_date: str,
    yesterday: EmotionIndicators | None,
    deps: _FetcherDeps,
) -> dict[str, Any]:
    """计算维度 4 韧性（断板反包）。

    需要：
    - 昨日 limit_stocks（找昨日涨停股代码）
    - 今日 stock_daily（检查这些股今日是否断板/反包）

    降级策略：
    - 昨日数据缺失 → 全部 None
    - 今日 stock_daily 为空 → 全部 None
    - 部分代码不在 stock_daily 中 → 只统计能查到的

    Args:
        trade_date: 今日交易日。
        yesterday: 昨日 EmotionIndicators（含 trade_date 用于查 limit_stocks）。
        deps: 依赖（用于 select_limit_stocks + select_stock_daily）。

    Returns:
        包含 board_break_total_count / board_break_rebound_count /
        rebound_success_ratio / resilience_level 的字典（值可能为 None）。
    """
    result: dict[str, Any] = {
        "board_break_total_count": None,
        "board_break_rebound_count": None,
        "rebound_success_ratio": None,
        "resilience_level": None,
    }
    if yesterday is None:
        return result

    # 昨日涨停股代码
    yesterday_limit_stocks = deps.select_limit_stocks(yesterday.trade_date)
    if not yesterday_limit_stocks:
        return result

    yesterday_codes = {
        s.stock_code for s in yesterday_limit_stocks if s.limit_type == "up"
    }
    if not yesterday_codes:
        return result

    # 今日 stock_daily（检查断板/反包）
    today_stock_daily = deps.select_stock_daily(trade_date)
    if not today_stock_daily:
        return result

    # 构建 code → pct_chg 映射
    today_chg_map: dict[str, float | None] = {
        s.stock_code: s.pct_chg for s in today_stock_daily
    }

    # 断板股：昨日涨停今日未涨停（pct_chg < 9.8 或无数据）
    board_break_total = 0
    board_break_rebound = 0
    for code in yesterday_codes:
        chg = today_chg_map.get(code)
        if chg is None:
            # 今日无 K 线数据（可能停牌或未抓到）→ 视为断板
            board_break_total += 1
            continue
        if chg < 9.8:
            # 断板（今日未涨停）
            board_break_total += 1
            if chg > 5.0:
                # 反包成功（涨幅 > 5% 但 < 9.8）
                board_break_rebound += 1

    if board_break_total == 0:
        # 昨日涨停股今日全部继续涨停 → 无断板
        result["board_break_total_count"] = 0
        result["board_break_rebound_count"] = 0
        result["rebound_success_ratio"] = None
        result["resilience_level"] = "无断板"
        return result

    rebound_ratio = compute_rebound_success_ratio(
        board_break_total, board_break_rebound
    )
    result["board_break_total_count"] = board_break_total
    result["board_break_rebound_count"] = board_break_rebound
    result["rebound_success_ratio"] = rebound_ratio
    result["resilience_level"] = compute_resilience_level(
        board_break_total, board_break_rebound
    )
    return result


async def _fetch(trade_date: str) -> EmotionRawData:
    """懒加载 akshare_client 并调用 fetch_emotion_daily。

    Task 17：用 ``asyncio.to_thread`` 包装同步 akshare 调用，避免阻塞事件循环。
    """
    from infrastructure.stock.akshare_client import fetch_emotion_daily

    return await asyncio.to_thread(fetch_emotion_daily, trade_date)


async def _fetch_top20(trade_date: str) -> Top20VolumeSnapshot | None:
    """拉成交额前 20 强度数据（维度 3）。

    失败时降级返回 None（不影响其他维度计算）。
    用 ``asyncio.to_thread`` 包装同步 akshare 调用。
    """
    try:
        from infrastructure.stock.akshare_client import fetch_top20_volume_stocks

        return await asyncio.to_thread(fetch_top20_volume_stocks)
    except AkshareFetchError as e:
        logger.warning(
            "emotion_daily_fetcher._fetch_top20: trade_date=%s err=%s",
            trade_date, e,
        )
        return None
    except Exception as e:  # noqa: BLE001 — 边界 catch-all
        logger.warning(
            "emotion_daily_fetcher._fetch_top20: unexpected err trade_date=%s err=%s",
            trade_date, e,
        )
        return None
