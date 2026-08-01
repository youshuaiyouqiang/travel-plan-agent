"""Task 19 失败测试：warmup 行数对齐 + 硬超时。

Issue 1-A（部分缺失永久化）：
- 现状：``has_stock_daily(date)`` 只查"是否有 1 行"，所以"99 → 80"
  的部分缺失状态被判定为"完整"，永远不会回填。
- 修复：新增 ``count_limit_stocks`` / ``count_stock_daily`` 端口方法；
  ``find_missing_stock_data_dates`` 增加第 2 阶段——当 5 张表都有行但
  ``count(stock_daily) < count(limit_stocks)`` 时也视为缺失。

Issue 1-B（warmup 整体无超时）：
- 现状：10 个工作日 × 5 fetcher × 99 股/日 = 几百次 akshare 调用，
  最坏情况跑 26 分钟，期间 login 慢 + 后台持续刷 warning。
- 修复：``run_stock_cache_warmup`` 加 ``timeout_seconds`` 参数；
  超时后立即 log warning 并返回已完成的 backfill 数。

覆盖（均失败先行 → 实现后变绿）：
- TestPortContract：协议声明 2 个 count_* 方法
- TestSqliteCount：SQLite 真实实现 count 返回值
- TestAkshareClientStubs：AkshareClient 有 NotImplementedError stub
- TestWarmupCountCheck：find_missing_stock_data_dates 3 阶段判定
  - test_partial_stock_daily_triggers_refetch
  - test_aligned_stock_daily_skips
  - test_no_limit_stocks_skips
- TestWarmupTimeout：run_stock_cache_warmup 硬超时
  - test_warmup_completes_within_timeout
  - test_warmup_aborts_on_timeout
  - test_warmup_no_timeout_default
- TestSettingsHasTimeoutField：settings.stock_warmup_timeout_seconds 存在
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import os
from datetime import date
from typing import Any
from unittest.mock import AsyncMock

import pytest

from application.stock import pipeline as pipeline_mod
from application.stock import warmup as warmup_mod
from config import settings
from domain.stock.ports import StockDataSource
from infrastructure.persistence.connection import get_connection
from infrastructure.persistence.database import init_db, reset_connection


# ── 共享 fake（兼容 Task 16 已有测试 + 扩展 count） ────────


class FakeStockDataSource:
    """5 张表分别独立可配的最小 StockDataSource fake（Task 19 扩展）。

    接受 5 个参数（每个表哪些日期有数据；Task 16 仅支持 ``set[str]``）：
    - ``set[str]``：每个日期算 1 行（兼容 Task 16 已有调用方）
    - ``dict[str, int]``：每个日期显式指定行数（Task 19 新增）

    count_limit_stocks / count_stock_daily 返回行数。
    """

    def __init__(
        self,
        *,
        limit_stocks: set[str] | dict[str, int] | None = None,
        market_index: set[str] | None = None,
        emotion_daily: set[str] | None = None,
        sector_daily: set[str] | None = None,
        stock_daily: set[str] | dict[str, int] | None = None,
    ) -> None:
        self._limit_count = _normalize_count_arg(limit_stocks)
        self._market = set(market_index or set())
        self._emotion = set(emotion_daily or set())
        self._sector = set(sector_daily or set())
        self._stock_count = _normalize_count_arg(stock_daily)
        self.calls: dict[str, list[str]] = {
            "limit": [],
            "market": [],
            "emotion": [],
            "sector": [],
            "stock": [],
            "count_limit": [],
            "count_stock": [],
        }

    async def has_limit_stocks(self, trade_date: str) -> bool:
        self.calls["limit"].append(trade_date)
        return self._limit_count.get(trade_date, 0) > 0

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
        return self._stock_count.get(trade_date, 0) > 0

    async def count_limit_stocks(self, trade_date: str) -> int:
        self.calls["count_limit"].append(trade_date)
        return self._limit_count.get(trade_date, 0)

    async def count_stock_daily(self, trade_date: str) -> int:
        self.calls["count_stock"].append(trade_date)
        return self._stock_count.get(trade_date, 0)


def _normalize_count_arg(arg: Any) -> dict[str, int]:
    """``set[str]`` → ``{d: 1}``；``dict[str, int]`` → 原样；None → ``{}``。"""
    if arg is None:
        return {}
    if isinstance(arg, set):
        return {d: 1 for d in arg}
    if isinstance(arg, dict):
        return dict(arg)
    raise TypeError(f"expected set or dict, got {type(arg).__name__}")


def _make_pipeline_result(phase: str = "morning", written: int = 5) -> Any:
    from application.stock.pipeline import PipelineResult

    return PipelineResult(
        phase=phase,
        trade_date="20260731",
        written=written,
        errors=[],
        duration_ms=10,
    )


# ── 1. 端口契约 ─────────────────────────────────────────


class TestPortContract:
    def test_port_has_count_limit_stocks(self) -> None:
        """StockDataSource 必须声明 count_limit_stocks。"""
        assert hasattr(StockDataSource, "count_limit_stocks"), (
            "StockDataSource 端口缺 count_limit_stocks 方法"
        )

    def test_port_has_count_stock_daily(self) -> None:
        assert hasattr(StockDataSource, "count_stock_daily"), (
            "StockDataSource 端口缺 count_stock_daily 方法"
        )

    def test_count_limit_stocks_signature(self) -> None:
        method = getattr(StockDataSource, "count_limit_stocks", None)
        assert method is not None
        sig = inspect.signature(method)
        required = [
            p for p in sig.parameters.values()
            if p.default is inspect.Parameter.empty and p.name != "self"
        ]
        assert [p.name for p in required] == ["trade_date"], (
            f"count_limit_stocks 必须只接受 trade_date，意外参数: "
            f"{[p.name for p in required]}"
        )

    def test_count_stock_daily_signature(self) -> None:
        method = getattr(StockDataSource, "count_stock_daily", None)
        assert method is not None
        sig = inspect.signature(method)
        required = [
            p for p in sig.parameters.values()
            if p.default is inspect.Parameter.empty and p.name != "self"
        ]
        assert [p.name for p in required] == ["trade_date"]

    def test_akshare_client_has_stubs(self) -> None:
        """AkshareClient 至少有 stub（NotImplementedError）。"""
        from infrastructure.stock.akshare_client import AkshareClient

        client = AkshareClient()
        assert hasattr(client, "count_limit_stocks")
        assert hasattr(client, "count_stock_daily")


# ── 2. SQLite 真实实现 ─────────────────────────────────


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_warmup_count.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()
    if db_path.exists():
        os.unlink(db_path)


def _seed_limit_stocks(conn, rows: list[tuple[str, str]]) -> None:
    for td, code in rows:
        conn.execute(
            "INSERT INTO limit_stocks_daily "
            "(trade_date, stock_code, stock_name, limit_type) "
            "VALUES (?, ?, ?, ?)",
            (td, code, f"测试股{code}", "limit_up"),
        )
    conn.commit()


def _seed_stock_daily(conn, rows: list[tuple[str, str]]) -> None:
    for td, code in rows:
        conn.execute(
            "INSERT INTO stock_daily "
            "(trade_date, stock_code, open, close) VALUES (?, ?, ?, ?)",
            (td, code, 10.0, 10.5),
        )
    conn.commit()


class TestSqliteCount:
    @pytest.mark.asyncio
    async def test_count_limit_stocks_returns_n(self, tmp_db) -> None:
        """count_limit_stocks 返回该日涨停股行数。"""
        _seed_limit_stocks(
            get_connection(),
            [("20260731", "000001"), ("20260731", "000002"), ("20260731", "000003")],
        )
        from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

        ds = SqliteStockDataSource(conn=get_connection())
        n = await ds.count_limit_stocks("20260731")
        assert n == 3

    @pytest.mark.asyncio
    async def test_count_stock_daily_returns_n(self, tmp_db) -> None:
        """count_stock_daily 返回该日 K 线行数。"""
        _seed_stock_daily(
            get_connection(),
            [("20260731", "000001"), ("20260731", "000002")],
        )
        from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

        ds = SqliteStockDataSource(conn=get_connection())
        n = await ds.count_stock_daily("20260731")
        assert n == 2

    @pytest.mark.asyncio
    async def test_count_zero_when_empty(self, tmp_db) -> None:
        """无数据时返 0（不返 None、不抛错）。"""
        from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

        ds = SqliteStockDataSource(conn=get_connection())
        assert await ds.count_limit_stocks("20260731") == 0
        assert await ds.count_stock_daily("20260731") == 0


# ── 3. 行数对齐判定（finder 第 2 阶段） ─────────────────


class TestWarmupCountCheck:
    """find_missing_stock_data_dates 在 has_* 全 True 后做对齐检查。"""

    @pytest.mark.asyncio
    async def test_partial_stock_daily_triggers_refetch(self) -> None:
        """5 张表都有行，但 stock_daily(80) < limit_stocks(99) → 回填。"""
        # 5 张表都有 20260731 的行（has_* 全 True）
        full_set = {"20260731"}
        # 但 stock_daily 只 80 行，limit_stocks 99 行
        fake = FakeStockDataSource(
            limit_stocks={"20260731": 99},
            market_index=full_set,
            emotion_daily=full_set,
            sector_daily=full_set,
            stock_daily={"20260731": 80},
        )
        missing = await warmup_mod.find_missing_stock_data_dates(
            fake,
            window_days=15,
            today=date(2026, 7, 31),
            trading_calendar={"20260731"},
        )
        assert "20260731" in missing, (
            "行数未对齐（80 < 99）但被判定为完整 → bug"
        )
        # 确认 count 方法被调用
        assert "20260731" in fake.calls["count_limit"]
        assert "20260731" in fake.calls["count_stock"]

    @pytest.mark.asyncio
    async def test_aligned_stock_daily_skips(self) -> None:
        """5 张表都有行 + count 对齐（99 == 99）→ 跳过。"""
        full_set = {"20260731"}
        fake = FakeStockDataSource(
            limit_stocks={"20260731": 99},
            market_index=full_set,
            emotion_daily=full_set,
            sector_daily=full_set,
            stock_daily={"20260731": 99},
        )
        missing = await warmup_mod.find_missing_stock_data_dates(
            fake,
            window_days=15,
            today=date(2026, 7, 31),
            trading_calendar={"20260731"},
        )
        assert "20260731" not in missing, (
            "行数对齐（99 == 99）但仍判定为缺失 → 误报"
        )

    @pytest.mark.asyncio
    async def test_no_limit_stocks_still_triggers_via_has_check(self) -> None:
        """limit_stocks=0（无涨停 / fetcher 失败）触发 has_limit_stocks=False
        → 仍判定为缺失（Stage 1）。

        设计取舍（AGENTS.md §3 业务边界）：
        - 系统无法区分"无涨停日"和"fetcher 失败日"
        - 保守策略：视为缺失 → 下次 warmup 重试 limit_fetcher
        - 若重试仍返回 0 行（真无涨停），fetcher 内部 log info + 不写入
        - 避免"看似完整但实际是空"的死状态
        """
        # 无涨停日或 fetcher 失败日：limit_stocks_daily 0 行
        fake = FakeStockDataSource(
            limit_stocks={},  # 0 行 → has_limit_stocks=False
            market_index={"20260731"},
            emotion_daily={"20260731"},
            sector_daily={"20260731"},
            stock_daily={},
        )
        missing = await warmup_mod.find_missing_stock_data_dates(
            fake,
            window_days=15,
            today=date(2026, 7, 31),
            trading_calendar={"20260731"},
        )
        assert "20260731" in missing, (
            "limit_stocks=0 应在 Stage 1（has_*）被判定为缺失"
        )

    @pytest.mark.asyncio
    async def test_alignment_calls_count_for_verification(self) -> None:
        """行数对齐（99==99）时 count_* 仍被调用一次（用于验证）。

        设计：count 是 Stage 2 的判定依据，has_* 通过后必须查 count 才能
        判断是否对齐。无法"提前短路"——除非有缓存。

        与 has_* 5 张表相比，count_* 只查 2 张（limit_stocks + stock_daily），
        性能开销 < has_* 阶段。
        """
        full_set = {"20260731"}
        fake = FakeStockDataSource(
            limit_stocks={"20260731": 99},
            market_index=full_set,
            emotion_daily=full_set,
            sector_daily=full_set,
            stock_daily={"20260731": 99},
        )
        await warmup_mod.find_missing_stock_data_dates(
            fake,
            window_days=15,
            today=date(2026, 7, 31),
            trading_calendar={"20260731"},
        )
        # Stage 1（5 has_*）+ Stage 2（2 count_*）= 7 调用
        assert len(fake.calls["count_limit"]) == 1
        assert len(fake.calls["count_stock"]) == 1
        assert len(fake.calls["limit"]) == 1  # has_limit_stocks 调用 1 次

    @pytest.mark.asyncio
    async def test_existing_partial_other_tables_still_triggers(self) -> None:
        """回归测试：has_* 任一为 False 仍判定为缺失（Task 16 行为）。"""
        # emotion_daily 缺失（has_emotion_daily=False）
        fake = FakeStockDataSource(
            limit_stocks={"20260731": 99},
            market_index={"20260731"},
            emotion_daily=set(),  # ← 缺失
            sector_daily={"20260731"},
            stock_daily={"20260731": 99},
        )
        missing = await warmup_mod.find_missing_stock_data_dates(
            fake,
            window_days=15,
            today=date(2026, 7, 31),
            trading_calendar={"20260731"},
        )
        assert "20260731" in missing


# ── 4. 硬超时（run_stock_cache_warmup） ──────────────────


class TestWarmupTimeout:
    """run_stock_cache_warmup 必须支持 timeout_seconds；超时后立即返回。"""

    @pytest.mark.asyncio
    async def test_warmup_completes_within_timeout(self) -> None:
        """fetcher 1ms/日 × 3 日 + timeout 5s → 全部完成。"""
        fake = FakeStockDataSource(
            # 3 日全部缺失
            market_index=set(),
            emotion_daily=set(),
            sector_daily=set(),
            stock_daily=set(),
            limit_stocks=set(),
        )

        # 注册快速 pipeline
        async def fast_run(trade_date: str) -> Any:
            await asyncio.sleep(0.001)
            return _make_pipeline_result()

        pipeline = AsyncMock()
        pipeline.run_morning = fast_run
        original = pipeline_mod.get_default_pipeline
        pipeline_mod._DEFAULT_PIPELINE = pipeline  # type: ignore[attr-defined]
        try:
            result = await warmup_mod.run_stock_cache_warmup(
                fake,
                window_days=15,
                today=date(2026, 7, 31),
                timeout_seconds=5.0,
            )
            assert result > 0, f"快速 fetcher 应有 backfill，实际 {result}"
        finally:
            pipeline_mod._DEFAULT_PIPELINE = None  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_warmup_aborts_on_timeout(self, caplog) -> None:
        """fetcher 1s/日 × 3 日 + timeout 0.5s → 触发超时 + warning。"""
        fake = FakeStockDataSource(
            market_index=set(),
            emotion_daily=set(),
            sector_daily=set(),
            stock_daily=set(),
            limit_stocks=set(),
        )

        async def slow_run(trade_date: str) -> Any:
            await asyncio.sleep(1.0)  # 故意慢
            return _make_pipeline_result()

        pipeline = AsyncMock()
        pipeline.run_morning = slow_run
        pipeline_mod._DEFAULT_PIPELINE = pipeline  # type: ignore[attr-defined]
        try:
            with caplog.at_level(logging.WARNING):
                start = asyncio.get_event_loop().time()
                result = await warmup_mod.run_stock_cache_warmup(
                    fake,
                    window_days=15,
                    today=date(2026, 7, 31),
                    timeout_seconds=0.5,
                )
                elapsed = asyncio.get_event_loop().time() - start

            # 验证：超时触发（不应等满 3s）
            assert elapsed < 2.0, (
                f"超时未生效：等待 {elapsed:.2f}s（期望 < 2s）"
            )
            # 验证：warning 包含 "timeout"
            assert any(
                "timeout" in r.message.lower() or "超时" in r.message
                for r in caplog.records
            ), f"未记录 timeout warning: {[r.message for r in caplog.records]}"
        finally:
            pipeline_mod._DEFAULT_PIPELINE = None  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_warmup_no_timeout_default(self) -> None:
        """默认 timeout_seconds=None → 不超时（兼容旧调用方）。"""
        fake = FakeStockDataSource(
            market_index=set(),
            emotion_daily=set(),
            sector_daily=set(),
            stock_daily=set(),
            limit_stocks=set(),
        )

        async def fast_run(trade_date: str) -> Any:
            await asyncio.sleep(0.001)
            return _make_pipeline_result()

        pipeline = AsyncMock()
        pipeline.run_morning = fast_run
        pipeline_mod._DEFAULT_PIPELINE = pipeline  # type: ignore[attr-defined]
        try:
            # 不传 timeout_seconds → 不应抛 TimeoutError
            result = await warmup_mod.run_stock_cache_warmup(
                fake,
                window_days=15,
                today=date(2026, 7, 31),
            )
            assert result > 0
        finally:
            pipeline_mod._DEFAULT_PIPELINE = None  # type: ignore[attr-defined]


# ── 5. settings 必须有 stock_warmup_timeout_seconds ──────


class TestSettingsHasTimeoutField:
    def test_settings_has_timeout_field(self) -> None:
        """settings.stock_warmup_timeout_seconds 必须存在且默认 ≥ 30s。"""
        assert hasattr(settings, "stock_warmup_timeout_seconds"), (
            "settings 缺 stock_warmup_timeout_seconds 字段"
        )
        assert isinstance(settings.stock_warmup_timeout_seconds, int)
        assert 30 <= settings.stock_warmup_timeout_seconds <= 3600, (
            f"stock_warmup_timeout_seconds 应在 [30, 3600]，"
            f"实际 {settings.stock_warmup_timeout_seconds}"
        )

    def test_warmup_window_days_still_exists(self) -> None:
        """Task 19 不破坏 Task 10 的 window_days 字段。"""
        assert hasattr(settings, "stock_warmup_window_days")
        assert settings.stock_warmup_window_days == 15
