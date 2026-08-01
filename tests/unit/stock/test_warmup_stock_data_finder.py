"""Task 16 失败测试：warmup 漏检 4 张表修复。

背景（Task 10 漏检）：
- 5 个 fetcher（limit / market_index / emotion_daily / sector_daily /
  stock_daily）已就绪，但 `find_missing_limit_dates` 只检测
  `has_limit_stocks` 一张表 → 只要 limit_stocks_daily 有数据，其它
  4 张表永远不会被回填。

修复：
- 新增 `find_missing_stock_data_dates`：5 张表任一缺失即回填该日
- `run_stock_cache_warmup` 改用新 finder

覆盖：
- find_missing_stock_data_dates：
  - 5 张表都齐 → 不回填
  - 5 张表都空 → 全回填
  - 任一表缺失（5 张表各 1 个测试）→ 该日回填
  - trading_calendar 仍生效
- run_stock_cache_warmup 调用新 finder（集成测试）：
  - 5 张表全空 → 11 个工作日全部回填
  - limit_stocks_daily 有 + 其它 4 张表无 → 仍回填（核心 bug 修复点）
  - 5 张表都齐 → 0 回填
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
    """5 张表分别独立可配的最小 StockDataSource fake。

    接受 5 个 set[str] 参数（每个表哪些日期有数据），未指定的日期视为空。
    """

    def __init__(
        self,
        *,
        limit_stocks: set[str] | None = None,
        market_index: set[str] | None = None,
        emotion_daily: set[str] | None = None,
        sector_daily: set[str] | None = None,
        stock_daily: set[str] | None = None,
    ) -> None:
        self._limit = set(limit_stocks or set())
        self._market = set(market_index or set())
        self._emotion = set(emotion_daily or set())
        self._sector = set(sector_daily or set())
        self._stock = set(stock_daily or set())
        # 记录每个端口的调用次数（便于断言"任一表缺失"路径）
        self.calls: dict[str, list[str]] = {
            "limit": [],
            "market": [],
            "emotion": [],
            "sector": [],
            "stock": [],
        }

    async def has_limit_stocks(self, trade_date: str) -> bool:
        self.calls["limit"].append(trade_date)
        return trade_date in self._limit

    async def has_market_index(self, trade_date: str) -> bool:
        self.calls["market"].append(trade_date)
        return trade_date in self._market

    async def has_emotion_daily(self, trade_date: str) -> bool:
        self.calls["emotion"].append(trade_date)
        return trade_date in self._emotion

    async def has_sector_daily(self, trade_date: str) -> bool:
        self.calls["sector"].append(trade_date)
        return trade_date in self._sector

    async def has_stock_daily(self, trade_date: str) -> bool:
        self.calls["stock"].append(trade_date)
        return trade_date in self._stock

    # Task 19：行数对齐判定需要 count_* 方法。本 fake 用 set 表示"有/无"，
    # count_* 返回 1（present）/ 0（absent）；对齐场景下所有"有"的日期都返 1，
    # 与 count_limit_stocks 相同 → 触发对齐短路。
    async def count_limit_stocks(self, trade_date: str) -> int:
        return 1 if trade_date in self._limit else 0

    async def count_stock_daily(self, trade_date: str) -> int:
        return 1 if trade_date in self._stock else 0


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

    def __init__(self) -> None:
        self.run_morning = AsyncMock(return_value=_make_pipeline_result())


@pytest.fixture
def fake_pipeline(monkeypatch: pytest.MonkeyPatch) -> FakePipeline:
    pipe = FakePipeline()
    pipeline_mod.set_default_pipeline(pipe)
    yield pipe
    pipeline_mod.set_default_pipeline(None)


# 2026-07-29 周三
FIXED_TODAY = date(2026, 7, 29)
ALL_11_CANDIDATES = {
    "20260715", "20260716", "20260717",
    "20260720", "20260721", "20260722", "20260723", "20260724",
    "20260727", "20260728", "20260729",
}


# ── find_missing_stock_data_dates：5 张表任一缺失 ─────


class TestFindMissingStockDataDatesAllPopulated:
    @pytest.mark.asyncio
    async def test_returns_empty_when_all_5_tables_populated(self):
        ds = FakeStockDataSource(
            limit_stocks=ALL_11_CANDIDATES,
            market_index=ALL_11_CANDIDATES,
            emotion_daily=ALL_11_CANDIDATES,
            sector_daily=ALL_11_CANDIDATES,
            stock_daily=ALL_11_CANDIDATES,
        )
        result = await warmup_mod.find_missing_stock_data_dates(
            ds, window_days=15, today=FIXED_TODAY
        )
        assert result == []


class TestFindMissingStockDataDatesAllEmpty:
    @pytest.mark.asyncio
    async def test_returns_all_candidates_when_5_tables_empty(self):
        ds = FakeStockDataSource()  # 全空
        result = await warmup_mod.find_missing_stock_data_dates(
            ds, window_days=15, today=FIXED_TODAY
        )
        assert len(result) == 11
        assert result[0] == "20260729"
        assert result[-1] == "20260715"
        # 中间无周末
        for wk in ("20260718", "20260719", "20260725", "20260726"):
            assert wk not in result


# ── 核心 bug 修复：任一表缺失 → 该日回填 ─────────


class TestFindMissingStockDataDatesAnyTableMissing:
    """5 张表各做 1 个测试：任一表缺失 → 候选日全回填。"""

    @pytest.mark.asyncio
    async def test_missing_market_index_only(self):
        # limit_stocks 已有数据；只缺 market_index
        ds = FakeStockDataSource(limit_stocks=ALL_11_CANDIDATES)
        result = await warmup_mod.find_missing_stock_data_dates(
            ds, window_days=15, today=FIXED_TODAY
        )
        # 11 天全回填（任一表缺失即回填）
        assert set(result) == ALL_11_CANDIDATES
        # 顺序由近及远
        assert result[0] == "20260729"
        assert result[-1] == "20260715"
        # limit_stocks 一定被调（每个候选日最先查它）；market_index 紧随其后
        assert len(ds.calls["limit"]) == 11
        assert len(ds.calls["market"]) == 11
        # 后续 3 张表因 break 早出，0 次调用（这也是短路求值的预期效果）
        assert len(ds.calls["emotion"]) == 0
        assert len(ds.calls["sector"]) == 0
        assert len(ds.calls["stock"]) == 0

    @pytest.mark.asyncio
    async def test_missing_emotion_daily_only(self):
        ds = FakeStockDataSource(
            limit_stocks=ALL_11_CANDIDATES,
            market_index=ALL_11_CANDIDATES,
        )
        result = await warmup_mod.find_missing_stock_data_dates(
            ds, window_days=15, today=FIXED_TODAY
        )
        assert set(result) == ALL_11_CANDIDATES

    @pytest.mark.asyncio
    async def test_missing_sector_daily_only(self):
        ds = FakeStockDataSource(
            limit_stocks=ALL_11_CANDIDATES,
            market_index=ALL_11_CANDIDATES,
            emotion_daily=ALL_11_CANDIDATES,
        )
        result = await warmup_mod.find_missing_stock_data_dates(
            ds, window_days=15, today=FIXED_TODAY
        )
        assert set(result) == ALL_11_CANDIDATES

    @pytest.mark.asyncio
    async def test_missing_stock_daily_only(self):
        ds = FakeStockDataSource(
            limit_stocks=ALL_11_CANDIDATES,
            market_index=ALL_11_CANDIDATES,
            emotion_daily=ALL_11_CANDIDATES,
            sector_daily=ALL_11_CANDIDATES,
        )
        result = await warmup_mod.find_missing_stock_data_dates(
            ds, window_days=15, today=FIXED_TODAY
        )
        assert set(result) == ALL_11_CANDIDATES

    @pytest.mark.asyncio
    async def test_missing_partial_subset_only_specific_days(self):
        # 4 张表都齐，但 market_index 只缺 7-15
        ds = FakeStockDataSource(
            limit_stocks=ALL_11_CANDIDATES,
            market_index=ALL_11_CANDIDATES - {"20260715"},
            emotion_daily=ALL_11_CANDIDATES,
            sector_daily=ALL_11_CANDIDATES,
            stock_daily=ALL_11_CANDIDATES,
        )
        result = await warmup_mod.find_missing_stock_data_dates(
            ds, window_days=15, today=FIXED_TODAY
        )
        # 只有 7-15 缺 → 只回填这一天
        assert result == ["20260715"]


# ── trading_calendar 仍生效 ─────────────────────────────


class TestFindMissingStockDataDatesTradingCalendar:
    @pytest.mark.asyncio
    async def test_calendar_filters_candidates(self):
        calendar = {"20260729", "20260728", "20260727"}
        ds = FakeStockDataSource()  # 全空
        result = await warmup_mod.find_missing_stock_data_dates(
            ds,
            window_days=15,
            today=FIXED_TODAY,
            trading_calendar=calendar,
        )
        assert result == ["20260729", "20260728", "20260727"]


# ── run_stock_cache_warmup 集成：核心 bug 修复点 ──────


class TestRunStockCacheWarmupUsesStockDataFinder:
    @pytest.mark.asyncio
    async def test_reruns_when_only_limit_stocks_populated(
        self, fake_pipeline: FakePipeline
    ):
        """核心 bug 修复：limit_stocks 已齐 + 其它 4 张表空 → 仍回填。

        之前 find_missing_limit_dates 会返 [] → 0 次调用；
        现在 find_missing_stock_data_dates 返 11 → 11 次调用。
        """
        ds = FakeStockDataSource(limit_stocks=ALL_11_CANDIDATES)
        result = await warmup_mod.run_stock_cache_warmup(
            ds, window_days=15, today=FIXED_TODAY
        )
        # 11 个工作日全部回填
        assert result == 11
        assert fake_pipeline.run_morning.await_count == 11

    @pytest.mark.asyncio
    async def test_zero_when_all_5_tables_populated(
        self, fake_pipeline: FakePipeline
    ):
        ds = FakeStockDataSource(
            limit_stocks=ALL_11_CANDIDATES,
            market_index=ALL_11_CANDIDATES,
            emotion_daily=ALL_11_CANDIDATES,
            sector_daily=ALL_11_CANDIDATES,
            stock_daily=ALL_11_CANDIDATES,
        )
        result = await warmup_mod.run_stock_cache_warmup(
            ds, window_days=15, today=FIXED_TODAY
        )
        assert result == 0
        assert fake_pipeline.run_morning.await_count == 0

    @pytest.mark.asyncio
    async def test_full_backfill_when_all_empty(
        self, fake_pipeline: FakePipeline
    ):
        ds = FakeStockDataSource()
        result = await warmup_mod.run_stock_cache_warmup(
            ds, window_days=15, today=FIXED_TODAY
        )
        assert result == 11
        # 顺序由近及远：第一次调用应是 today
        first_call = fake_pipeline.run_morning.await_args_list[0]
        assert first_call.kwargs["trade_date"] == "20260729"
