"""Task 13 失败测试：market_index_fetcher fetcher——大盘指数。

覆盖：
- 正常路径：akshare 返 3 个指数（sh/sz/cyb）DataFrame → 写 cache → 返回条数
- 错误路径：akshare 抛具体异常 → 任务不抛异常，返回 0
- 空数据：akshare 返空 DataFrame → 不写库，返回 0

不访问真实网络——mock akshare。
运行前 infrastructure/stock/market_index_fetcher.py 不存在，
本测试在 Step 1 应全部失败（ImportError / AttributeError）。
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

import pandas as pd
import pytest

from infrastructure.persistence.connection import get_connection
from infrastructure.persistence.database import init_db, reset_connection


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_market_index_fetcher.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()
    if db_path.exists():
        os.unlink(db_path)


def _fake_index_df() -> pd.DataFrame:
    """模拟 akshare 拉到的 3 个指数 DataFrame。

    字段命名参考 akshare.stock_zh_index_daily 实际返回列名；
    date 列以字符串 YYYY-MM-DD 形式给出。
    """
    return pd.DataFrame(
        [
            {"date": "2026-07-30", "open": 3500.0, "close": 3520.0,
             "high": 3530.0, "low": 3490.0, "volume": 4.5e10, "pct_chg": 0.5},
            {"date": "2026-07-30", "open": 11800.0, "close": 11850.0,
             "high": 11900.0, "low": 11750.0, "volume": 5.0e10, "pct_chg": 0.4},
            {"date": "2026-07-30", "open": 2400.0, "close": 2410.0,
             "high": 2415.0, "low": 2395.0, "volume": 1.8e10, "pct_chg": 0.3},
        ]
    )


def _mock_per_symbol(mock_ak: Any) -> None:
    """对每个 symbol 返回不同 df，3 次调用得到 3 个不同指数。"""

    def _by_symbol(symbol: str) -> pd.DataFrame:
        rows = {
            "sh000001": {"close": 3520.0, "open": 3500.0, "high": 3530.0,
                         "low": 3490.0, "volume": 4.5e10, "pct_chg": 0.5},
            "sz399001": {"close": 11850.0, "open": 11800.0, "high": 11900.0,
                         "low": 11750.0, "volume": 5.0e10, "pct_chg": 0.4},
            "sz399006": {"close": 2410.0, "open": 2400.0, "high": 2415.0,
                         "low": 2395.0, "volume": 1.8e10, "pct_chg": 0.3},
        }
        r = rows.get(symbol, rows["sh000001"])
        return pd.DataFrame(
            [{"date": "2026-07-30", **r}]
        )

    mock_ak.stock_zh_index_daily.side_effect = _by_symbol


class TestMarketIndexFetcherSuccess:
    """正常路径：3 个指数落库。"""

    @pytest.mark.asyncio
    async def test_writes_three_indices_to_cache(self, tmp_db) -> None:
        """akshare 返 3 行 → cache 写入 3 行 → 读出也是 3 行。"""
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.market_index_fetcher import run

        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            # 3 个 mock 调用对应 3 个不同 symbol → 3 个不同指数
            _mock_per_symbol(mock_ak)
            repo = CacheRepository(get_connection(tmp_db))
            count = await run("20260730", repo)

        assert count == 3
        rows = repo.select_market_index(trade_date="20260730")
        assert len(rows) == 3
        # 三只指数 close 应该都能读到（各不相同）
        closes = sorted(r.close for r in rows if r.close is not None)
        assert closes == [2410.0, 3520.0, 11850.0]


class TestMarketIndexFetcherFailure:
    """错误路径：akshare 抛具体异常时 fetcher 不抛、不脏写。"""

    @pytest.mark.asyncio
    async def test_returns_zero_on_akshare_error(self, tmp_db) -> None:
        """akshare 抛 requests.RequestException → 包装→fetcher 返回 0。"""
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.market_index_fetcher import run

        repo = CacheRepository(get_connection(tmp_db))
        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            mock_ak.stock_zh_index_daily.side_effect = ValueError("network down")
            count = await run("20260730", repo)
        assert count == 0
        # 确认 cache 没被脏写
        assert repo.select_market_index(trade_date="20260730") == []


class TestMarketIndexFetcherEmpty:
    """空数据：akshare 返空 DataFrame。"""

    @pytest.mark.asyncio
    async def test_returns_zero_on_empty_dataframe(self, tmp_db) -> None:
        """akshare 返空 df → fetcher 返回 0，不写库。"""
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.market_index_fetcher import run

        repo = CacheRepository(get_connection(tmp_db))
        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            mock_ak.stock_zh_index_daily.return_value = pd.DataFrame()
            count = await run("20260730", repo)
        assert count == 0
        assert repo.select_market_index(trade_date="20260730") == []


class TestMarketIndexFetcherAdapter:
    """Fetcher 协议适配器——包装 fetch_market_index + upsert_market_index。

    注：fetcher run 函数的接口形态可能为：
        async def run(trade_date: str, repo: CacheRepository) -> int
    也可能由 adapter 单独提供。本测试在 Step 1 期望全部失败。
    """

    @pytest.mark.asyncio
    async def test_adapter_runs_through_pipeline(self, tmp_db) -> None:
        """MarketIndexFetcherAdapter 走 Fetcher 协议：run(trade_date=, repo=)。"""
        from infrastructure.stock.akshare_client import AkshareClient
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.market_index_fetcher_adapter import (
            MarketIndexFetcherAdapter,
        )

        adapter = MarketIndexFetcherAdapter(client=AkshareClient())
        # 协议 duck-type 校验：name + run 方法都在
        assert adapter.name == "market_index_fetcher"
        assert callable(adapter.run)

        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            _mock_per_symbol(mock_ak)
            repo = CacheRepository(get_connection(tmp_db))
            written = await adapter.run(trade_date="20260730", repo=repo)

        assert written == 3
