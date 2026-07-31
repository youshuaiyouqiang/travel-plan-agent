"""Task 10 — 启动期股票缓存回填模块。

设计要点（AGENTS.md §3 业务边界 + §8.1 端口先于实现 + §8.3 禁止依赖方向）：

- application 层只 import domain + application，**不 import infrastructure**（§8.3 零容忍）
- pipeline 通过 ``get_default_pipeline()`` 取得（接缝 4，与 scheduler 同构）
- ``find_missing_limit_dates`` 是纯函数，便于单元测试
- ``run_stock_cache_warmup`` 内部 lazy load 交易日历；失败回退 weekday 过滤
- 单日 fetcher 失败 ``log warning`` 跳过；整体不抛异常
- 启动期 ``lifespan`` 通过 ``asyncio.create_task`` 调度，不阻塞 ready

业务边界（已知）：
- 当前 fetcher 只写入 ``limit_stocks_daily`` 一张表
- ``market_index_daily`` / ``emotion_daily`` / ``sector_daily`` 暂无 fetcher，
  属于独立工单（建议 Task 11+），本模块不做处理
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from domain.stock.ports import StockDataSource

logger = logging.getLogger(__name__)


# 窗口配置边界：与 get_emotion_indicators_trend 的 bounded_days 模式对齐
_WINDOW_MIN = 1
_WINDOW_MAX = 60


def _clamp_window(window_days: int) -> int:
    """将窗口天数 clamp 到 [_WINDOW_MIN, _WINDOW_MAX] 区间。

    配置错误时（0/负/超 60）兜底到合法值，避免 akshare 被无效请求打爆。
    """
    try:
        value = int(window_days)
    except (TypeError, ValueError):
        return _WINDOW_MIN
    if value < _WINDOW_MIN:
        return _WINDOW_MIN
    if value > _WINDOW_MAX:
        return _WINDOW_MAX
    return value


def _candidate_dates(today: date, window_days: int) -> list[date]:
    """生成 [today - window_days + 1, today] 区间内的所有日期（升序）。"""
    span = _clamp_window(window_days)
    return [today - timedelta(days=offset) for offset in range(span)]


def _format_yyyymmdd(d: date) -> str:
    """date → YYYYMMDD 字符串。"""
    return d.strftime("%Y%m%d")


def _is_weekday(d: date) -> bool:
    """判断 date 是否为工作日（Mon-Fri）。"""
    return d.weekday() < 5


async def find_missing_limit_dates(
    data_source: StockDataSource,
    *,
    window_days: int,
    today: date | None = None,
    trading_calendar: set[str] | None = None,
) -> list[str]:
    """查找最近 ``window_days`` 个交易日内 ``limit_stocks_daily`` 缺失的日期。

    判定规则：
    - 候选日期 = [today - window_days + 1, today] 区间，去除周末
    - 若 ``trading_calendar`` 非空，额外过滤（仅保留交易日历内的日期）
    - 候选日通过 ``data_source.has_limit_stocks`` 判定是否已存在
    - 缺失的日期按"由近及远"顺序返回（today 优先）

    Args:
        data_source: 满足 ``StockDataSource`` 协议的数据源。
        window_days: 回填窗口（自然日）；会被 clamp 到 [1, 60]。
        today: 测试注入用；``None`` 时取 ``date.today()``。
        trading_calendar: 可选交易日历（YYYYMMDD 集合）；``None`` 时仅按 weekday 过滤。

    Returns:
        YYYYMMDD 字符串列表，按"由近及远"排序。
    """
    effective_today = today or date.today()
    candidates = _candidate_dates(effective_today, window_days)

    # 周末过滤
    candidates = [d for d in candidates if _is_weekday(d)]

    # 交易日历过滤（可选）
    if trading_calendar:
        candidates = [
            d for d in candidates if _format_yyyymmdd(d) in trading_calendar
        ]

    # _candidate_dates 已按"由近及远"返回（today 优先），保持顺序
    # 检查每个候选日是否已有数据
    missing: list[str] = []
    for d in candidates:
        trade_date = _format_yyyymmdd(d)
        if not await data_source.has_limit_stocks(trade_date):
            missing.append(trade_date)
    return missing


async def _load_calendar_lazy() -> set[str]:
    """Lazy load 交易日历：调用 scheduler 已有实现；失败时返回空集合。

    Returns:
        交易日历（YYYYMMDD 集合）。失败时为空，调用方应回退 weekday 过滤。
    """
    try:
        from application import scheduler

        return await scheduler._load_trading_calendar()
    except Exception as e:  # noqa: BLE001 — 边界 catch-all
        logger.warning("warmup: failed to load trading calendar: %s", e)
        return set()


async def run_stock_cache_warmup(
    data_source: StockDataSource,
    *,
    window_days: int,
    today: date | None = None,
) -> int:
    """执行一次启动期股票缓存回填。

    Args:
        data_source: 满足 ``StockDataSource`` 协议的数据源（只读缓存）。
        window_days: 回填窗口（自然日）；会被 clamp 到 [1, 60]。
        today: 测试注入用；``None`` 时取 ``date.today()``。

    Returns:
        成功回填的日期数（fetcher 单日失败不计入）。pipeline 未注册时返回 0。
    """
    # Lazy load 交易日历；失败 / 仍空 → 回退 weekday 过滤
    calendar = await _load_calendar_lazy()
    if not calendar:
        # 明确给调用方一个信号：calendar 加载失败时的回退路径
        logger.info(
            "stock_warmup: trading calendar unavailable; "
            "falling back to weekday-only filtering"
        )

    missing = await find_missing_limit_dates(
        data_source,
        window_days=window_days,
        today=today,
        trading_calendar=calendar or None,
    )

    if not missing:
        logger.info(
            "stock_warmup: no missing dates in last %d days; skip",
            _clamp_window(window_days),
        )
        return 0

    # 取默认 pipeline；未注册（组合根未装配）时优雅降级
    from application.stock.pipeline import get_default_pipeline

    pipeline = get_default_pipeline()
    if pipeline is None:
        logger.warning(
            "stock_warmup: no default pipeline registered; "
            "%d missing dates will not be backfilled",
            len(missing),
        )
        return 0

    backfilled = 0
    for trade_date in missing:
        try:
            await pipeline.run_morning(trade_date=trade_date)
            backfilled += 1
            logger.info(
                "stock_warmup: trade_date=%s backfilled (window=%d)",
                trade_date,
                _clamp_window(window_days),
            )
        except Exception as e:  # noqa: BLE001 — 边界 catch-all
            logger.warning(
                "stock_warmup: trade_date=%s failed: %s", trade_date, e
            )
            # 单日失败不影响后续日期

    logger.info(
        "stock_warmup: done; total=%d backfilled=%d",
        len(missing),
        backfilled,
    )
    return backfilled
