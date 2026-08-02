"""Task 20 失败测试：stock_fetch_log 跟踪个股抓取状态。

Issue 1-C（重启后无谓重抓）：
- 现状：stock_daily_fetcher 对 99 只涨停股串行调 akshare，akshare
  高失败率（1-2s/fail）→ 19 只失败 + 80 只成功（~3 分钟）。
- 重启后 warmup 仍会调全 99 只；前次成功的 80 只再走一遍 akshare，
  即使 stock_daily 表里数据是齐的。
- 修复：引入 ``stock_fetch_log`` 表记录每只股的最近抓取状态。
  stock_daily_fetcher 在抓取前先查 log，若 24h 内 status=success
  则跳过；抓取后写入 log。这样重启后只抓 19 只失败股，~36s 完成。

覆盖（均失败先行 → 实现后变绿）：
- TestMigrationV22: v022 迁移创建 stock_fetch_log 表 + 索引
- TestCacheRepositoryFetchLog: CacheRepository 写读接口
  - test_record_fetch_inserts_row
  - test_record_fetch_upserts_existing
  - test_is_recently_succeeded_true
  - test_is_recently_succeeded_false_outside_ttl
  - test_is_recently_succeeded_false_for_failed_status
- TestStockFetchLogPortContract: domain 端口契约
- TestStockDailyFetcherSkipsRecentlyFetched: fetcher 跳过最近成功股
  - test_skips_when_log_says_recent_success
  - test_fetches_when_log_says_old_or_missing
  - test_records_success_after_fetch
  - test_records_failure_after_akshare_error
- TestWarmupFasterOnReboot: 集成场景
  - 99 股中 80 已 success 在 log → warmup 只触发 19 次 akshare
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

import pandas as pd
import pytest

from domain.stock.models import LimitStock, StockDaily
from infrastructure.persistence.connection import get_connection
from infrastructure.persistence.database import init_db, reset_connection
from infrastructure.persistence.migrations.runner import get_migration_status
from infrastructure.stock import stock_daily_fetcher as fetcher_mod
from infrastructure.stock.akshare_client import AkshareFetchError
from infrastructure.stock.cache_repository import CacheRepository, _validate_table


# ── fixtures ──────────────────────────────────────────────


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_fetch_log.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()
    if db_path.exists():
        os.unlink(db_path)


# ── helpers ───────────────────────────────────────────────


def _make_limit_stocks(n: int) -> list[LimitStock]:
    return [
        LimitStock(
            trade_date="20260731",
            stock_code=f"{600000 + i:06d}",
            stock_name=f"测试股{i}",
            limit_type="limit_up",
            consecutive_boards=1,
            first_limit_time="10:00:00",
            last_limit_time="10:00:00",
            open_count=0,
            is_valid_limit_up=True,
        )
        for i in range(n)
    ]


def _make_daily_row(stock_code: str, trade_date: str = "20260731") -> StockDaily:
    return StockDaily(
        trade_date=trade_date,
        stock_code=stock_code,
        open=10.0,
        close=10.5,
        high=10.8,
        low=9.9,
        volume=1_000_000,
        pct_chg=5.0,
        turnover=2.5,
    )


# ── 1. 迁移 v022：stock_fetch_log 表 ───────────────────────


class TestMigrationV22:
    def test_migration_creates_stock_fetch_log(self, tmp_db) -> None:
        """v022 迁移必须创建 stock_fetch_log 表。"""
        conn = get_connection()
        # 表存在
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='stock_fetch_log'"
        ).fetchone()
        assert row is not None, "v022 应创建 stock_fetch_log 表"

    def test_migration_creates_index(self, tmp_db) -> None:
        """v022 迁移必须创建 last_attempt_at 索引。"""
        conn = get_connection()
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND tbl_name='stock_fetch_log'"
        ).fetchone()
        assert row is not None, "v022 应创建 stock_fetch_log 索引"

    def test_migration_registered_in_schema(self, tmp_db) -> None:
        """v022 必须在 schema_migrations 中。"""
        status = get_migration_status()
        applied_versions = {m["version"] for m in status["applied"]}
        assert 22 in applied_versions

    def test_table_in_allowed_tables_whitelist(self) -> None:
        """ALLOWED_TABLES 必须含 stock_fetch_log。"""
        # 静态引用检查（避免运行期 _validate_table 与白名单漂移）
        from infrastructure.stock.cache_repository import ALLOWED_TABLES

        assert "stock_fetch_log" in ALLOWED_TABLES, (
            "ALLOWED_TABLES 白名单缺 stock_fetch_log"
        )

    def test_table_validates_via_validate_table(self) -> None:
        """_validate_table 接受 stock_fetch_log。"""
        _validate_table("stock_fetch_log")  # 不抛


# ── 2. CacheRepository 写读接口 ─────────────────────────


class TestCacheRepositoryFetchLog:
    def test_record_fetch_inserts_row(self, tmp_db) -> None:
        """首次 record_fetch 插入一行。"""
        repo = CacheRepository(conn=get_connection())
        repo.record_fetch(
            trade_date="20260731",
            stock_code="600000",
            table_name="stock_daily",
            status="success",
        )
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM stock_fetch_log "
            "WHERE trade_date=? AND stock_code=? AND table_name=?",
            ("20260731", "600000", "stock_daily"),
        ).fetchone()
        assert row is not None
        assert row["status"] == "success"
        assert row["error_message"] is None

    def test_record_fetch_upserts_existing(self, tmp_db) -> None:
        """再次 record_fetch 覆盖（更新 last_attempt_at 和 status）。"""
        repo = CacheRepository(conn=get_connection())
        repo.record_fetch(
            trade_date="20260731",
            stock_code="600000",
            table_name="stock_daily",
            status="failed",
            error_message="akshare timeout",
        )
        repo.record_fetch(
            trade_date="20260731",
            stock_code="600000",
            table_name="stock_daily",
            status="success",
        )
        conn = get_connection()
        row = conn.execute(
            "SELECT status, error_message FROM stock_fetch_log "
            "WHERE trade_date=? AND stock_code=? AND table_name=?",
            ("20260731", "600000", "stock_daily"),
        ).fetchone()
        assert row["status"] == "success"
        assert row["error_message"] is None, "成功记录后 error_message 必须清空"

    def test_is_recently_succeeded_true(self, tmp_db) -> None:
        """记录 success → is_recently_succeeded 24h 内 True。"""
        repo = CacheRepository(conn=get_connection())
        repo.record_fetch(
            trade_date="20260731",
            stock_code="600000",
            table_name="stock_daily",
            status="success",
        )
        assert repo.is_recently_succeeded(
            trade_date="20260731",
            stock_code="600000",
            table_name="stock_daily",
            within_seconds=86400,
        ) is True

    def test_is_recently_succeeded_false_outside_ttl(self, tmp_db) -> None:
        """记录 last_attempt_at 在 ttl 之前 → False。"""
        conn = get_connection()
        # 手工插入一条 25 小时前的记录
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        conn.execute(
            "INSERT INTO stock_fetch_log "
            "(trade_date, stock_code, table_name, status, last_attempt_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("20260731", "600000", "stock_daily", "success", old_ts),
        )
        conn.commit()
        repo = CacheRepository(conn=get_connection())
        assert repo.is_recently_succeeded(
            trade_date="20260731",
            stock_code="600000",
            table_name="stock_daily",
            within_seconds=86400,
        ) is False

    def test_is_recently_succeeded_false_for_failed_status(self, tmp_db) -> None:
        """status=failed 即使在 24h 内也返 False（允许重试）。"""
        repo = CacheRepository(conn=get_connection())
        repo.record_fetch(
            trade_date="20260731",
            stock_code="600000",
            table_name="stock_daily",
            status="failed",
        )
        assert repo.is_recently_succeeded(
            trade_date="20260731",
            stock_code="600000",
            table_name="stock_daily",
            within_seconds=86400,
        ) is False

    def test_is_recently_succeeded_false_when_no_log(self, tmp_db) -> None:
        """无 log 行 → False（必须抓取）。"""
        repo = CacheRepository(conn=get_connection())
        assert repo.is_recently_succeeded(
            trade_date="20260731",
            stock_code="600000",
            table_name="stock_daily",
            within_seconds=86400,
        ) is False


# ── 3. 端口契约 ──────────────────────────────────────────


class TestStockFetchLogPortContract:
    """domain 端口必须声明 is_recently_succeeded / record_fetch。"""

    def test_port_exists(self) -> None:
        from domain.stock.ports import StockFetchLogPort

        assert StockFetchLogPort is not None

    def test_is_recently_succeeded_signature(self) -> None:
        from domain.stock.ports import StockFetchLogPort

        import inspect

        method = getattr(StockFetchLogPort, "is_recently_succeeded", None)
        assert method is not None
        sig = inspect.signature(method)
        params = list(sig.parameters.keys())
        assert "trade_date" in params
        assert "stock_code" in params
        assert "table_name" in params
        assert "within_seconds" in params

    def test_record_fetch_signature(self) -> None:
        from domain.stock.ports import StockFetchLogPort

        import inspect

        method = getattr(StockFetchLogPort, "record_fetch", None)
        assert method is not None
        sig = inspect.signature(method)
        params = list(sig.parameters.keys())
        assert "trade_date" in params
        assert "stock_code" in params
        assert "table_name" in params
        assert "status" in params


# ── 4. stock_daily_fetcher 集成 stock_fetch_log ─────────


class TestStockDailyFetcherSkipsRecentlyFetched:
    """fetcher 应在抓取前查 log，跳过 24h 内成功的股票。"""

    @pytest.mark.asyncio
    async def test_skips_when_log_says_recent_success(self, tmp_db) -> None:
        """log 标记 success → 不调 akshare。"""
        repo = CacheRepository(conn=get_connection())
        repo.upsert_limit_stocks(
            trade_date="20260731", stocks=_make_limit_stocks(3)
        )
        # 标记 600000 成功、600001 失败、600002 无记录
        repo.record_fetch(
            trade_date="20260731",
            stock_code="600000",
            table_name="stock_daily",
            status="success",
        )
        repo.record_fetch(
            trade_date="20260731",
            stock_code="600001",
            table_name="stock_daily",
            status="failed",
        )

        # mock akshare: 只 600001 和 600002 应被调
        # Task D：腾讯接口 symbol 是 "sh600000" 格式（带前缀）
        called_codes: list[str] = []

        def _slow_hist(*_args: Any, **_kwargs: Any) -> pd.DataFrame:
            # 腾讯接口调用：stock_zh_a_hist_tx(symbol="sh600000", ...)
            actual = _kwargs.get("symbol") or (_args[0] if _args else None)
            assert actual is not None
            called_codes.append(str(actual))
            # 返回 2 行便于 fetcher 取到 trade_date 当日行
            return pd.DataFrame(
                [
                    {"date": "2026-07-30", "open": 10.0, "close": 10.0,
                     "high": 10.2, "low": 9.8, "volume": 800_000,
                     "turnover": 0.004, "amount": 8_000_000.0},
                    {"date": "2026-07-31", "open": 10.0, "close": 10.5,
                     "high": 10.8, "low": 9.9, "volume": 1_000_000,
                     "turnover": 0.005, "amount": 10_500_000.0},
                ]
            )

        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            mock_ak.stock_zh_a_hist_tx.side_effect = _slow_hist
            written = await fetcher_mod.run("20260731", repo)

        # 600000 跳过；600001 重抓 → success（之前 failed）；600002 抓 → success
        # 注意：腾讯接口 symbol 带 sh 前缀
        assert "sh600000" not in called_codes, "log 标 success 的股不应调 akshare"
        assert "sh600001" in called_codes, "log 标 failed 的股应重抓"
        assert "sh600002" in called_codes, "无 log 的股应抓取"
        assert len(called_codes) == 2
        # 实际：fetcher 只 upsert 抓到的 2 行（600001 + 600002）
        assert written == 2

    @pytest.mark.asyncio
    async def test_records_success_after_fetch(self, tmp_db) -> None:
        """抓取成功后写 log。"""
        repo = CacheRepository(conn=get_connection())
        repo.upsert_limit_stocks(
            trade_date="20260731", stocks=_make_limit_stocks(1)
        )

        def _hist(*_args: Any, **_kwargs: Any) -> pd.DataFrame:
            return pd.DataFrame(
                [
                    {"date": "2026-07-30", "open": 10.0, "close": 10.0,
                     "high": 10.2, "low": 9.8, "volume": 800_000,
                     "turnover": 0.004, "amount": 8_000_000.0},
                    {"date": "2026-07-31", "open": 10.0, "close": 10.5,
                     "high": 10.8, "low": 9.9, "volume": 1_000_000,
                     "turnover": 0.005, "amount": 10_500_000.0},
                ]
            )

        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            mock_ak.stock_zh_a_hist_tx.side_effect = _hist
            await fetcher_mod.run("20260731", repo)

        # 验证 log 已写入
        assert repo.is_recently_succeeded(
            trade_date="20260731",
            stock_code="600000",
            table_name="stock_daily",
            within_seconds=86400,
        ) is True

    @pytest.mark.asyncio
    async def test_records_failure_after_akshare_error(self, tmp_db) -> None:
        """akshare 抛 AkshareFetchError → log 记 failed。"""
        repo = CacheRepository(conn=get_connection())
        repo.upsert_limit_stocks(
            trade_date="20260731", stocks=_make_limit_stocks(1)
        )

        def _hist(*_args: Any, **_kwargs: Any) -> pd.DataFrame:
            raise AkshareFetchError("akshare 异常")

        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            mock_ak.stock_zh_a_hist_tx.side_effect = _hist
            written = await fetcher_mod.run("20260731", repo)

        assert written == 0
        # log 应记 failed（不是 success）
        assert repo.is_recently_succeeded(
            trade_date="20260731",
            stock_code="600000",
            table_name="stock_daily",
            within_seconds=86400,
        ) is False
        # 通过 SQL 直接查 status
        row = get_connection().execute(
            "SELECT status, error_message FROM stock_fetch_log "
            "WHERE trade_date=? AND stock_code=? AND table_name=?",
            ("20260731", "600000", "stock_daily"),
        ).fetchone()
        assert row is not None
        assert row["status"] == "failed"
        assert "akshare 异常" in (row["error_message"] or "")


# ── 5. 集成：99 股 80 已 success → 只重抓 19 只 ────────


class TestWarmupFasterOnReboot:
    @pytest.mark.asyncio
    async def test_partial_log_skips_already_fetched_stocks(self, tmp_db) -> None:
        """99 只涨停股中 80 只 log 标 success → fetcher 只调 19 次 akshare。

        业务价值：重启后 warmup 节省 ~80% akshare 调用（从 99 降到 19），
        极端情况下 warmup 整体耗时从 ~3 分钟降到 ~36s。
        """
        repo = CacheRepository(conn=get_connection())
        # 99 只涨停股
        limit_stocks = _make_limit_stocks(99)
        repo.upsert_limit_stocks(trade_date="20260731", stocks=limit_stocks)

        # 80 只标 success（code 600000..600079）
        for i in range(80):
            repo.record_fetch(
                trade_date="20260731",
                stock_code=f"{600000 + i:06d}",
                table_name="stock_daily",
                status="success",
            )

        called_codes: list[str] = []

        def _hist(*_args: Any, **_kwargs: Any) -> pd.DataFrame:
            # Task D：腾讯接口 symbol 是 "sh600000" 格式（带前缀）
            actual = _kwargs.get("symbol") or (_args[0] if _args else None)
            assert actual is not None
            called_codes.append(str(actual))
            # 返回 2 行便于 fetcher 取到 trade_date 当日行
            return pd.DataFrame(
                [
                    {"date": "2026-07-30", "open": 10.0, "close": 10.0,
                     "high": 10.2, "low": 9.8, "volume": 800_000,
                     "turnover": 0.004, "amount": 8_000_000.0},
                    {"date": "2026-07-31", "open": 10.0, "close": 10.5,
                     "high": 10.8, "low": 9.9, "volume": 1_000_000,
                     "turnover": 0.005, "amount": 10_500_000.0},
                ]
            )

        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            mock_ak.stock_zh_a_hist_tx.side_effect = _hist
            written = await fetcher_mod.run("20260731", repo)

        # 只调 19 次（80..98）
        assert len(called_codes) == 19, (
            f"应只重抓 19 只（99-80），实际 {len(called_codes)}"
        )
        # 写入 19 行
        assert written == 19
        # log 中这 19 只也应被记 success
        for i in range(80, 99):
            code = f"{600000 + i:06d}"
            assert repo.is_recently_succeeded(
                trade_date="20260731",
                stock_code=code,
                table_name="stock_daily",
                within_seconds=86400,
            ) is True
