"""Task C 失败测试：sector_daily_fetcher（同花顺数据源）。

设计要点：
- Task C 把数据源从东财 ``stock_board_industry_name_em``（反爬失败）
  切换到同花顺 ``stock_board_industry_name_ths`` + ``stock_board_industry_index_ths``
- 6 类场景：成功 / 板块列表失败 / 空板块列表 / 单板块 K 线失败 /
  pct_chg 自算 / 首行无前日 pct_chg=None
- mock ``infrastructure.stock.akshare_client.ak`` 的两个函数
- mock ``time.sleep`` 避免反爬 sleep 拖慢单测（0.3s × 3 板块 = 0.9s）
- 验证写入 sector_daily 后从 cache_repository 读出字段一致
- ``leading_stock_codes`` / ``limit_up_count`` 在 Task C 阶段填 [] / 0；
  后续 Task F 由 ``stock_fund_flow_industry`` 二次加工
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
    """ak.stock_board_industry_name_ths 返回的简化版（按 akshare 实际列名）。

    实测列：['name', 'code']，90 行。这里简化为 3 行。
    """
    return pd.DataFrame(
        [
            {"name": "半导体", "code": "881121"},
            {"name": "白酒", "code": "881273"},
            {"name": "白色家电", "code": "881131"},
        ]
    )


def _fake_sector_hist_df(prev_close: float, today_close: float) -> pd.DataFrame:
    """ak.stock_board_industry_index_ths 返回的简化版（按 akshare 实际列名）。

    实测列：['日期', '开盘价', '最高价', '最低价', '收盘价', '成交量', '成交额']。
    返回 2 行：前日 + 当日（20260730），用于 pct_chg 自算。

    Args:
        prev_close: 前一日 close
        today_close: 当日 close
    """
    return pd.DataFrame(
        [
            {
                "日期": "2026-07-29",
                "开盘价": prev_close,
                "最高价": prev_close + 5,
                "最低价": prev_close - 5,
                "收盘价": prev_close,
                "成交量": 4.0e8,
                "成交额": 3.0e10,
            },
            {
                "日期": "2026-07-30",
                "开盘价": today_close - 2,
                "最高价": today_close + 5,
                "最低价": today_close - 5,
                "收盘价": today_close,
                "成交量": 4.5e8,
                "成交额": 3.5e10,
            },
        ]
    )


# ── TestSectorFetcherSuccess ─────────────────────────────


class TestSectorFetcherSuccess:
    """同花顺接口正常 → 写 cache → 读出 sector_daily 行。"""

    @pytest.mark.asyncio
    async def test_writes_sector_daily_with_ths_source(self, tmp_db) -> None:
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.sector_daily_fetcher_adapter import (
            SectorDailyFetcherAdapter,
        )

        adapter = SectorDailyFetcherAdapter()
        repo = CacheRepository(conn=get_connection())
        with patch("infrastructure.stock.akshare_client.ak") as mock_ak, \
                patch("infrastructure.stock.akshare_client.time.sleep"):
            mock_ak.stock_board_industry_name_ths.return_value = _fake_sectors_df()
            # 3 个板块都返回前日 close=100，当日 close=105 → pct_chg=5.0%
            mock_ak.stock_board_industry_index_ths.side_effect = lambda **kwargs: (
                _fake_sector_hist_df(prev_close=100.0, today_close=105.0)
            )
            count = await adapter.run(trade_date="20260730", repo=repo)

        # 3 个板块全写入
        assert count == 3

        rows = repo.select_sector_daily(trade_date="20260730")
        assert len(rows) == 3
        # 按 sector_code 索引方便断言
        by_code = {r.sector_code: r for r in rows}
        assert "881121" in by_code
        sem = by_code["881121"]
        assert sem.trade_date == "20260730"
        assert sem.sector_name == "半导体"
        # pct_chg = (105 - 100) / 100 * 100 = 5.0
        assert sem.pct_chg == pytest.approx(5.0)
        # leading_stock_codes 在 Task C 阶段填 []（同花顺接口不返回领涨股）
        assert sem.leading_stock_codes == []
        # limit_up_count 在 Task C 阶段填 0（同花顺接口不返回板块涨停数）
        assert sem.limit_up_count == 0


# ── TestSectorFetcherFailure ─────────────────────────────


class TestSectorFetcherFailure:
    """板块列表接口失败 → 返 0，cache 不写。"""

    @pytest.mark.asyncio
    async def test_sectors_list_error_returns_zero(self, tmp_db) -> None:
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.sector_daily_fetcher_adapter import (
            SectorDailyFetcherAdapter,
        )

        adapter = SectorDailyFetcherAdapter()
        repo = CacheRepository(conn=get_connection())
        with patch("infrastructure.stock.akshare_client.ak") as mock_ak, \
                patch("infrastructure.stock.akshare_client.time.sleep"):
            # 板块列表接口失败 → 整体失败
            mock_ak.stock_board_industry_name_ths.side_effect = ValueError(
                "akshare 板块列表失败"
            )
            count = await adapter.run(trade_date="20260730", repo=repo)

        assert count == 0
        rows = repo.select_sector_daily(trade_date="20260730")
        assert rows == []


# ── TestSectorFetcherEmpty ───────────────────────────────


class TestSectorFetcherEmpty:
    """板块列表为空 DataFrame → 返 0。"""

    @pytest.mark.asyncio
    async def test_empty_sectors_df_returns_zero(self, tmp_db) -> None:
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.sector_daily_fetcher_adapter import (
            SectorDailyFetcherAdapter,
        )

        adapter = SectorDailyFetcherAdapter()
        repo = CacheRepository(conn=get_connection())
        with patch("infrastructure.stock.akshare_client.ak") as mock_ak, \
                patch("infrastructure.stock.akshare_client.time.sleep"):
            mock_ak.stock_board_industry_name_ths.return_value = pd.DataFrame()
            count = await adapter.run(trade_date="20260730", repo=repo)

        assert count == 0


# ── TestSectorFetcherPartialFailure ──────────────────────


class TestSectorFetcherPartialFailure:
    """单板块 K 线接口失败 → 跳过该板块，其他板块正常写入。"""

    @pytest.mark.asyncio
    async def test_single_sector_failure_skipped(self, tmp_db) -> None:
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.sector_daily_fetcher_adapter import (
            SectorDailyFetcherAdapter,
        )

        adapter = SectorDailyFetcherAdapter()
        repo = CacheRepository(conn=get_connection())

        # 构造 side_effect：第 1 个板块（半导体）失败，后 2 个成功
        call_count = {"n": 0}

        def _ths_side_effect(**kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise ValueError("单板块接口失败")
            return _fake_sector_hist_df(prev_close=100.0, today_close=105.0)

        with patch("infrastructure.stock.akshare_client.ak") as mock_ak, \
                patch("infrastructure.stock.akshare_client.time.sleep"):
            mock_ak.stock_board_industry_name_ths.return_value = _fake_sectors_df()
            mock_ak.stock_board_industry_index_ths.side_effect = _ths_side_effect
            count = await adapter.run(trade_date="20260730", repo=repo)

        # 3 个板块中 1 个失败 → 写入 2 个
        assert count == 2
        rows = repo.select_sector_daily(trade_date="20260730")
        assert len(rows) == 2


# ── TestSectorFetcherPctChgCalc ──────────────────────────


class TestSectorFetcherPctChgCalc:
    """Task C：同花顺接口不返回 pct_chg，必须自己算。"""

    @pytest.mark.asyncio
    async def test_pct_chg_calculated_from_prev_close(self, tmp_db) -> None:
        """前日 close=100，当日 close=110 → pct_chg=10.0%。"""
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.sector_daily_fetcher_adapter import (
            SectorDailyFetcherAdapter,
        )

        adapter = SectorDailyFetcherAdapter()
        repo = CacheRepository(conn=get_connection())
        with patch("infrastructure.stock.akshare_client.ak") as mock_ak, \
                patch("infrastructure.stock.akshare_client.time.sleep"):
            mock_ak.stock_board_industry_name_ths.return_value = pd.DataFrame(
                [{"name": "半导体", "code": "881121"}]
            )
            mock_ak.stock_board_industry_index_ths.return_value = (
                _fake_sector_hist_df(prev_close=100.0, today_close=110.0)
            )
            await adapter.run(trade_date="20260730", repo=repo)

        rows = repo.select_sector_daily(trade_date="20260730")
        assert len(rows) == 1
        # (110 - 100) / 100 * 100 = 10.0
        assert rows[0].pct_chg == pytest.approx(10.0)

    @pytest.mark.asyncio
    async def test_pct_chg_none_when_only_one_row(self, tmp_db) -> None:
        """只返回 1 天 K 线（无前日）→ pct_chg=None。"""
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.sector_daily_fetcher_adapter import (
            SectorDailyFetcherAdapter,
        )

        adapter = SectorDailyFetcherAdapter()
        repo = CacheRepository(conn=get_connection())
        with patch("infrastructure.stock.akshare_client.ak") as mock_ak, \
                patch("infrastructure.stock.akshare_client.time.sleep"):
            mock_ak.stock_board_industry_name_ths.return_value = pd.DataFrame(
                [{"name": "半导体", "code": "881121"}]
            )
            # 只返回 1 行（当日，无前日）
            mock_ak.stock_board_industry_index_ths.return_value = pd.DataFrame(
                [
                    {
                        "日期": "2026-07-30",
                        "开盘价": 100.0,
                        "最高价": 105.0,
                        "最低价": 99.0,
                        "收盘价": 103.0,
                        "成交量": 4.5e8,
                        "成交额": 3.5e10,
                    }
                ]
            )
            await adapter.run(trade_date="20260730", repo=repo)

        rows = repo.select_sector_daily(trade_date="20260730")
        assert len(rows) == 1
        # 首行无前日 close → pct_chg=None（不能算）
        assert rows[0].pct_chg is None

    @pytest.mark.asyncio
    async def test_pct_chg_zero_when_close_unchanged(self, tmp_db) -> None:
        """前日 close=100，当日 close=100 → pct_chg=0.0（非 None）。"""
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.sector_daily_fetcher_adapter import (
            SectorDailyFetcherAdapter,
        )

        adapter = SectorDailyFetcherAdapter()
        repo = CacheRepository(conn=get_connection())
        with patch("infrastructure.stock.akshare_client.ak") as mock_ak, \
                patch("infrastructure.stock.akshare_client.time.sleep"):
            mock_ak.stock_board_industry_name_ths.return_value = pd.DataFrame(
                [{"name": "半导体", "code": "881121"}]
            )
            mock_ak.stock_board_industry_index_ths.return_value = (
                _fake_sector_hist_df(prev_close=100.0, today_close=100.0)
            )
            await adapter.run(trade_date="20260730", repo=repo)

        rows = repo.select_sector_daily(trade_date="20260730")
        assert len(rows) == 1
        # close 不变 → pct_chg=0.0
        assert rows[0].pct_chg == 0.0


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
        with patch("infrastructure.stock.akshare_client.ak") as mock_ak, \
                patch("infrastructure.stock.akshare_client.time.sleep"):
            mock_ak.stock_board_industry_name_ths.return_value = _fake_sectors_df()
            mock_ak.stock_board_industry_index_ths.side_effect = lambda **kwargs: (
                _fake_sector_hist_df(prev_close=100.0, today_close=105.0)
            )
            written = await adapter.run(trade_date="20260730", repo=repo)

        assert written == 3
