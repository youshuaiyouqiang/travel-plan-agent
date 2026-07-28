"""P1-3：记忆维护与热点池后台调度器。

记忆维护（每小时）：
1. 逐用户蒸馏（确保用户间记忆隔离，避免 TypeError 与跨用户污染）
2. 全量衰减（run_decay 内部按 user_id 分组处理）

热点刷新（每 15 分钟）：
- 调用 ``HotspotService.refresh`` 仅抓取 ``enabled`` 来源。
- 不抓取新闻全文；只更新元数据缓存。

热点清理（每 6 小时）：
- 当前为占位实现：仅记录日志。
- 后续若引入聚类/衰减策略，在此扩展，不破坏现有抓取流程。

关键设计：
- `run_distillation(user_id: str)` 的参数是必填 str，不支持 None
- 蒸馏必须在独立线程中执行（via asyncio.to_thread），让 _compress_content
  内部的 asyncio.run() 能正常工作
- 使用 lifespan 上下文管理器注册，不使用废弃的 @app.on_event("startup")
"""

from __future__ import annotations

import asyncio
import logging

from domain.memory.memory_distiller import MemoryDistiller
from domain.memory.ports import get_default_memory_repository
from domain.shared.llm.ports import get_default_llm

logger = logging.getLogger(__name__)

# 蒸馏循环间隔（秒）
_DISTILL_INTERVAL = 3600  # 1 小时

# 热点刷新间隔（秒）— Task 2：每 15 分钟增量刷新一次
_HOTSPOT_REFRESH_INTERVAL = 900  # 15 分钟

# 热点清理/重聚类间隔（秒）— Task 2：每 6 小时执行一次
_HOTSPOT_CLEANUP_INTERVAL = 6 * 3600  # 6 小时


async def run_memory_maintenance() -> None:
    """后台任务：逐用户蒸馏 + 衰减。

    每小时跑一次。第一次启动延迟 60 秒，避免与 lifespan warmup 抢资源。
    """
    await asyncio.sleep(60)

    while True:
        try:
            # P4.1：通过组合根注册的默认 LLM 端口构造 distiller，
            # 不再直接 ``OpenAILLM(...)`` 实例化（消除 application → infrastructure 依赖）。
            llm = get_default_llm()
            if llm is None:
                logger.warning("No default LLM configured; skip memory maintenance cycle")
                await asyncio.sleep(_DISTILL_INTERVAL)
                continue
            distiller = MemoryDistiller(llm=llm)

            # 1. 枚举所有有短期记忆的用户，逐个蒸馏（确保隔离）
            # P2.6：通过 MemoryRepositoryPort 枚举用户，不再直接查询数据库
            memory_repo = get_default_memory_repository()
            user_ids = memory_repo.list_user_ids_with_short_term_memories()

            total_distilled = 0
            for uid in user_ids:
                try:
                    # 在独立线程中调用 sync run_distillation，
                    # 让 _compress_content 内的 asyncio.run() 正常工作
                    distilled = await asyncio.to_thread(distiller.run_distillation, uid)
                    if distilled > 0:
                        logger.info("Memory distilled: user=%s count=%d", uid, distilled)
                    total_distilled += distilled
                except Exception:
                    logger.warning("Distillation failed for user=%s", uid, exc_info=True)

            # 2. 全量衰减（run_decay 支持 user_id=None，内部按 user_id 分组）
            try:
                decayed = await asyncio.to_thread(distiller.run_decay, None)
                if decayed > 0:
                    logger.info("Memory decay: total=%d", decayed)
            except Exception:
                logger.warning("Memory decay failed", exc_info=True)

            logger.info(
                "Memory maintenance cycle done: users=%d distilled=%d",
                len(user_ids),
                total_distilled,
            )
        except Exception:
            logger.warning("Memory maintenance cycle failed", exc_info=True)

        await asyncio.sleep(_DISTILL_INTERVAL)


