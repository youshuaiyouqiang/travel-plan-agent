"""Task 15 失败测试：stock_daily_fetcher（个股 K 线 fetcher）。

设计要点：
- 4 类场景：成功 / akshare 错误 / 空 df / adapter 协议
- mock `infrastructure.stock.akshare_client.ak.stock_zh_a_hist`
- 验证 stock_daily 写入字段一致
- 简化：只测"1 只股 × 1 天"路径；批量 N 股由 fetcher 内部循环
  （测试不验证循环，避免脆弱的 monkeypatch）
- 业务边界：仅"前一日涨停股" + 板块龙头 + 自选股需要 K 线
  （写路径简单起见，Task 15 fetcher 只处理 limit_stocks_daily 中的股）
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


def _fake_hist_df() -> pd.DataFrame:
    """ak.stock_zh_a_hist 返回的简化版（按 akshare 实际列名）。"""
    return pd.DataFrame(
        [
            {
                "日期": "2026-07-30",
                "开盘": 12.50,
                "收盘": 13.00,
                "最高": 13.20,
                "最低": 12.30,
                "成交量": 1000000,
                "成交额": 12.95e6,
                "涨跌幅": 4.0,
            },
        ]
    )


# ── TestStockDailyFetcherSuccess ────────────────────────


class TestStockDailyFetcherSuccess:
    """akshare 正常 → 写 cache → 读出 stock_daily 行。"""

    @pytest.mark.asyncio
    async def test_writes_stock_daily(self, tmp_db) -> None:
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.stock_daily_fetcher_adapter import (
            StockDailyFetcherAdapter,
        )

        adapter = StockDailyFetcherAdapter()
        repo = CacheRepository(conn=get_connection())
        # 塞当日涨停股 — fetcher 应拉它的 K 线
        _seed_limit_stocks(repo, trade_date="20260730")

        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            mock_ak.stock_zh_a_hist.return_value = _fake_hist_df()
            count = await adapter.run(trade_date="20260730", repo=repo)

        # 1 只股 × 1 天 = 1 行
        assert count == 1

        rows = repo.select_stock_daily(trade_date="20260730")
        assert len(rows) == 1
        r = rows[0]
        assert r.trade_date == "20260730"
        assert r.stock_code == "000001"
        assert r.open == pytest.approx(12.50)
        assert r.close == pytest.approx(13.00)
        assert r.high == pytest.approx(13.20)
        assert r.low == pytest.approx(12.30)
        assert r.volume == pytest.approx(1000000)
        assert r.pct_chg == pytest.approx(4.0)
        # turnover 来自 akshare 成交额
        assert r.turnover == pytest.approx(12.95e6)


# ── TestStockDailyFetcherFailure ────────────────────────


class TestStockDailyFetcherFailure:
    """akshare 抛异常 → 返 0，cache 不写。"""

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
            mock_ak.stock_zh_a_hist.side_effect = ValueError("akshare 失败")
            count = await adapter.run(trade_date="20260730", repo=repo)

        assert count == 0
        rows = repo.select_stock_daily(trade_date="20260730")
        assert rows == []


# ── TestStockDailyFetcherEmpty ─────────────────────────


class TestStockDailyFetcherEmpty:
    """akshare 返空 DataFrame → 返 0。"""

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
            mock_ak.stock_zh_a_hist.return_value = pd.DataFrame()
            count = await adapter.run(trade_date="20260730", repo=repo)

        assert count == 0


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
            mock_ak.stock_zh_a_hist.return_value = _fake_hist_df()
            written = await adapter.run(trade_date="20260730", repo=repo)

        assert written == 1
