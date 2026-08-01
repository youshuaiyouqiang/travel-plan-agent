"""Task 14 失败测试：sector_daily_fetcher（与 market_index_fetcher 同构）。

设计要点：
- 4 类场景：成功 / akshare 错误 / 空 df / adapter 协议
- mock `infrastructure.stock.akshare_client.ak.stock_board_industry_name_em`
- 验证写入 sector_daily 后从 cache_repository 读出字段一致
- limit_up_count / leading_stock_codes 在 Task 14 阶段填 0 / []；
  后续可由板块龙头 fetcher 二次加工（避免 N+1 调 akshare）
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
    db_path = tmp_path / "test_sector_fetcher.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()
    if db_path.exists():
        os.unlink(db_path)


def _fake_sectors_df() -> pd.DataFrame:
    """ak.stock_board_industry_name_em 返回的简化版（按 akshare 实际列名）。"""
    return pd.DataFrame(
        [
            {
                "板块名称": "半导体",
                "板块代码": "BK1004",
                "涨跌幅": 2.35,
                "领涨股": "中芯国际",
                "领涨股代码": "688981",
            },
            {
                "板块名称": "新能源",
                "板块代码": "BK1005",
                "涨跌幅": -1.20,
                "领涨股": "宁德时代",
                "领涨股代码": "300750",
            },
            {
                "板块名称": "房地产",
                "板块代码": "BK1006",
                "涨跌幅": 0.50,
                "领涨股": "万科A",
                "领涨股代码": "000002",
            },
        ]
    )


# ── TestSectorFetcherSuccess ─────────────────────────────


class TestSectorFetcherSuccess:
    """akshare 正常 → 写 cache → 读出 sector_daily 行。"""

    @pytest.mark.asyncio
    async def test_writes_sector_daily(self, tmp_db) -> None:
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.sector_daily_fetcher_adapter import (
            SectorDailyFetcherAdapter,
        )

        adapter = SectorDailyFetcherAdapter()
        repo = CacheRepository(conn=get_connection())
        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            mock_ak.stock_board_industry_name_em.return_value = _fake_sectors_df()
            count = await adapter.run(trade_date="20260730", repo=repo)

        # 3 个板块全写入
        assert count == 3

        rows = repo.select_sector_daily(trade_date="20260730")
        assert len(rows) == 3
        # 按 sector_code 索引方便断言
        by_code = {r.sector_code: r for r in rows}
        assert "BK1004" in by_code
        sem = by_code["BK1004"]
        assert sem.trade_date == "20260730"
        assert sem.sector_name == "半导体"
        assert sem.pct_chg == pytest.approx(2.35)
        # leading_stock_codes 是 JSON 数组字符串
        assert sem.leading_stock_codes == ["688981"]
        # limit_up_count 在 Task 14 阶段填 0
        assert sem.limit_up_count == 0


# ── TestSectorFetcherFailure ─────────────────────────────


class TestSectorFetcherFailure:
    """akshare 抛异常 → 返 0，cache 不写。"""

    @pytest.mark.asyncio
    async def test_akshare_error_returns_zero(self, tmp_db) -> None:
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.sector_daily_fetcher_adapter import (
            SectorDailyFetcherAdapter,
        )

        adapter = SectorDailyFetcherAdapter()
        repo = CacheRepository(conn=get_connection())
        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            mock_ak.stock_board_industry_name_em.side_effect = ValueError("akshare 失败")
            count = await adapter.run(trade_date="20260730", repo=repo)

        assert count == 0
        rows = repo.select_sector_daily(trade_date="20260730")
        assert rows == []


# ── TestSectorFetcherEmpty ───────────────────────────────


class TestSectorFetcherEmpty:
    """akshare 返空 DataFrame → 返 0。"""

    @pytest.mark.asyncio
    async def test_empty_df_returns_zero(self, tmp_db) -> None:
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.sector_daily_fetcher_adapter import (
            SectorDailyFetcherAdapter,
        )

        adapter = SectorDailyFetcherAdapter()
        repo = CacheRepository(conn=get_connection())
        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            mock_ak.stock_board_industry_name_em.return_value = pd.DataFrame()
            count = await adapter.run(trade_date="20260730", repo=repo)

        assert count == 0


# ── TestSectorFetcherAdapter ─────────────────────────────


class TestSectorFetcherAdapter:
    """SectorDailyFetcherAdapter 走 Fetcher 协议。"""

    @pytest.mark.asyncio
    async def test_adapter_runs_through_pipeline(self, tmp_db) -> None:
        from infrastructure.stock.akshare_client import AkshareClient
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.sector_daily_fetcher_adapter import (
            SectorDailyFetcherAdapter,
        )

        adapter = SectorDailyFetcherAdapter(client=AkshareClient())
        # 协议 duck-type 校验
        assert adapter.name == "sector_daily_fetcher"
        assert callable(adapter.run)

        repo = CacheRepository(conn=get_connection())
        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            mock_ak.stock_board_industry_name_em.return_value = _fake_sectors_df()
            written = await adapter.run(trade_date="20260730", repo=repo)

        assert written == 3
