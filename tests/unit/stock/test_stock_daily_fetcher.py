"""Task D 失败测试：stock_daily_fetcher（腾讯数据源）。

设计要点：
- Task D 把数据源从东财 ``stock_zh_a_hist``（反爬严重，99 股失败 80 只）
  切换到腾讯 ``stock_zh_a_hist_tx``（成功率显著提升）
- 7 类场景：成功 / akshare 错误 / 空 df / 单股 pct_chg 自算 /
  首行无前日 pct_chg=None / close 不变 pct_chg=0 / adapter 协议
- mock ``infrastructure.stock.akshare_client.ak.stock_zh_a_hist_tx``
- 验证 stock_daily 写入字段一致；StockDaily.turnover 映射腾讯 amount 字段
- 简化：只测"1 只股 × 当日"路径；批量 N 股由 fetcher 内部循环
  （测试不验证循环，避免脆弱的 monkeypatch）
- 业务边界：仅"前一日涨停股" + 板块龙头 + 自选股需要 K 线
  （写路径简单起见，fetcher 只处理 limit_stocks_daily 中的股）
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pandas as pd
import pytest

from infrastructure.persistence.database import init_db, reset_connection
from infrastructure.persistence.connection import get_connection


# ── fixtures ──────────────────────────────────────────────


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_stock_daily_fetcher.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()
    if db_path.exists():
        os.unlink(db_path)


def _seed_limit_stocks(repo, trade_date: str) -> None:
    """塞 limit_stocks_daily 一只涨停股，让 fetcher 知道要拉哪只。

    stock_daily_fetcher 的数据源来自"同一天"的 limit_stocks_daily——
    收市后 limit_fetcher 写涨停股列表，stock_daily_fetcher 同步拉这些股
    的当日 K 线（与 limit_stocks_daily 时间对齐）。
    """
    from domain.stock.models import LimitStock

    repo.upsert_limit_stocks(
        trade_date=trade_date,
        stocks=[
            LimitStock(
                trade_date=trade_date, stock_code="000001", stock_name="平安银行",
                limit_type="up", consecutive_boards=1,
                first_limit_time="10:00:00", last_limit_time="10:00:00",
                open_count=0, is_valid_limit_up=True,
            ),
        ],
    )


def _fake_hist_df(prev_close: float, today_close: float) -> pd.DataFrame:
    """ak.stock_zh_a_hist_tx 返回的简化版（按 akshare 实际英文列名）。

    实测列：``['date', 'open', 'close', 'high', 'low', 'volume',
    'turnover', 'amount']``。返回 2 行：前日 + 当日（20260730），
    用于 pct_chg 自算。

    Args:
        prev_close: 前一日 close
        today_close: 当日 close
    """
    return pd.DataFrame(
        [
            {
                "date": "2026-07-29",
                "open": prev_close,
                "close": prev_close,
                "high": prev_close + 0.5,
                "low": prev_close - 0.5,
                "volume": 800_000,
                "turnover": 0.0040,
                "amount": 10_400_000.0,
            },
            {
                "date": "2026-07-30",
                "open": today_close - 0.2,
                "close": today_close,
                "high": today_close + 0.5,
                "low": today_close - 0.5,
                "volume": 1_000_000,
                "turnover": 0.0050,
                "amount": 12_950_000.0,
            },
        ]
    )


# ── TestStockDailyFetcherSuccess ────────────────────────


class TestStockDailyFetcherSuccess:
    """腾讯接口正常 → 写 cache → 读出 stock_daily 行。"""

    @pytest.mark.asyncio
    async def test_writes_stock_daily_with_tx_source(self, tmp_db) -> None:
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.stock_daily_fetcher_adapter import (
            StockDailyFetcherAdapter,
        )

        adapter = StockDailyFetcherAdapter()
        repo = CacheRepository(conn=get_connection())
        # 塞当日涨停股 — fetcher 应拉它的 K 线
        _seed_limit_stocks(repo, trade_date="20260730")

        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            # 前日 close=12.5，当日 close=13.0 → pct_chg=(13-12.5)/12.5*100=4.0%
            mock_ak.stock_zh_a_hist_tx.return_value = _fake_hist_df(
                prev_close=12.5, today_close=13.0
            )
            count = await adapter.run(trade_date="20260730", repo=repo)

        # 1 只股 × 1 天 = 1 行
        assert count == 1

        rows = repo.select_stock_daily(trade_date="20260730")
        assert len(rows) == 1
        r = rows[0]
        assert r.trade_date == "20260730"
        assert r.stock_code == "000001"
        assert r.open == pytest.approx(12.8)  # 13.0 - 0.2
        assert r.close == pytest.approx(13.0)
        assert r.high == pytest.approx(13.5)
        assert r.low == pytest.approx(12.5)
        assert r.volume == pytest.approx(1_000_000)
        # pct_chg 自算：(13 - 12.5) / 12.5 * 100 = 4.0
        assert r.pct_chg == pytest.approx(4.0)
        # turnover 来自腾讯 amount 字段（StockDaily.turnover 是成交额）
        assert r.turnover == pytest.approx(12_950_000.0)


# ── TestStockDailyFetcherFailure ────────────────────────


class TestStockDailyFetcherFailure:
    """腾讯接口抛异常 → 返 0，cache 不写。"""

    @pytest.mark.asyncio
    async def test_akshare_error_returns_zero(self, tmp_db) -> None:
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.stock_daily_fetcher_adapter import (
            StockDailyFetcherAdapter,
        )

        adapter = StockDailyFetcherAdapter()
        repo = CacheRepository(conn=get_connection())
        _seed_limit_stocks(repo, trade_date="20260730")

        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            mock_ak.stock_zh_a_hist_tx.side_effect = ValueError("akshare 失败")
            count = await adapter.run(trade_date="20260730", repo=repo)

        assert count == 0
        rows = repo.select_stock_daily(trade_date="20260730")
        assert rows == []


# ── TestStockDailyFetcherEmpty ─────────────────────────


class TestStockDailyFetcherEmpty:
    """腾讯接口返空 DataFrame → 返 0。"""

    @pytest.mark.asyncio
    async def test_empty_df_returns_zero(self, tmp_db) -> None:
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.stock_daily_fetcher_adapter import (
            StockDailyFetcherAdapter,
        )

        adapter = StockDailyFetcherAdapter()
        repo = CacheRepository(conn=get_connection())
        _seed_limit_stocks(repo, trade_date="20260730")

        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            mock_ak.stock_zh_a_hist_tx.return_value = pd.DataFrame()
            count = await adapter.run(trade_date="20260730", repo=repo)

        assert count == 0


# ── TestStockDailyFetcherPctChgCalc ────────────────────


class TestStockDailyFetcherPctChgCalc:
    """Task D：腾讯接口不返回 pct_chg，必须自己算。"""

    @pytest.mark.asyncio
    async def test_pct_chg_calculated_from_prev_close(self, tmp_db) -> None:
        """前日 close=10，当日 close=11 → pct_chg=10.0%。"""
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.stock_daily_fetcher_adapter import (
            StockDailyFetcherAdapter,
        )

        adapter = StockDailyFetcherAdapter()
        repo = CacheRepository(conn=get_connection())
        _seed_limit_stocks(repo, trade_date="20260730")

        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            mock_ak.stock_zh_a_hist_tx.return_value = _fake_hist_df(
                prev_close=10.0, today_close=11.0
            )
            await adapter.run(trade_date="20260730", repo=repo)

        rows = repo.select_stock_daily(trade_date="20260730")
        assert len(rows) == 1
        # (11 - 10) / 10 * 100 = 10.0
        assert rows[0].pct_chg == pytest.approx(10.0)

    @pytest.mark.asyncio
    async def test_pct_chg_none_when_only_one_row(self, tmp_db) -> None:
        """只返回 1 天 K 线（无前日）→ pct_chg=None。"""
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.stock_daily_fetcher_adapter import (
            StockDailyFetcherAdapter,
        )

        adapter = StockDailyFetcherAdapter()
        repo = CacheRepository(conn=get_connection())
        _seed_limit_stocks(repo, trade_date="20260730")

        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            # 只返回 1 行（当日，无前日）
            mock_ak.stock_zh_a_hist_tx.return_value = pd.DataFrame(
                [
                    {
                        "date": "2026-07-30",
                        "open": 13.0,
                        "close": 13.0,
                        "high": 13.5,
                        "low": 12.8,
                        "volume": 1_000_000,
                        "turnover": 0.005,
                        "amount": 12_950_000.0,
                    }
                ]
            )
            await adapter.run(trade_date="20260730", repo=repo)

        rows = repo.select_stock_daily(trade_date="20260730")
        assert len(rows) == 1
        # 首行无前日 close → pct_chg=None
        assert rows[0].pct_chg is None

    @pytest.mark.asyncio
    async def test_pct_chg_zero_when_close_unchanged(self, tmp_db) -> None:
        """前日 close=10，当日 close=10 → pct_chg=0.0（非 None）。"""
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.stock_daily_fetcher_adapter import (
            StockDailyFetcherAdapter,
        )

        adapter = StockDailyFetcherAdapter()
        repo = CacheRepository(conn=get_connection())
        _seed_limit_stocks(repo, trade_date="20260730")

        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            mock_ak.stock_zh_a_hist_tx.return_value = _fake_hist_df(
                prev_close=10.0, today_close=10.0
            )
            await adapter.run(trade_date="20260730", repo=repo)

        rows = repo.select_stock_daily(trade_date="20260730")
        assert len(rows) == 1
        # close 不变 → pct_chg=0.0
        assert rows[0].pct_chg == 0.0


# ── TestStockDailyFetcherAdapter ────────────────────────


class TestStockDailyFetcherAdapter:
    """StockDailyFetcherAdapter 走 Fetcher 协议。"""

    @pytest.mark.asyncio
    async def test_adapter_runs_through_pipeline(self, tmp_db) -> None:
        from infrastructure.stock.akshare_client import AkshareClient
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.stock_daily_fetcher_adapter import (
            StockDailyFetcherAdapter,
        )

        adapter = StockDailyFetcherAdapter(client=AkshareClient())
        # 协议 duck-type 校验
        assert adapter.name == "stock_daily_fetcher"
        assert callable(adapter.run)

        repo = CacheRepository(conn=get_connection())
        _seed_limit_stocks(repo, trade_date="20260730")
        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            mock_ak.stock_zh_a_hist_tx.return_value = _fake_hist_df(
                prev_close=12.5, today_close=13.0
            )
            written = await adapter.run(trade_date="20260730", repo=repo)

        assert written == 1
