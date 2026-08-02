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


# ── Task B：spot_em 降级 + 无 limit_stocks 边界 ────────────────


class TestEmotionFetcherSpotEmDegradation:
    """Task B：spot_em 失败时降级为 total_volume=None，其他字段照写。

    现状 bug：fetch_emotion_daily 在 spot_em 失败时直接 raise AkshareFetchError，
    导致整个 fetcher 返回 0，emotion_daily 表该日完全不写入。
    修复后：legu 成功 + spot_em 失败 → total_volume=None，其他字段正常写入。
    """

    @pytest.mark.asyncio
    async def test_spot_em_failure_writes_with_none_volume(self, tmp_db) -> None:
        """spot_em 抛异常 → total_volume=None，但 limit_up/limit_down/valid 照写。"""
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
            # spot_em 失败
            mock_ak.stock_zh_index_spot_em.side_effect = ValueError("反爬失败")
            count = await adapter.run(trade_date="20260730", repo=repo)

        # 修复后：spot_em 失败时降级，fetcher 仍写 1 行
        assert count == 1
        rows = repo.select_emotion_daily(trade_date="20260730")
        assert len(rows) == 1
        r = rows[0]
        # 其他字段照写
        assert r.limit_up_count == 4
        assert r.limit_down_count == 1
        assert r.valid_limit_up_count == 3
        # total_volume 应为 None（降级）
        assert r.total_volume is None, (
            f"spot_em 失败时 total_volume 应为 None（降级），got={r.total_volume}"
        )
        # volume_change_pct 也应为 None（当日 total_volume=None 无法算）
        assert r.volume_change_pct is None

    @pytest.mark.asyncio
    async def test_spot_em_empty_df_writes_with_none_volume(self, tmp_db) -> None:
        """spot_em 返空 df → total_volume=None（非 0.0）。"""
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
            # spot_em 返空 df
            mock_ak.stock_zh_index_spot_em.return_value = pd.DataFrame()
            count = await adapter.run(trade_date="20260730", repo=repo)

        assert count == 1
        rows = repo.select_emotion_daily(trade_date="20260730")
        r = rows[0]
        assert r.total_volume is None, (
            f"spot_em 返空时 total_volume 应为 None，got={r.total_volume}"
        )


class TestEmotionFetcherNoLimitStocksBoundary:
    """Task B：limit_stocks 为空时也写入（冰点期是有效数据）。

    现状 bug：fetcher 第 80-86 行在 limit_stocks 为空时直接 return 0，
    导致"涨停数为 0 的冰点期"完全不写入 emotion_daily。
    修复后：limit_stocks 为空时 valid_count=0、max_boards=0，
    其他字段照写。
    """

    @pytest.mark.asyncio
    async def test_no_limit_stocks_still_writes(self, tmp_db) -> None:
        """limit_stocks_daily 该日无数据 → 仍写入 emotion_daily（valid=0, max_boards=0）。"""
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.emotion_daily_fetcher_adapter import (
            EmotionDailyFetcherAdapter,
        )
        from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

        adapter = EmotionDailyFetcherAdapter(
            data_source=SqliteStockDataSource(conn=get_connection()),
        )
        repo = CacheRepository(conn=get_connection())
        # 不 seed limit_stocks_daily（模拟涨停数为 0 的冰点期）

        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            # legu 返回涨停 0 / 跌停 5 / 炸板 0（冰点期）
            mock_ak.stock_market_activity_legu.return_value = pd.DataFrame(
                [
                    {"item": "涨停", "value": 0},
                    {"item": "跌停", "value": 5},
                    {"item": "炸板", "value": 0},
                ]
            )
            mock_ak.stock_zh_index_spot_em.return_value = pd.DataFrame(
                [{"code": "sh000001", "成交额": 8.0e11}]
            )
            count = await adapter.run(trade_date="20260730", repo=repo)

        # 修复后：limit_stocks 为空时仍写入（不 skip）
        assert count == 1
        rows = repo.select_emotion_daily(trade_date="20260730")
        assert len(rows) == 1
        r = rows[0]
        assert r.limit_up_count == 0
        assert r.limit_down_count == 5
        # valid / max_boards 为 0（无涨停股）
        assert r.valid_limit_up_count == 0
        assert r.max_consecutive_boards == 0
        # broken_ratio = 0 / (0 + 0) 应为 0.0（不能 NaN）
        assert r.broken_limit_ratio == 0.0
        # total_volume 照写
        assert r.total_volume == pytest.approx(8.0e11)


class TestEmotionFetcherVolumeChangePctWithNone:
    """Task B：volume_change_pct 在 None total_volume 时的边界。

    - 当日 total_volume=None → volume_change_pct=None
    - 前日 total_volume=None → volume_change_pct=None
    """

    @pytest.mark.asyncio
    async def test_volume_change_pct_none_when_today_volume_none(
        self, tmp_db
    ) -> None:
        """当日 total_volume=None（spot_em 失败）→ volume_change_pct=None。"""
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.emotion_daily_fetcher_adapter import (
            EmotionDailyFetcherAdapter,
        )
        from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

        adapter = EmotionDailyFetcherAdapter(
            data_source=SqliteStockDataSource(conn=get_connection()),
        )
        repo = CacheRepository(conn=get_connection())
        # 写昨日 emotion_daily（有 total_volume）
        from domain.stock.models import EmotionIndicators

        repo.upsert_emotion_daily(
            trade_date="20260729",
            rows=[
                EmotionIndicators(
                    trade_date="20260729",
                    limit_up_count=10, limit_down_count=2,
                    valid_limit_up_count=8, broken_limit_ratio=0.1,
                    max_consecutive_boards=2,
                    yesterday_limit_up_today_premium=None,
                    total_volume=1.0e12, volume_change_pct=None,
                    phase=None, phase_confidence=None, phase_reason=None,
                )
            ],
        )
        _seed_limit_stocks(repo, trade_date="20260730")
        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            mock_ak.stock_market_activity_legu.return_value = _fake_activity_df()
            # spot_em 失败 → 当日 total_volume=None
            mock_ak.stock_zh_index_spot_em.side_effect = ValueError("失败")
            count = await adapter.run(trade_date="20260730", repo=repo)

        assert count == 1
        rows = repo.select_emotion_daily(trade_date="20260730")
        r = rows[0]
        # 当日 total_volume=None → volume_change_pct 必须为 None（不能除 0）
        assert r.total_volume is None
        assert r.volume_change_pct is None
