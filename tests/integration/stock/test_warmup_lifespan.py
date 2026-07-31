"""Task 10 集成测试：真实 SQLite + fake pipeline 端到端验证回填。

覆盖：
- run_stock_cache_warmup 与 SqliteStockDataSource / CacheRepository 协同：
  warmup 跑完 → 限 cache 真的被写入
- has_limit_stocks 在真实 SQLite 上的行为：
  - 空表 → False
  - 有行 → True
  - 隔离性：不同 trade_date 互不影响
"""

from __future__ import annotations

import os
from datetime import date
from typing import Any

import pytest

from application.stock import warmup as warmup_mod
from application.stock import pipeline as pipeline_mod
from domain.stock.models import LimitStock
from infrastructure.persistence.database import init_db, reset_connection
from infrastructure.stock.cache_repository import CacheRepository
from infrastructure.stock.sqlite_data_source import SqliteStockDataSource


# ── fixtures ───────────────────────────────────────────────


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_warmup_integration.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()
    if db_path.exists():
        os.unlink(db_path)


def _make_pipeline_result(written: int = 1) -> Any:
    class _R:
        def __init__(self) -> None:
            self.phase = "morning"
            self.written = written
            self.errors: list[str] = []
            self.duration_ms = 10

    return _R()


class FakePipelineThatWrites:
    """fake pipeline：被调用时往真实 CacheRepository 写一行 limit_stocks_daily。"""

    def __init__(self, repo: CacheRepository) -> None:
        self._repo = repo
        self.calls: list[str] = []

    async def run_morning(self, *, trade_date: str, **_kw: Any) -> Any:
        self.calls.append(trade_date)
        self._repo.upsert_limit_stocks(
            trade_date=trade_date,
            stocks=[
                LimitStock(
                    trade_date=trade_date,
                    stock_code="000001",
                    stock_name="测试股票",
                    limit_type="up",
                    consecutive_boards=1,
                    first_limit_time="10:00:00",
                    last_limit_time="10:00:00",
                    open_count=0,
                    is_valid_limit_up=True,
                )
            ],
        )
        return _make_pipeline_result(written=1)


# ── has_limit_stocks 在真实 SQLite 上 ──────────────────────


class TestHasLimitStocksRealSqlite:
    @pytest.mark.asyncio
    async def test_returns_false_when_table_empty(self, tmp_db):
        from infrastructure.persistence.connection import get_connection

        ds = SqliteStockDataSource(conn=get_connection())
        assert await ds.has_limit_stocks("20260729") is False
        assert await ds.has_limit_stocks("20260728") is False

    @pytest.mark.asyncio
    async def test_returns_true_when_row_exists(self, tmp_db):
        from infrastructure.persistence.connection import get_connection

        conn = get_connection()
        repo = CacheRepository(conn=conn)
        repo.upsert_limit_stocks(
            trade_date="20260729",
            stocks=[
                LimitStock(
                    trade_date="20260729",
                    stock_code="000001",
                    stock_name="测试",
                    limit_type="up",
                    consecutive_boards=1,
                    first_limit_time="10:00:00",
                    last_limit_time="10:00:00",
                    open_count=0,
                    is_valid_limit_up=True,
                )
            ],
        )
        ds = SqliteStockDataSource(conn=conn)
        assert await ds.has_limit_stocks("20260729") is True
        # 隔离：相邻日期仍为 False
        assert await ds.has_limit_stocks("20260728") is False

    @pytest.mark.asyncio
    async def test_idempotent_upsert_does_not_double_count(self, tmp_db):
        """LIMIT 1 + 重复 upsert 同一 trade_date 仍只算 1 行 → has_limit_stocks=True。"""
        from infrastructure.persistence.connection import get_connection

        conn = get_connection()
        repo = CacheRepository(conn=conn)
        stock = LimitStock(
            trade_date="20260729",
            stock_code="000001",
            stock_name="测试",
            limit_type="up",
            consecutive_boards=1,
            first_limit_time="10:00:00",
            last_limit_time="10:00:00",
            open_count=0,
            is_valid_limit_up=True,
        )
        repo.upsert_limit_stocks(trade_date="20260729", stocks=[stock])
        repo.upsert_limit_stocks(trade_date="20260729", stocks=[stock])
        ds = SqliteStockDataSource(conn=conn)
        assert await ds.has_limit_stocks("20260729") is True


# ── run_stock_cache_warmup + 真实 SQLite ──────────────────


class TestWarmupEndToEnd:
    @pytest.mark.asyncio
    async def test_warmup_populates_cache_for_missing_dates(self, tmp_db):
        """冷启动：cache 全空 → warmup 跑完 → limit_stocks_daily 真的有数据。"""
        from infrastructure.persistence.connection import get_connection

        conn = get_connection()
        repo = CacheRepository(conn=conn)
        ds = SqliteStockDataSource(conn=conn)
        pipe = FakePipelineThatWrites(repo=repo)
        pipeline_mod.set_default_pipeline(pipe)

        try:
            # 2026-07-29 是周三；3 天窗口 = 7-27(一), 7-28(二), 7-29(三) 三个工作日
            n = await warmup_mod.run_stock_cache_warmup(
                ds, window_days=3, today=date(2026, 7, 29)
            )
            assert n == 3
            assert pipe.calls == ["20260729", "20260728", "20260727"]
            # 验证 cache 真的被写入
            assert await ds.has_limit_stocks("20260729") is True
            assert await ds.has_limit_stocks("20260728") is True
            assert await ds.has_limit_stocks("20260727") is True
        finally:
            pipeline_mod.set_default_pipeline(None)

    @pytest.mark.asyncio
    async def test_warmup_skips_already_populated_dates(self, tmp_db):
        """已有部分数据：warmup 只回填缺的日期。"""
        from infrastructure.persistence.connection import get_connection

        conn = get_connection()
        repo = CacheRepository(conn=conn)
        ds = SqliteStockDataSource(conn=conn)
        # 预先填充 7-29
        repo.upsert_limit_stocks(
            trade_date="20260729",
            stocks=[
                LimitStock(
                    trade_date="20260729",
                    stock_code="000001",
                    stock_name="测试",
                    limit_type="up",
                    consecutive_boards=1,
                    first_limit_time="10:00:00",
                    last_limit_time="10:00:00",
                    open_count=0,
                    is_valid_limit_up=True,
                )
            ],
        )
        pipe = FakePipelineThatWrites(repo=repo)
        pipeline_mod.set_default_pipeline(pipe)

        try:
            n = await warmup_mod.run_stock_cache_warmup(
                ds, window_days=3, today=date(2026, 7, 29)
            )
            # 7-29 已有 → 只回填 7-28, 7-27
            assert n == 2
            assert pipe.calls == ["20260728", "20260727"]
        finally:
            pipeline_mod.set_default_pipeline(None)
