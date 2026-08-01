"""Task 10 失败测试先行：启动期股票缓存回填。

覆盖（基于 4-step 模式：先写失败，再写实现）：
- find_missing_limit_dates：
  - 全空 / 全有 / 部分缺 / 窗口边界（1, 0, 30）/ weekend 过滤 /
    trading_calendar 过滤 / 返回顺序由近及远
- run_stock_cache_warmup：
  - 成功路径返回回填数 / pipeline 单日抛错不外抛 /
    pipeline 未注册返回 0 / 缺 trading_calendar 时 lazy load

设计要点：
- 内联最小 FakeStockDataSource（仅实现 has_limit_stocks，duck-type 满足
  domain.stock.ports.StockDataSource 协议子集）
- pipeline 通过 monkeypatch 替换 application.stock.warmup.get_default_pipeline
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import AsyncMock

import pytest

from application.stock import warmup as warmup_mod
from application.stock import pipeline as pipeline_mod


# ── 共享 fake ──────────────────────────────────────────────


class FakeStockDataSource:
    """最小 StockDataSource fake：5 张表分别可配（Task 10 + 16 兼容）。

    Task 16 修订：扩展为 5 张表 has_* 方法，参数从单 populated_dates
    改为 limit_stocks / market_index / emotion_daily /
    sector_daily / stock_daily 五个 set；老测试仍可通过 ``populated_dates``
    向后兼容（仅填 limit_stocks）。
    """

    def __init__(
        self,
        populated_dates: set[str] | None = None,
        *,
        market_index: set[str] | None = None,
        emotion_daily: set[str] | None = None,
        sector_daily: set[str] | None = None,
        stock_daily: set[str] | None = None,
    ) -> None:
        self._populated: set[str] = set(populated_dates or set())
        self._market: set[str] = set(market_index or set())
        self._emotion: set[str] = set(emotion_daily or set())
        self._sector: set[str] = set(sector_daily or set())
        self._stock: set[str] = set(stock_daily or set())
        self.calls: list[str] = []

    async def has_limit_stocks(self, trade_date: str) -> bool:
        self.calls.append(trade_date)
        return trade_date in self._populated

    async def has_market_index(self, trade_date: str) -> bool:
        return trade_date in self._market

    async def has_emotion_daily(self, trade_date: str) -> bool:
        return trade_date in self._emotion

    async def has_sector_daily(self, trade_date: str) -> bool:
        return trade_date in self._sector

    async def has_stock_daily(self, trade_date: str) -> bool:
        return trade_date in self._stock

    # Task 19：行数对齐判定需要 count_* 方法；本 fake 用 set 表示"有/无"，
    # count_* 返回 1（present）/ 0（absent）。Task 19 的对齐检查只看相对大小，
    # 单值对齐场景下（每个日期的 5 张表都 1 行）足以验证"对齐"路径。
    async def count_limit_stocks(self, trade_date: str) -> int:
        return 1 if trade_date in self._populated else 0

    async def count_stock_daily(self, trade_date: str) -> int:
        return 1 if trade_date in self._stock else 0


async def _async_true(_td: str) -> bool:
    """Helper: 把 lambda 变 async 用于覆盖 has_* 默认实现。"""
    return True


def _make_pipeline_result(phase: str = "morning", written: int = 5) -> Any:
    class _R:
        def __init__(self) -> None:
            self.phase = phase
            self.written = written
            self.errors: list[str] = []
            self.duration_ms = 10

    return _R()


class FakePipeline:
    """满足 StockPipelineService.run_morning 协议的假门面。"""

    def __init__(self, *, fail_dates: set[str] | None = None) -> None:
        self.run_morning = AsyncMock(return_value=_make_pipeline_result())
        self._fail_dates = fail_dates or set()

    async def _maybe_fail(self, trade_date: str) -> None:
        if trade_date in self._fail_dates:
            raise RuntimeError(f"akshare 网络异常 {trade_date}")

    def install_failure(self, fail_dates: set[str]) -> None:
        """包装 run_morning 让指定日期抛错。"""
        self._fail_dates = set(fail_dates)

        async def _impl(*, trade_date: str, **_kw: Any) -> Any:
            await self._maybe_fail(trade_date)
            return _make_pipeline_result()

        self.run_morning = AsyncMock(side_effect=_impl)


@pytest.fixture
def fake_pipeline(monkeypatch: pytest.MonkeyPatch) -> FakePipeline:
    """把 fake pipeline 注册到 pipeline_mod 的默认注册表。"""
    pipe = FakePipeline()
    pipeline_mod.set_default_pipeline(pipe)
    yield pipe
    pipeline_mod.set_default_pipeline(None)


# 2026-07-29 是周三（按 ISO weekday 2）。测试固定 today 便于断言。
FIXED_TODAY = date(2026, 7, 29)
# 7-29 周三 → 倒推 14 天窗口 = 7-15（周三）到 7-29（周三），周末跳过：
# 7-15(三), 7-16(四), 7-17(五), 7-18(六)✗, 7-19(日)✗, 7-20(一),
# 7-21(二), 7-22(三), 7-23(四), 7-24(五), 7-25(六)✗, 7-26(日)✗,
# 7-27(一), 7-28(二), 7-29(三) = 11 个候选日


# ── find_missing_limit_dates ────────────────────────────────


class TestFindMissingLimitDatesAllEmpty:
    @pytest.mark.asyncio
    async def test_returns_all_candidates_when_cache_empty(self):
        ds = FakeStockDataSource(populated_dates=set())
        result = await warmup_mod.find_missing_limit_dates(
            ds, window_days=15, today=FIXED_TODAY
        )
        # 11 个候选日全部返回（顺序由近及远）
        assert len(result) == 11
        assert result[0] == "20260729"  # today
        assert result[-1] == "20260715"  # oldest
        # 中间没有周末
        assert "20260718" not in result  # 周六
        assert "20260719" not in result  # 周日
        assert "20260725" not in result  # 周六
        assert "20260726" not in result  # 周日


class TestFindMissingLimitDatesAllPopulated:
    @pytest.mark.asyncio
    async def test_returns_empty_when_all_candidates_have_data(self):
        all_dates = {
            "20260715", "20260716", "20260717",
            "20260720", "20260721", "20260722", "20260723", "20260724",
            "20260727", "20260728", "20260729",
        }
        ds = FakeStockDataSource(populated_dates=all_dates)
        result = await warmup_mod.find_missing_limit_dates(
            ds, window_days=15, today=FIXED_TODAY
        )
        assert result == []


class TestFindMissingLimitDatesPartial:
    @pytest.mark.asyncio
    async def test_returns_only_missing_subset(self):
        populated = {"20260729", "20260728", "20260727", "20260724"}
        ds = FakeStockDataSource(populated_dates=populated)
        result = await warmup_mod.find_missing_limit_dates(
            ds, window_days=15, today=FIXED_TODAY
        )
        # 缺的应该是 7/15, 7/16, 7/17, 7/20, 7/21, 7/22, 7/23
        assert set(result) == {
            "20260715", "20260716", "20260717",
            "20260720", "20260721", "20260722", "20260723",
        }
        # 顺序由近及远
        assert result[0] == "20260723"
        assert result[-1] == "20260715"


class TestFindMissingLimitDatesWindowBounds:
    @pytest.mark.asyncio
    async def test_window_one_returns_only_today(self):
        ds = FakeStockDataSource()
        result = await warmup_mod.find_missing_limit_dates(
            ds, window_days=1, today=FIXED_TODAY
        )
        assert result == ["20260729"]

    @pytest.mark.asyncio
    async def test_window_zero_clamped_to_one(self):
        ds = FakeStockDataSource()
        result = await warmup_mod.find_missing_limit_dates(
            ds, window_days=0, today=FIXED_TODAY
        )
        assert result == ["20260729"]

    @pytest.mark.asyncio
    async def test_window_30_clamped_to_60_returns_30(self):
        """window_days=30 不会触发 clamp 上限（30 < 60），返回最近 30 天候选。"""
        ds = FakeStockDataSource()
        result = await warmup_mod.find_missing_limit_dates(
            ds, window_days=30, today=FIXED_TODAY
        )
        # 30 天 = 22 个工作日左右（7-29 倒推到 6-30）
        # 仅校验数量大于 0 且包含 today
        assert "20260729" in result
        assert len(result) > 11  # 比 15 天窗口多

    @pytest.mark.asyncio
    async def test_window_100_clamped_to_60(self):
        """window_days=100 触发 clamp 上限到 60；返回的日期不会超过 60 天前。"""
        ds = FakeStockDataSource()
        result = await warmup_mod.find_missing_limit_dates(
            ds, window_days=100, today=FIXED_TODAY
        )
        # 60 天窗口：2026-05-31 到 2026-07-29，约 43 个工作日
        # 仅校验最早日期不超过 60 天前
        oldest = min(result)
        oldest_date = date(
            int(oldest[0:4]), int(oldest[4:6]), int(oldest[6:8])
        )
        delta = (FIXED_TODAY - oldest_date).days
        assert delta <= 60


class TestFindMissingLimitDatesTradingCalendar:
    @pytest.mark.asyncio
    async def test_calendar_filters_non_trading_days(self):
        # 交易日历只标 20260729, 20260728, 20260727 三天
        calendar = {"20260729", "20260728", "20260727"}
        ds = FakeStockDataSource()
        result = await warmup_mod.find_missing_limit_dates(
            ds,
            window_days=15,
            today=FIXED_TODAY,
            trading_calendar=calendar,
        )
        assert result == ["20260729", "20260728", "20260727"]


# ── run_stock_cache_warmup ─────────────────────────────────


class TestRunStockCacheWarmupSuccess:
    @pytest.mark.asyncio
    async def test_calls_pipeline_for_each_missing_date(
        self, fake_pipeline: FakePipeline
    ):
        ds = FakeStockDataSource(populated_dates=set())
        result = await warmup_mod.run_stock_cache_warmup(
            ds, window_days=15, today=FIXED_TODAY
        )
        # 11 个候选日全部回填
        assert result == 11
        assert fake_pipeline.run_morning.await_count == 11
        # 顺序由近及远：第一次调用应是 today
        first_call = fake_pipeline.run_morning.await_args_list[0]
        assert first_call.kwargs["trade_date"] == "20260729"


class TestRunStockCacheWarmupNoMissing:
    @pytest.mark.asyncio
    async def test_skips_when_all_candidates_have_data(
        self, fake_pipeline: FakePipeline
    ):
        """Task 16: 5 张表都齐才返 0。"""
        all_dates = {
            "20260715", "20260716", "20260717",
            "20260720", "20260721", "20260722", "20260723", "20260724",
            "20260727", "20260728", "20260729",
        }
        ds = FakeStockDataSource(
            populated_dates=all_dates,
            market_index=all_dates,
            emotion_daily=all_dates,
            sector_daily=all_dates,
            stock_daily=all_dates,
        )
        result = await warmup_mod.run_stock_cache_warmup(
            ds, window_days=15, today=FIXED_TODAY
        )
        assert result == 0
        assert fake_pipeline.run_morning.await_count == 0


class TestRunStockCacheWarmupSwallowsErrors:
    @pytest.mark.asyncio
    async def test_pipeline_exception_does_not_propagate(
        self, fake_pipeline: FakePipeline
    ):
        # 7-29 和 7-28 让它抛错
        fake_pipeline.install_failure({"20260729", "20260728"})
        ds = FakeStockDataSource(populated_dates=set())
        # 不应抛
        result = await warmup_mod.run_stock_cache_warmup(
            ds, window_days=15, today=FIXED_TODAY
        )
        # 11 个候选，2 个失败 → 9 个成功
        assert result == 9
        assert fake_pipeline.run_morning.await_count == 11


class TestRunStockCacheWarmupNoPipeline:
    @pytest.mark.asyncio
    async def test_returns_zero_when_no_pipeline_registered(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        pipeline_mod.set_default_pipeline(None)
        ds = FakeStockDataSource(populated_dates=set())
        result = await warmup_mod.run_stock_cache_warmup(
            ds, window_days=15, today=FIXED_TODAY
        )
        assert result == 0


class TestRunStockCacheWarmupLazyCalendar:
    @pytest.mark.asyncio
    async def test_loads_calendar_when_not_provided(
        self, fake_pipeline: FakePipeline, monkeypatch: pytest.MonkeyPatch
    ):
        """未传 trading_calendar 时，warmup 内部调用 _load_trading_calendar 一次。"""
        calendar = {"20260729", "20260728"}  # 只这两天
        all_dates = calendar
        from application import scheduler

        async def _fake_load() -> set[str]:
            return set(calendar)

        monkeypatch.setattr(scheduler, "_load_trading_calendar", _fake_load)
        # 5 张表都填这 2 天（避免其他 4 张空被判定为缺）
        ds = FakeStockDataSource(
            populated_dates=set(),  # 全空：5 张表都缺
            market_index=set(),
            emotion_daily=set(),
            sector_daily=set(),
            stock_daily=set(),
        )
        result = await warmup_mod.run_stock_cache_warmup(
            ds, window_days=15, today=FIXED_TODAY
        )
        # calendar 只含 2 个交易日 → 只回填 2 个
        assert result == 2
        assert fake_pipeline.run_morning.await_count == 2

    @pytest.mark.asyncio
    async def test_falls_back_to_weekday_when_calendar_load_fails(
        self, fake_pipeline: FakePipeline, monkeypatch: pytest.MonkeyPatch
    ):
        """_load_trading_calendar 抛错 → 回退到 weekday 过滤。"""
        from application import scheduler

        async def _fake_load_fail() -> set[str]:
            raise RuntimeError("akshare 不可用")

        monkeypatch.setattr(
            scheduler, "_load_trading_calendar", _fake_load_fail
        )
        ds = FakeStockDataSource(populated_dates=set())
        result = await warmup_mod.run_stock_cache_warmup(
            ds, window_days=15, today=FIXED_TODAY
        )
        # weekday 兜底 → 11 个工作日全部回填
        assert result == 11