async def run_hotspot_refresh() -> None:
    """后台任务：每 15 分钟刷新热点池。

    - 仅抓取 ``enabled`` 来源；非 enabled 由 ``SourceService`` 过滤。
    - 不抓取新闻全文；只更新元数据缓存。
    - 首次启动延迟 30 秒，避免与 lifespan warmup 抢资源。
    """
    await asyncio.sleep(30)
    while True:
        try:
            from application.news.hotspot_service import get_default_service

            service = get_default_service()
            result = await service.refresh()
            logger.info(
                "Hotspot refresh cycle done: count=%d sources=%d",
                result.count,
                len(result.sources_used),
            )
        except Exception:
            logger.warning("Hotspot refresh cycle failed", exc_info=True)

        await asyncio.sleep(_HOTSPOT_REFRESH_INTERVAL)


async def run_hotspot_cleanup() -> None:
    """后台任务：每 6 小时执行一次热点清理/重聚类。

    当前为占位实现：仅记录日志。后续若引入聚类/衰减策略，在此扩展，
    不破坏现有抓取流程。首次启动延迟 5 分钟，避免与 warmup 抢资源。
    """
    await asyncio.sleep(300)
    while True:
        try:
            # 占位：当前热点池由 refresh 全量替换，无需额外清理。
            # 未来若引入聚类/衰减/过期清理，在此扩展。
            logger.info("Hotspot cleanup cycle: no-op (placeholder)")
        except Exception:
            logger.warning("Hotspot cleanup cycle failed", exc_info=True)

        await asyncio.sleep(_HOTSPOT_CLEANUP_INTERVAL)


# ── 股票复盘调度（Task 6，AGENTS.md §8.7 声明 lifespan 改动） ─────


from datetime import datetime
from zoneinfo import ZoneInfo  # noqa: E402  (Py3.9+ stdlib)

# A 股按北京时间（UTC+8）
_CST = ZoneInfo("Asia/Shanghai")

# 调度窗口
_MORNING_HOUR = 11
_MORNING_MINUTE = 30
_CLOSE_HOUR = 16
_CLOSE_MINUTE = 30
_POLL_INTERVAL_SECONDS = 600  # 10 分钟轮询，due 判定

# 模块级状态（测试可通过 monkeypatch 覆盖）
_TRADING_CALENDAR: set[str] = set()  # YYYYMMDD 集合
_LAST_DONE_CLOSE: dict[str, str] = {}  # key → trade_date
_LAST_DONE_MORNING: dict[str, str] = {}


def _now_cst() -> datetime:
    """当前北京时间（可被测试 monkeypatch 覆盖）。"""
    return datetime.now(_CST)


def _format_trade_date(dt: datetime) -> str:
    """datetime → YYYYMMDD（用 CST 时区）。"""
    return dt.strftime("%Y%m%d")


def _is_trading_day(trade_date: str) -> bool:
    """判定给定日期是否为 A 股交易日。

    Args:
        trade_date: YYYYMMDD 字符串。

    Returns:
        True 当且仅当 ``trade_date`` 在 ``_TRADING_CALENDAR`` 集合内。
        集合为空时返回 False（避免误把任意日期当交易日）。
    """
    if not _TRADING_CALENDAR:
        return False
    return trade_date in _TRADING_CALENDAR


