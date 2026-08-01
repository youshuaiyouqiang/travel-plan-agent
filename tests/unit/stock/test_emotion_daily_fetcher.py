"""Task 12 失败测试：emotion_daily_fetcher（与 market_index_fetcher 同构）。

设计要点：
- 4 类场景：成功 / akshare 错误 / 空 df / adapter 协议
- mock `infrastructure.stock.akshare_client.ak.stock_market_activity_legu`
- 验证写入 emotion_daily 后从 cache_repository 读出字段一致
- 不测 phase / phase_confidence / phase_reason（由 LLM 后置回填）
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

import pandas as pd
import pytest

from infrastructure.persistence.database import init_db, reset_connection
from infrastructure.persistence.connection import get_connection


# ── fixtures ──────────────────────────────────────────────


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_emotion_fetcher.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()
    if db_path.exists():
        os.unlink(db_path)


def _seed_limit_stocks(repo: Any, trade_date: str) -> None:
    """塞 limit_stocks_daily 让 fetcher 算 valid / broken / max_consecutive。"""
    from domain.stock.models import LimitStock

    stocks = [
        # 3 个一次性封死（有效涨停）
        LimitStock(
            trade_date=trade_date, stock_code="000001", stock_name="A",
            limit_type="up", consecutive_boards=3,
            first_limit_time="10:00:00", last_limit_time="10:00:00",
            open_count=0, is_valid_limit_up=True,
        ),
        LimitStock(
            trade_date=trade_date, stock_code="000002", stock_name="B",
            limit_type="up", consecutive_boards=1,
            first_limit_time="10:30:00", last_limit_time="10:30:00",
            open_count=0, is_valid_limit_up=True,
        ),
        LimitStock(
            trade_date=trade_date, stock_code="000003", stock_name="C",
            limit_type="up", consecutive_boards=5,
            first_limit_time="11:00:00", last_limit_time="11:00:00",
            open_count=0, is_valid_limit_up=True,
        ),
        # 1 个炸板后回封（无效涨停，但炸板数 +1）
        LimitStock(
            trade_date=trade_date, stock_code="000004", stock_name="D",
            limit_type="up", consecutive_boards=1,
            first_limit_time="10:00:00", last_limit_time="14:00:00",
            open_count=1, is_valid_limit_up=False,
        ),
        # 1 个跌停（不算涨停也不算炸板，仅用于 max_consecutive 验证）
        LimitStock(
            trade_date=trade_date, stock_code="000005", stock_name="E",
            limit_type="down", consecutive_boards=0,
            first_limit_time=None, last_limit_time=None,
            open_count=0, is_valid_limit_up=False,
        ),
    ]
    repo.upsert_limit_stocks(trade_date=trade_date, stocks=stocks)


def _fake_activity_df() -> pd.DataFrame:
    """ak.stock_market_activity_legu 返回的简化版。"""
    return pd.DataFrame(
        [
            {"item": "涨停", "value": 4},     # 4 家涨停（含 1 个炸板后回封）
            {"item": "跌停", "value": 1},
            {"item": "炸板", "value": 1},
        ]
    )


# ── TestEmotionFetcherSuccess ─────────────────────────────


class TestEmotionFetcherSuccess:
    """akshare 正常 → 写 cache → 读出 8 个数（phase 3 字段 NULL）。"""

    @pytest.mark.asyncio
    async def test_writes_emotion_daily(self, tmp_db) -> None:
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.emotion_daily_fetcher_adapter import (
            EmotionDailyFetcherAdapter,
        )
        from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

        adapter = EmotionDailyFetcherAdapter(
            data_source=SqliteStockDataSource(conn=get_connection()),
        )
        repo = CacheRepository(conn=get_connection())
        _seed_limit_stocks(repo, trade_date="20260730")
        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            mock_ak.stock_market_activity_legu.return_value = _fake_activity_df()
            mock_ak.stock_zh_index_spot_em.return_value = pd.DataFrame(
                [{"code": "sh000001", "成交额": 1.2e12}]
            )
            count = await adapter.run(trade_date="20260730", repo=repo)

        # fetcher 写 1 行（一天一行）
        assert count == 1

        # 读出验证
        rows = repo.select_emotion_daily(trade_date="20260730")
        assert len(rows) == 1
        r = rows[0]
        assert r.trade_date == "20260730"
        # 数值字段
        assert r.limit_up_count == 4   # akshare 返的"涨停"=4
        assert r.limit_down_count == 1
        # 聚合字段（来自 limit_stocks_daily）
        assert r.valid_limit_up_count == 3  # 3 个一次性封死
        assert r.broken_limit_ratio == pytest.approx(1 / 5)  # 1 / (4+1)
        assert r.max_consecutive_boards == 5  # 3 只涨停中最大连板
        # 成交额
        assert r.total_volume == pytest.approx(1.2e12)
        # volume_change_pct：昨日无数据 → None
        assert r.volume_change_pct is None
        # phase 3 字段：fetcher 不写，留 None
        assert r.phase is None
        assert r.phase_confidence is None
        assert r.phase_reason is None


# ── TestEmotionFetcherFailure ─────────────────────────────


class TestEmotionFetcherFailure:
    """akshare 抛异常 → 返 0，cache 不写。"""

    @pytest.mark.asyncio
    async def test_akshare_error_returns_zero(self, tmp_db) -> None:
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.emotion_daily_fetcher_adapter import (
            EmotionDailyFetcherAdapter,
        )
        from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

        adapter = EmotionDailyFetcherAdapter(
            data_source=SqliteStockDataSource(conn=get_connection()),
        )
        repo = CacheRepository(conn=get_connection())
        _seed_limit_stocks(repo, trade_date="20260730")
        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            mock_ak.stock_market_activity_legu.side_effect = ValueError("akshare 失败")
            count = await adapter.run(trade_date="20260730", repo=repo)

        assert count == 0
        rows = repo.select_emotion_daily(trade_date="20260730")
        assert rows == []


# ── TestEmotionFetcherEmpty ───────────────────────────────


class TestEmotionFetcherEmpty:
    """akshare 返空 DataFrame → 返 0。"""

    @pytest.mark.asyncio
    async def test_empty_df_returns_zero(self, tmp_db) -> None:
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.emotion_daily_fetcher import run

        _seed_limit_stocks(
            CacheRepository(conn=get_connection()),
            trade_date="20260730",
        )
        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            mock_ak.stock_market_activity_legu.return_value = pd.DataFrame()
            mock_ak.stock_zh_index_spot_em.return_value = pd.DataFrame()
            repo = CacheRepository(conn=get_connection())
            count = await run("20260730", repo)

        assert count == 0


# ── TestEmotionFetcherAdapter ─────────────────────────────


class TestEmotionFetcherAdapter:
    """EmotionDailyFetcherAdapter 走 Fetcher 协议。"""

    @pytest.mark.asyncio
    async def test_adapter_runs_through_pipeline(self, tmp_db) -> None:
        from infrastructure.stock.akshare_client import AkshareClient
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.emotion_daily_fetcher_adapter import (
            EmotionDailyFetcherAdapter,
        )
        from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

        ds = SqliteStockDataSource(conn=get_connection())
        adapter = EmotionDailyFetcherAdapter(client=AkshareClient(), data_source=ds)
        # 协议 duck-type 校验
        assert adapter.name == "emotion_daily_fetcher"
        assert callable(adapter.run)

        repo = CacheRepository(conn=get_connection())
        _seed_limit_stocks(repo, trade_date="20260730")
        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            mock_ak.stock_market_activity_legu.return_value = _fake_activity_df()
            mock_ak.stock_zh_index_spot_em.return_value = pd.DataFrame(
                [{"code": "sh000001", "成交额": 1.0e12}]
            )
            written = await adapter.run(trade_date="20260730", repo=repo)

        assert written == 1
