"""Task 6 失败测试：调度触发与防漏。

覆盖 6 项验收用例（计划文档 §7 Task 6）：
1. 交易日 16:30 后唤醒 → 执行收盘管线
2. 进程 17:00 重启（错过窗口）→ due 判定触发补抓
3. 当日已完成 → 不重复执行（last_done_date 节流）
4. 仅周五在收盘管线后串行追加相关性分析
5. 非交易日（周末/节假日）→ 跳过，不写库
6. akshare 失败 → 仅 log warning，任务不抛异常

设计要点：
- 调度函数从模块状态读取 trading_calendar + last_done_date
- 测试通过 monkeypatch 注入假时间、假日历、假 pipeline
- 把"due 判定"和"执行管线"拆开；测试优先覆盖判定逻辑
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from application import scheduler
from application.stock import pipeline as pipeline_mod


# ── 共享 fake ──────────────────────────────────────────────


class FakeStockPipelineService:
    """满足 StockPipelineService 协议的内存假门面。"""

    def __init__(self) -> None:
        self.run_close = AsyncMock(return_value=_ok_result("close"))
        self.run_morning = AsyncMock(return_value=_ok_result("morning"))
        self.run_correlation = AsyncMock(return_value=_ok_correlation())

    def reset_records(self) -> None:
        self.run_close.reset_mock()
        self.run_morning.reset_mock()
        self.run_correlation.reset_mock()


def _ok_result(phase: str) -> Any:
    """构造一个最小 PipelineResult（duck-type）。"""

    class _R:
        def __init__(self) -> None:
            self.phase = phase
            self.written = 1
            self.errors: list[str] = []
            self.duration_ms = 10

    return _R()


def _ok_correlation() -> Any:
    class _C:
        individual_stocks: list = []
        clustered_groups: list = []

    return _C()


@pytest.fixture
def fake_pipeline(monkeypatch) -> FakeStockPipelineService:
    """把 fake pipeline 注册到 pipeline_mod 默认实例。"""
    pipe = FakeStockPipelineService()
    pipeline_mod.set_default_pipeline(pipe)
    yield pipe
    pipeline_mod.set_default_pipeline(None)


@pytest.fixture
def reset_scheduler_state(monkeypatch):
    """每个测试前重置 last_done + trading_calendar。"""
    monkeypatch.setattr(scheduler, "_LAST_DONE_CLOSE", {})
    monkeypatch.setattr(scheduler, "_LAST_DONE_MORNING", {})
    monkeypatch.setattr(scheduler, "_TRADING_CALENDAR", set())


def _set_now(monkeypatch, iso: str) -> None:
    """把 _now_cst() 替换为固定时间。"""
    fixed = datetime.fromisoformat(iso)

    def _fixed_now() -> datetime:
        return fixed

    monkeypatch.setattr(scheduler, "_now_cst", _fixed_now)


def _set_calendar(monkeypatch, dates: list[str]) -> None:
    """直接覆盖交易日历集合。"""
    monkeypatch.setattr(scheduler, "_TRADING_CALENDAR", set(dates))


# ── 1. 交易日 16:30 后唤醒 → 执行收盘管线 ────────────────


class TestCloseFetchRunsAfter1630OnTradingDay:
    @pytest.mark.asyncio
    async def test_runs_pipeline_when_now_after_close_on_trading_day(
        self, monkeypatch, fake_pipeline, reset_scheduler_state
    ):
        _set_calendar(monkeypatch, ["20260728"])
        _set_now(monkeypatch, "2026-07-28T16:35:00+08:00")
        await scheduler.run_stock_close_fetch_once()

        assert fake_pipeline.run_close.await_count == 1
        assert fake_pipeline.run_close.await_args.kwargs["trade_date"] == "20260728"
        # 不应触发 morning / correlation
        assert fake_pipeline.run_morning.await_count == 0
        assert fake_pipeline.run_correlation.await_count == 0


# ── 2. 进程 17:00 重启（错过窗口）→ due 判定触发补抓 ─────


class TestCloseFetchCatchupAfterRestart:
    @pytest.mark.asyncio
    async def test_catchup_when_started_after_1630_no_last_done(
        self, monkeypatch, fake_pipeline, reset_scheduler_state
    ):
        """17:00 启动（错过 16:30 窗口）→ last_done 空 → 立即补抓。"""
        _set_calendar(monkeypatch, ["20260728"])
        _set_now(monkeypatch, "2026-07-28T17:00:00+08:00")
        # last_done 空：未跑过
        await scheduler.run_stock_close_fetch_once()

        assert fake_pipeline.run_close.await_count == 1
        assert fake_pipeline.run_close.await_args.kwargs["trade_date"] == "20260728"


# ── 3. 当日已完成 → 不重复执行 ────────────────────────────


class TestCloseFetchIdempotentSameDay:
    @pytest.mark.asyncio
    async def test_skips_when_already_done_today(
        self, monkeypatch, fake_pipeline, reset_scheduler_state
    ):
        _set_calendar(monkeypatch, ["20260728"])
        _set_now(monkeypatch, "2026-07-28T16:35:00+08:00")
        scheduler._LAST_DONE_CLOSE["close"] = "20260728"

        await scheduler.run_stock_close_fetch_once()

        assert fake_pipeline.run_close.await_count == 0


# ── 4. 仅周五在收盘管线后串行追加相关性分析 ────────────────


class TestCorrelationOnlyOnFriday:
    @pytest.mark.asyncio
    async def test_correlation_runs_on_friday_after_close(
        self, monkeypatch, fake_pipeline, reset_scheduler_state
    ):
        """2026-07-31 是周五（按 ISO 星期）。"""
        _set_calendar(monkeypatch, ["20260731"])
        _set_now(monkeypatch, "2026-07-31T16:35:00+08:00")
        await scheduler.run_stock_close_fetch_once()

        assert fake_pipeline.run_close.await_count == 1
        assert fake_pipeline.run_correlation.await_count == 1
        # 早盘不应该跑
        assert fake_pipeline.run_morning.await_count == 0

    @pytest.mark.asyncio
    async def test_correlation_skipped_on_non_friday(
        self, monkeypatch, fake_pipeline, reset_scheduler_state
    ):
        """2026-07-28 是周二（按 ISO 星期）。"""
        _set_calendar(monkeypatch, ["20260728"])
        _set_now(monkeypatch, "2026-07-28T16:35:00+08:00")
        await scheduler.run_stock_close_fetch_once()

        assert fake_pipeline.run_close.await_count == 1
        assert fake_pipeline.run_correlation.await_count == 0


# ── 5. 非交易日 → 跳过 ────────────────────────────────────


class TestNonTradingDaySkips:
    @pytest.mark.asyncio
    async def test_weekend_skipped(
        self, monkeypatch, fake_pipeline, reset_scheduler_state
    ):
        """2026-07-26 是周日（按 ISO 星期）；不在交易日历。"""
        _set_calendar(monkeypatch, ["20260728"])  # 不含周日
        _set_now(monkeypatch, "2026-07-26T16:35:00+08:00")
        await scheduler.run_stock_close_fetch_once()

        assert fake_pipeline.run_close.await_count == 0
        assert fake_pipeline.run_correlation.await_count == 0

    @pytest.mark.asyncio
    async def test_morning_skipped_on_non_trading_day(
        self, monkeypatch, fake_pipeline, reset_scheduler_state
    ):
        _set_calendar(monkeypatch, ["20260728"])
        _set_now(monkeypatch, "2026-07-26T11:35:00+08:00")  # 周日
        await scheduler.run_stock_morning_fetch_once()

        assert fake_pipeline.run_morning.await_count == 0


# ── 6. akshare 失败 → 不抛异常 ────────────────────────────


class TestFetchFailureDoesNotRaise:
    @pytest.mark.asyncio
    async def test_pipeline_exception_is_swallowed(
        self, monkeypatch, fake_pipeline, reset_scheduler_state
    ):
        """pipeline.run_close 抛异常 → scheduler 捕获并 log warning，不外抛。"""
        _set_calendar(monkeypatch, ["20260728"])
        _set_now(monkeypatch, "2026-07-28T16:35:00+08:00")

        async def _raise(*_a, **_kw):
            raise RuntimeError("akshare 网络异常")

        fake_pipeline.run_close = AsyncMock(side_effect=_raise)
        # 不应抛
        await scheduler.run_stock_close_fetch_once()

    @pytest.mark.asyncio
    async def test_correlation_exception_does_not_block(
        self, monkeypatch, fake_pipeline, reset_scheduler_state
    ):
        """周五 correlation 失败 → 收盘管线已完成，correl 异常被吞。"""
        _set_calendar(monkeypatch, ["20260731"])
        _set_now(monkeypatch, "2026-07-31T16:35:00+08:00")

        async def _raise(*_a, **_kw):
            raise RuntimeError("correlation 失败")

        fake_pipeline.run_correlation = AsyncMock(side_effect=_raise)
        await scheduler.run_stock_close_fetch_once()
        # 收盘管线仍应执行
        assert fake_pipeline.run_close.await_count == 1
        # last_done_close 应被设置（即便 correlation 失败）
        assert scheduler._LAST_DONE_CLOSE.get("close") == "20260731"