async def _load_trading_calendar() -> set[str]:
    """从 akshare 加载全年交易日历到内存（启动时调用一次）。

    失败时仅 log warning，保留空集合（_is_trading_day 返回 False，
    调度自动跳过，不会用错误数据乱跑）。
    """
    global _TRADING_CALENDAR
    try:
        import akshare as ak

        df = ak.tool_trade_date_hist_sina()
        if df is None or len(df) == 0:
            logger.warning("Trading calendar empty from akshare")
            return _TRADING_CALENDAR
        # akshare 返回 DataFrame 含 trade_date 列（YYYY-MM-DD）
        _TRADING_CALENDAR = {
            str(d).replace("-", "") for d in df["trade_date"].tolist()
        }
        logger.info(
            "Trading calendar loaded: %d trading days", len(_TRADING_CALENDAR)
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to load trading calendar: %s", e)
    return _TRADING_CALENDAR


def _is_friday(trade_date: str) -> bool:
    """判定 YYYYMMDD 是否为周五（按 CST 解析）。"""
    try:
        dt = datetime.strptime(trade_date, "%Y%m%d").replace(tzinfo=_CST)
    except ValueError:
        return False
    return dt.weekday() == 4  # Monday=0, Friday=4


def _should_run_close(now: datetime) -> tuple[bool, str]:
    """收盘管线 due 判定。

    规则：
    - 当前时间 ≥ 16:30
    - 今天在交易日历内
    - 当日 last_done_close 未设置

    Returns:
        (should_run, trade_date)。
    """
    trade_date = _format_trade_date(now)
    if now.hour < _CLOSE_HOUR or (
        now.hour == _CLOSE_HOUR and now.minute < _CLOSE_MINUTE
    ):
        return False, trade_date
    if not _is_trading_day(trade_date):
        return False, trade_date
    if _LAST_DONE_CLOSE.get("close") == trade_date:
        return False, trade_date
    return True, trade_date


def _should_run_morning(now: datetime) -> tuple[bool, str]:
    """早盘管线 due 判定。

    规则：
    - 当前时间 ≥ 11:30
    - 今天在交易日历内
    - 当日 last_done_morning 未设置
    """
    trade_date = _format_trade_date(now)
    if now.hour < _MORNING_HOUR or (
        now.hour == _MORNING_HOUR and now.minute < _MORNING_MINUTE
    ):
        return False, trade_date
    if not _is_trading_day(trade_date):
        return False, trade_date
    if _LAST_DONE_MORNING.get("morning") == trade_date:
        return False, trade_date
    return True, trade_date


async def run_stock_close_fetch_once() -> None:
    """执行一次收盘管线判定 + 跑管线 + 周五链式 correlation。

    单次执行；用于 lifespan 后台循环轮询调用。失败仅 log warning，
    任务不抛异常。
    """
    now = _now_cst()
    should_run, trade_date = _should_run_close(now)
    if not should_run:
        return

    from application.stock.pipeline import get_default_pipeline

    pipeline = get_default_pipeline()
    if pipeline is None:
        logger.warning("stock_close_fetch: no default pipeline registered")
        return

    try:
        await pipeline.run_close(trade_date=trade_date)
    except Exception:  # noqa: BLE001
        logger.warning("stock_close_fetch pipeline failed", exc_info=True)
        return

    # 标记当日已完成（即便 correlation 失败也算 close 跑过）
    _LAST_DONE_CLOSE["close"] = trade_date

    # 周五链式追加 correlation（失败不阻塞 close 已完成的状态）
    if _is_friday(trade_date):
        try:
            await pipeline.run_correlation(end_date=trade_date, days=7)
        except Exception:  # noqa: BLE001
            logger.warning(
                "stock_close_fetch: friday correlation failed",
                exc_info=True,
            )


async def run_stock_morning_fetch_once() -> None:
    """执行一次早盘管线判定 + 跑管线。

    单次执行；用于 lifespan 后台循环轮询调用。失败仅 log warning。
    """
    now = _now_cst()
    should_run, trade_date = _should_run_morning(now)
    if not should_run:
        return

    from application.stock.pipeline import get_default_pipeline

    pipeline = get_default_pipeline()
    if pipeline is None:
        logger.warning("stock_morning_fetch: no default pipeline registered")
        return

    try:
        await pipeline.run_morning(trade_date=trade_date)
    except Exception:  # noqa: BLE001
        logger.warning("stock_morning_fetch pipeline failed", exc_info=True)
        return

    _LAST_DONE_MORNING["morning"] = trade_date


async def run_stock_morning_fetch() -> None:
    """后台任务：早盘抓取（11:30 窗口起，10 分钟轮询）。

    首次启动延迟 30 秒避免与 lifespan warmup 抢资源。
    """
    await asyncio.sleep(30)
    # 启动时尝试加载交易日历（失败也无所谓，后续 _is_trading_day 返 False 跳过）
    await _load_trading_calendar()
    while True:
        try:
            await run_stock_morning_fetch_once()
        except Exception:  # noqa: BLE001
            logger.warning(
                "stock_morning_fetch cycle failed", exc_info=True
            )
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)


async def run_stock_close_fetch() -> None:
    """后台任务：收盘抓取（16:30 窗口起，10 分钟轮询 + 周五链式 correlation）。

    首次启动延迟 60 秒（等早盘先跑完再开始轮询收盘窗口）。
    """
    await asyncio.sleep(60)
    while True:
        try:
            await run_stock_close_fetch_once()
        except Exception:  # noqa: BLE001
            logger.warning(
                "stock_close_fetch cycle failed", exc_info=True
            )
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
