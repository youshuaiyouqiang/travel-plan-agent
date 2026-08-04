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


@pytest.fixture(autouse=True)
def force_today(monkeypatch):
    """Bug① 修复后 fetcher 在历史日期走 _run_historical 分支（raw-derived 字段 None）。

    现有测试用 trade_date=\"20260730\" 等历史日期 + mock akshare 接口验证完整
    today 分支流程。autouse fixture 把 ``_is_today`` mock 为 True 保持旧行为。
    新增的"历史分支"测试单独 override 此 fixture（或传入 monkeypatch 直接设 False）。
    """
    monkeypatch.setattr(
        "infrastructure.stock.emotion_daily_fetcher._is_today",
        lambda trade_date: True,
    )


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
        # 1 个炸板股（limit_type="broken"，验证 broken_ratio 走 DB 聚合）
        LimitStock(
            trade_date=trade_date, stock_code="000006", stock_name="F",
            limit_type="broken", consecutive_boards=0,
            first_limit_time=None, last_limit_time="14:30:00",
            open_count=2, is_valid_limit_up=False,
        ),
    ]
    repo.upsert_limit_stocks(trade_date=trade_date, stocks=stocks)


def _fake_activity_df() -> pd.DataFrame:
    """ak.stock_market_activity_legu 返回的简化版。

    Task E：新增"上涨"/"下跌"项（维度 2 广度原始数据）。

    数值故意与 _seed_limit_stocks 不一致（"涨停"=99，但 db 里只塞 4 个 up），
    用来断言 fetcher 现在走 db 聚合而非 akshare 实时截面。
    """
    return pd.DataFrame(
        [
            {"item": "涨停", "value": 99},   # fake ≠ db 个数，驱动 fetcher 走 db
            {"item": "跌停", "value": 1},    # fetcher 仍信 akshare（无 db 替代）
            {"item": "炸板", "value": 99},   # fake ≠ db 个数，驱动 fetcher 走 db
            {"item": "上涨", "value": 300},
            {"item": "下跌", "value": 200},
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
        # 修复前 fetcher 直接用 akshare 实时截面的"涨停"=99 → 与历史 7-30 真实数不符。
        # 现在 fetcher 从 limit_stocks_daily 聚合（4 个 up）→ 4（fake 99 必须被忽略）。
        assert r.limit_up_count == 4
        assert r.limit_down_count == 1
        # 聚合字段（来自 limit_stocks_daily）
        assert r.valid_limit_up_count == 3  # 3 个一次性封死
        # 修复前 fetcher 用 akshare "炸板"=99 算 → broken_ratio ≈ 99/(99+99) ≈ 0.5
        # 现在 db 有 1 个 broken 行 → broken_ratio = 1/(4+1) = 0.2（DB 优先）
        assert r.broken_limit_ratio == pytest.approx(0.2)
        assert r.max_consecutive_boards == 5  # 3 只涨停中最大连板
        # 龙头股票：5 板的 000003 必须出现在 top_board_leaders
        assert "000003" in r.top_board_leaders
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


# ── Task E：6 维度情绪观察框架集成测试 ────────────────────


def _fake_fund_flow_df() -> pd.DataFrame:
    """ak.stock_fund_flow_individual 返回的简化版（含字符串字段）。

    Task E：成交额前 20 名的涨幅统计（维度 3 强度）。
    构造 25 行：前 20 名平均涨幅约 3.5%、上涨 18 只、涨停 2 只 → "强势"。
    """
    rows = []
    # 前 20 名：高成交额 + 多数上涨
    for i in range(20):
        chg = f"{3.0 + i * 0.05:.2f}%"  # 3.00% ~ 3.95%
        amount = f"{10 - i * 0.1:.1f}亿"  # 10亿 ~ 8.1亿
        rows.append({
            "序号": i + 1, "股票代码": f"60000{i:02d}", "股票简称": f"股{i}",
            "最新价": 10.0, "涨跌幅": chg, "换手率": "5.0%",
            "流入资金": "5亿", "流出资金": "3亿", "净额": "2亿", "成交额": amount,
        })
    # 5 名低成交额（不会进 top 20）
    for i in range(5):
        rows.append({
            "序号": 21 + i, "股票代码": f"00000{i}", "股票简称": f"小{i}",
            "最新价": 5.0, "涨跌幅": "1.00%", "换手率": "2.0%",
            "流入资金": "0.1亿", "流出资金": "0.05亿", "净额": "0.05亿",
            "成交额": "0.5亿",
        })
    return pd.DataFrame(rows)


def _seed_history_emotion(repo: Any, end_date: str, days: int) -> None:
    """塞近 N 日 emotion_daily（用于 height percentile + trend）。

    涨停数序列（近→远）：[40, 35, 30, 25, 20, 15, 10, ...]（递减趋势）
    """
    from domain.stock.models import EmotionIndicators

    base = int(end_date)
    for i in range(days):
        # 日期往前推 i 天（简化：不考虑周末）
        d = base - i
        trade_date = str(d)
        # 涨停数递减：近 5 日 [40,35,30,25,20]，趋势=下降
        limit_up = max(5, 40 - i * 3)
        repo.upsert_emotion_daily(
            trade_date=trade_date,
            rows=[
                EmotionIndicators(
                    trade_date=trade_date,
                    limit_up_count=limit_up,
                    limit_down_count=2,
                    valid_limit_up_count=limit_up - 1,
                    broken_limit_ratio=0.1,
                    max_consecutive_boards=2,
                    yesterday_limit_up_today_premium=None,
                    total_volume=1.0e12, volume_change_pct=0.05,
                    phase=None, phase_confidence=None, phase_reason=None,
                )
            ],
        )


class TestEmotionFetcherSixDimensions:
    """Task E：6 维度情绪观察框架集成测试。

    验证 fetcher 正确调用 6 维度计算函数并写入 v023 新增字段。
    """

    @pytest.mark.asyncio
    async def test_six_dimensions_written(self, tmp_db) -> None:
        """完整 6 维度计算流程 → 18 个新字段正确写入。"""
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.emotion_daily_fetcher_adapter import (
            EmotionDailyFetcherAdapter,
        )
        from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

        adapter = EmotionDailyFetcherAdapter(
            data_source=SqliteStockDataSource(conn=get_connection()),
        )
        repo = CacheRepository(conn=get_connection())

        # 1. 塞历史 emotion_daily（近 10 日，用于 height + trend）
        _seed_history_emotion(repo, end_date="20260729", days=10)

        # 2. 塞昨日 limit_stocks + 今日 stock_daily（用于韧性维度）
        from domain.stock.models import LimitStock, StockDaily
        yesterday_stocks = [
            LimitStock(
                trade_date="20260729", stock_code="600000", stock_name="A",
                limit_type="up", consecutive_boards=2,
                first_limit_time="10:00:00", last_limit_time="10:00:00",
                open_count=0, is_valid_limit_up=True,
            ),
            LimitStock(
                trade_date="20260729", stock_code="600001", stock_name="B",
                limit_type="up", consecutive_boards=1,
                first_limit_time="10:30:00", last_limit_time="10:30:00",
                open_count=0, is_valid_limit_up=True,
            ),
        ]
        repo.upsert_limit_stocks(trade_date="20260729", stocks=yesterday_stocks)

        # 今日 stock_daily：600000 涨 6%（断板反包成功），600001 跌 2%（断板未反包）
        today_stocks = [
            StockDaily(
                trade_date="20260730", stock_code="600000",
                open=10.0, close=10.6, high=10.8, low=9.9,
                volume=1e6, pct_chg=6.0, turnover=1e7,
            ),
            StockDaily(
                trade_date="20260730", stock_code="600001",
                open=10.0, close=9.8, high=10.1, low=9.7,
                volume=5e5, pct_chg=-2.0, turnover=5e6,
            ),
        ]
        repo.upsert_stock_daily(trade_date="20260730", rows=today_stocks)

        # 3. 塞今日 limit_stocks（用于 valid_count + max_boards）
        _seed_limit_stocks(repo, trade_date="20260730")

        # 4. mock akshare（legu + spot_em + fund_flow_individual）
        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            mock_ak.stock_market_activity_legu.return_value = _fake_activity_df()
            mock_ak.stock_zh_index_spot_em.return_value = pd.DataFrame(
                [{"code": "sh000001", "成交额": 1.2e12}]
            )
            mock_ak.stock_fund_flow_individual.return_value = _fake_fund_flow_df()
            count = await adapter.run(trade_date="20260730", repo=repo)

        assert count == 1
        rows = repo.select_emotion_daily(trade_date="20260730")
        assert len(rows) == 1
        r = rows[0]

        # 维度 2：广度（adv=300, decl=200 → ratio=1.5 → "偏广"）
        assert r.adv_count == 300
        assert r.decl_count == 200
        assert r.adv_decl_ratio == pytest.approx(1.5)
        assert r.breadth_level == "偏广"

        # 维度 3：强度（top20 avg_chg≈3.48, up_count=20, limit_up=0 → "强势"）
        assert r.strength_level == "强势"
        assert r.top20_volume_up_count == 20
        assert r.market_style is not None  # 有 height_level 才有 market_style

        # 维度 5：真实度（db 有 1 个 broken 行 → broken_ratio=0.2 → "偏真"）
        assert r.authenticity_level == "偏真"

        # 维度 1：高度（有历史数据 → 非 None）
        assert r.height_level is not None

        # 维度 6：持续性（近 5 日涨停数递减 → "下降"）
        assert r.trend_5d is not None

        # 维度 4：韧性（昨日 2 涨停，今日 1 断板反包 → board_break_total=2, rebound=1）
        assert r.board_break_total_count is not None
        assert r.board_break_total_count >= 1
        assert r.resilience_level is not None

    @pytest.mark.asyncio
    async def test_strength_degrades_when_fund_flow_fails(self, tmp_db) -> None:
        """fetch_top20_volume_stocks 失败 → strength 字段为 None，其他维度照写。"""
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
                [{"code": "sh000001", "成交额": 1.0e12}]
            )
            # fund_flow_individual 失败
            mock_ak.stock_fund_flow_individual.side_effect = ValueError("反爬失败")
            count = await adapter.run(trade_date="20260730", repo=repo)

        assert count == 1
        rows = repo.select_emotion_daily(trade_date="20260730")
        r = rows[0]
        # 强度字段为 None（降级）
        assert r.strength_level is None
        assert r.market_style is None
        assert r.top20_volume_avg_chg is None
        # 其他维度照写
        assert r.breadth_level is not None
        assert r.authenticity_level is not None

    @pytest.mark.asyncio
    async def test_resilience_none_when_no_yesterday_data(self, tmp_db) -> None:
        """无昨日 emotion_daily → 韧性字段全部 None。"""
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
        # 不 seed 历史 emotion_daily（无昨日数据）

        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            mock_ak.stock_market_activity_legu.return_value = _fake_activity_df()
            mock_ak.stock_zh_index_spot_em.return_value = pd.DataFrame(
                [{"code": "sh000001", "成交额": 1.0e12}]
            )
            mock_ak.stock_fund_flow_individual.return_value = _fake_fund_flow_df()
            count = await adapter.run(trade_date="20260730", repo=repo)

        assert count == 1
        rows = repo.select_emotion_daily(trade_date="20260730")
        r = rows[0]
        # 韧性字段全部 None（无昨日数据）
        assert r.board_break_total_count is None
        assert r.board_break_rebound_count is None
        assert r.resilience_level is None
        # 高度/trend 仍可计算（默认"中位"/"数据不足"）
        assert r.height_level == "中位"  # 无历史 → 默认中位
        assert r.trend_5d == "数据不足"  # 无历史 → 数据不足


class TestEmotionFetcherHistoricalBranch:
    """Bug①：fetcher 对历史日期走 _run_historical 分支。

    akshare 实时接口（legu / spot_em / fund_flow_individual）不接受日期参数，
    永远返回"今天"截面。fetcher 对历史日期继续走 akshare 会污染历史行
    的 raw-derived 维度（adv/decl/total_volume/strength/height/trend）。
    修复后：trade_date != today → 跳过 akshare，所有 raw-derived 字段 None，
    仅写 limit_stocks_daily 聚合的核心字段。
    """

    @pytest.fixture(autouse=True)
    def force_historical(self, monkeypatch):
        """覆盖外层 autouse force_today，强制 fetcher 走历史分支。"""
        monkeypatch.setattr(
            "infrastructure.stock.emotion_daily_fetcher._is_today",
            lambda trade_date: False,
        )

    @pytest.mark.asyncio
    async def test_historical_branch_does_not_call_akshare(self, tmp_db) -> None:
        """历史分支：fetcher 不调 akshare 实时接口，写入 1 行。"""
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
            count = await adapter.run(trade_date="20260730", repo=repo)
            # akshare 实时接口不被调用（避免污染）
            mock_ak.stock_market_activity_legu.assert_not_called()
            mock_ak.stock_zh_index_spot_em.assert_not_called()
            mock_ak.stock_fund_flow_individual.assert_not_called()

        assert count == 1
        rows = repo.select_emotion_daily(trade_date="20260730")
        assert len(rows) == 1
        r = rows[0]

        # limit_stocks 聚合字段：db 真实值
        assert r.limit_up_count == 4
        assert r.broken_limit_ratio == pytest.approx(0.2)  # db 有 1 个 broken 行: 1/(4+1)
        assert r.max_consecutive_boards == 5
        assert "000003" in r.top_board_leaders
        assert r.valid_limit_up_count == 3

        # akshare 实时源字段：全部 None（历史日期不可用）
        assert r.limit_down_count == 0  # 历史日期无数据
        assert r.total_volume is None
        assert r.volume_change_pct is None
        assert r.adv_count is None
        assert r.decl_count is None
        assert r.adv_decl_ratio is None
        assert r.breadth_level is None
        assert r.top20_volume_avg_chg is None
        assert r.top20_volume_up_count is None
        assert r.top20_volume_limit_up_count is None
        assert r.strength_level is None
        assert r.market_style is None
        assert r.board_break_total_count is None
        assert r.board_break_rebound_count is None
        assert r.rebound_success_ratio is None
        assert r.resilience_level is None
        # 历史分支现从 DB 计算 height/trend（无历史时降级为默认值，非 None）
        assert r.height_level == "中位"  # 无历史 → percentile None → 默认中位
        assert r.trend_5d == "数据不足"  # 无历史 → 数据点 <3
        assert r.trend_20d == "数据不足"

        # authenticity 仍可计算（来自 broken_ratio）
        assert r.authenticity_level is not None

    @pytest.mark.asyncio
    async def test_historical_branch_with_broken_data(self, tmp_db) -> None:
        """历史分支：当 limit_stocks 有 broken 行时，broken_ratio 不为 0。"""
        from domain.stock.models import LimitStock
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.emotion_daily_fetcher_adapter import (
            EmotionDailyFetcherAdapter,
        )
        from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

        # seed：3 涨停 + 2 炸板
        stocks = [
            LimitStock(
                trade_date="20260730", stock_code="000001", stock_name="A",
                limit_type="up", consecutive_boards=1,
                first_limit_time="10:00:00", last_limit_time="10:00:00",
                open_count=0, is_valid_limit_up=True,
            ),
            LimitStock(
                trade_date="20260730", stock_code="000002", stock_name="B",
                limit_type="up", consecutive_boards=2,
                first_limit_time="10:30:00", last_limit_time="10:30:00",
                open_count=0, is_valid_limit_up=True,
            ),
            LimitStock(
                trade_date="20260730", stock_code="000003", stock_name="C",
                limit_type="up", consecutive_boards=1,
                first_limit_time="11:00:00", last_limit_time="11:00:00",
                open_count=0, is_valid_limit_up=True,
            ),
            LimitStock(
                trade_date="20260730", stock_code="600000", stock_name="X",
                limit_type="broken", consecutive_boards=0,
                first_limit_time=None, last_limit_time="14:35:21",
                open_count=2, is_valid_limit_up=False,
            ),
            LimitStock(
                trade_date="20260730", stock_code="600001", stock_name="Y",
                limit_type="broken", consecutive_boards=0,
                first_limit_time=None, last_limit_time="13:12:45",
                open_count=1, is_valid_limit_up=False,
            ),
        ]
        repo = CacheRepository(conn=get_connection())
        repo.upsert_limit_stocks(trade_date="20260730", stocks=stocks)

        adapter = EmotionDailyFetcherAdapter(
            data_source=SqliteStockDataSource(conn=get_connection()),
        )
        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            count = await adapter.run(trade_date="20260730", repo=repo)
            mock_ak.stock_market_activity_legu.assert_not_called()

        assert count == 1
        rows = repo.select_emotion_daily(trade_date="20260730")
        r = rows[0]
        # 真实聚合：3 涨停 + 2 炸板 → broken_ratio = 2 / (3 + 2) = 0.4
        assert r.limit_up_count == 3
        assert r.broken_limit_ratio == pytest.approx(0.4)
        assert r.max_consecutive_boards == 2
        assert r.top_board_leaders == ["000002"]  # 唯一 2 板龙头

    @pytest.mark.asyncio
    async def test_historical_branch_computes_emotion_cycle(self, tmp_db) -> None:
        """历史分支现从 DB 计算情绪周期字段（v025），不再硬编码 None。

        镜像 test_emotion_phase_written 的 seed（history + 昨日 limit_stocks +
        今日 stock_daily），但走 _run_historical 分支（_is_today=False）。
        验证：溢价从 DB 算出（2.0），风格得分/情绪得分/阶段非 None，
        akshare 实时字段仍 None（历史日不调 akshare）。
        """
        from domain.stock.models import LimitStock, StockDaily
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.emotion_daily_fetcher_adapter import (
            EmotionDailyFetcherAdapter,
        )
        from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

        adapter = EmotionDailyFetcherAdapter(
            data_source=SqliteStockDataSource(conn=get_connection()),
        )
        repo = CacheRepository(conn=get_connection())

        # 1. 历史 emotion_daily（近 10 日，用于 day_3d_ago + percentile + trend）
        _seed_history_emotion(repo, end_date="20260729", days=10)

        # 2. 昨日 limit_stocks + 今日 stock_daily（用于溢价 + 韧性）
        yesterday_stocks = [
            LimitStock(trade_date="20260729", stock_code="600000", stock_name="A",
                       limit_type="up", consecutive_boards=2,
                       first_limit_time="10:00:00", last_limit_time="10:00:00",
                       open_count=0, is_valid_limit_up=True),
            LimitStock(trade_date="20260729", stock_code="600001", stock_name="B",
                       limit_type="up", consecutive_boards=1,
                       first_limit_time="10:30:00", last_limit_time="10:30:00",
                       open_count=0, is_valid_limit_up=True),
        ]
        repo.upsert_limit_stocks(trade_date="20260729", stocks=yesterday_stocks)
        today_stocks = [
            StockDaily(trade_date="20260730", stock_code="600000",
                       open=10.0, close=10.6, high=10.8, low=9.9,
                       volume=1e6, pct_chg=6.0, turnover=1e7),
            StockDaily(trade_date="20260730", stock_code="600001",
                       open=10.0, close=9.8, high=10.1, low=9.7,
                       volume=5e5, pct_chg=-2.0, turnover=5e6),
        ]
        repo.upsert_stock_daily(trade_date="20260730", rows=today_stocks)

        # 3. 今日 limit_stocks（用于 valid_count + max_boards）
        _seed_limit_stocks(repo, trade_date="20260730")

        # 4. 历史分支不调 akshare；spy 捕获 upsert 的 EmotionIndicators
        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            with patch.object(
                repo, "upsert_emotion_daily", wraps=repo.upsert_emotion_daily
            ) as spy:
                count = await adapter.run(trade_date="20260730", repo=repo)
            # 历史分支跳过 akshare 实时接口（避免污染历史行）
            mock_ak.stock_market_activity_legu.assert_not_called()

        assert count == 1
        captured = spy.call_args.kwargs["rows"][0]

        # 昨日涨停今日溢价：(6.0 + -2.0) / 2 = 2.0（从 DB 计算，非 None）
        assert captured.yesterday_limit_up_today_premium == pytest.approx(2.0)

        # 三风格得分 + 全局得分 + 阶段：全部从 DB 算出
        # （趋势无 akshare 宽度降级为 50，仍非 None；打板/反包从 DB 准确算）
        assert captured.board_style_score is not None
        assert 0 <= captured.board_style_score <= 100
        assert captured.trend_style_score is not None
        assert 0 <= captured.trend_style_score <= 100
        assert captured.emotion_score is not None
        assert 0 <= captured.emotion_score <= 100
        assert captured.emotion_phase in {
            "冰点", "强分歧", "弱分歧", "弱修复", "强修复", "高潮"
        }

        # akshare 实时源字段：历史日仍 None（不被污染）
        assert captured.total_volume is None
        assert captured.adv_count is None
        assert captured.top20_volume_avg_chg is None


# ── Task 3：情绪周期（昨日涨停溢价 + 风格得分 + 阶段）──────────────


class _FakePremiumDeps:
    """_compute_yesterday_premium 的最小依赖 stub。

    只实现 select_limit_stocks / select_stock_daily（_compute_yesterday_premium
    仅需这两个）；用 dict 按 trade_date 提供数据。传给函数时以 Any 类型绕开
    _FetcherDeps Protocol 的 mypy 校验（运行期 Protocol 是结构化鸭类型）。
    """

    def __init__(
        self,
        limit_stocks_by_date: dict[str, list[Any]] | None = None,
        stock_daily_by_date: dict[str, list[Any]] | None = None,
    ) -> None:
        self._limit = limit_stocks_by_date or {}
        self._daily = stock_daily_by_date or {}

    def select_limit_stocks(self, trade_date: str) -> list[Any]:
        return self._limit.get(trade_date, [])

    def select_stock_daily(self, trade_date: str) -> list[Any]:
        return self._daily.get(trade_date, [])


class TestEmotionCycleYesterdayPremium:
    """Task 3：昨日涨停今日溢价计算（_compute_yesterday_premium，开发文档 §3.3 §7.2）。"""

    def test_yesterday_premium_normal(self) -> None:
        """昨日 2 只非 ST 涨停股 + 今日 stock_daily → 返回算术平均。

        broken 股不算涨停不参与；今日涨幅 3.0% / 5.0% → (3.0+5.0)/2 = 4.0。
        """
        from domain.stock.models import EmotionIndicators, LimitStock, StockDaily
        from infrastructure.stock.emotion_daily_fetcher import _compute_yesterday_premium

        yesterday = EmotionIndicators(
            trade_date="20260729",
            limit_up_count=2, limit_down_count=0, valid_limit_up_count=2,
            broken_limit_ratio=0.0, max_consecutive_boards=1,
            yesterday_limit_up_today_premium=None, total_volume=None,
            volume_change_pct=None, phase=None, phase_confidence=None,
            phase_reason=None,
        )
        limit_stocks = [
            LimitStock(trade_date="20260729", stock_code="000001", stock_name="甲股",
                       limit_type="up", consecutive_boards=1,
                       first_limit_time="10:00:00", last_limit_time="10:00:00",
                       open_count=0, is_valid_limit_up=True),
            LimitStock(trade_date="20260729", stock_code="000002", stock_name="乙股",
                       limit_type="up", consecutive_boards=1,
                       first_limit_time="10:30:00", last_limit_time="10:30:00",
                       open_count=0, is_valid_limit_up=True),
            # broken 不算涨停
            LimitStock(trade_date="20260729", stock_code="000003", stock_name="丙股",
                       limit_type="broken", consecutive_boards=0,
                       first_limit_time=None, last_limit_time="14:00:00",
                       open_count=1, is_valid_limit_up=False),
        ]
        stock_daily = [
            StockDaily(trade_date="20260730", stock_code="000001",
                       open=10.0, close=10.3, high=10.5, low=9.9,
                       volume=1e6, pct_chg=3.0, turnover=1e7),
            StockDaily(trade_date="20260730", stock_code="000002",
                       open=10.0, close=10.5, high=10.6, low=9.8,
                       volume=2e6, pct_chg=5.0, turnover=2e7),
            StockDaily(trade_date="20260730", stock_code="000003",
                       open=10.0, close=10.1, high=10.2, low=9.9,
                       volume=5e5, pct_chg=1.0, turnover=5e6),
        ]
        deps: Any = _FakePremiumDeps(
            limit_stocks_by_date={"20260729": limit_stocks},
            stock_daily_by_date={"20260730": stock_daily},
        )
        assert _compute_yesterday_premium("20260730", yesterday, deps) == pytest.approx(4.0)

    def test_yesterday_premium_st_filtered(self) -> None:
        """ST/*ST/退市股被 is_st_stock 过滤，只算非 ST 涨停股的溢价。"""
        from domain.stock.models import EmotionIndicators, LimitStock, StockDaily
        from infrastructure.stock.emotion_daily_fetcher import _compute_yesterday_premium

        yesterday = EmotionIndicators(
            trade_date="20260729",
            limit_up_count=3, limit_down_count=0, valid_limit_up_count=3,
            broken_limit_ratio=0.0, max_consecutive_boards=1,
            yesterday_limit_up_today_premium=None, total_volume=None,
            volume_change_pct=None, phase=None, phase_confidence=None,
            phase_reason=None,
        )
        limit_stocks = [
            LimitStock(trade_date="20260729", stock_code="000001", stock_name="正常股",
                       limit_type="up", consecutive_boards=1,
                       first_limit_time="10:00:00", last_limit_time="10:00:00",
                       open_count=0, is_valid_limit_up=True),
            LimitStock(trade_date="20260729", stock_code="000002", stock_name="ST退市",
                       limit_type="up", consecutive_boards=1,
                       first_limit_time="10:00:00", last_limit_time="10:00:00",
                       open_count=0, is_valid_limit_up=True),
            LimitStock(trade_date="20260729", stock_code="000003", stock_name="*ST股",
                       limit_type="up", consecutive_boards=1,
                       first_limit_time="10:00:00", last_limit_time="10:00:00",
                       open_count=0, is_valid_limit_up=True),
        ]
        stock_daily = [
            StockDaily(trade_date="20260730", stock_code="000001",
                       open=10.0, close=10.4, high=10.5, low=9.9,
                       volume=1e6, pct_chg=4.0, turnover=1e7),
            StockDaily(trade_date="20260730", stock_code="000002",
                       open=5.0, close=5.3, high=5.4, low=4.9,
                       volume=1e6, pct_chg=6.0, turnover=5e6),
            StockDaily(trade_date="20260730", stock_code="000003",
                       open=3.0, close=3.15, high=3.2, low=2.95,
                       volume=1e6, pct_chg=5.0, turnover=3e6),
        ]
        deps: Any = _FakePremiumDeps(
            limit_stocks_by_date={"20260729": limit_stocks},
            stock_daily_by_date={"20260730": stock_daily},
        )
        # ST退市 / *ST股 被过滤 → 只算 000001 的 4.0
        assert _compute_yesterday_premium("20260730", yesterday, deps) == pytest.approx(4.0)

    def test_yesterday_premium_no_yesterday(self) -> None:
        """yesterday=None（无昨日数据）→ 返回 None（冰点期无法计算溢价）。"""
        from infrastructure.stock.emotion_daily_fetcher import _compute_yesterday_premium

        deps: Any = _FakePremiumDeps()
        assert _compute_yesterday_premium("20260730", None, deps) is None

    def test_yesterday_premium_no_stock_daily(self) -> None:
        """昨日有涨停但今日 stock_daily 缺失 → 返回 None。"""
        from domain.stock.models import EmotionIndicators, LimitStock
        from infrastructure.stock.emotion_daily_fetcher import _compute_yesterday_premium

        yesterday = EmotionIndicators(
            trade_date="20260729",
            limit_up_count=1, limit_down_count=0, valid_limit_up_count=1,
            broken_limit_ratio=0.0, max_consecutive_boards=1,
            yesterday_limit_up_today_premium=None, total_volume=None,
            volume_change_pct=None, phase=None, phase_confidence=None,
            phase_reason=None,
        )
        limit_stocks = [
            LimitStock(trade_date="20260729", stock_code="000001", stock_name="甲股",
                       limit_type="up", consecutive_boards=1,
                       first_limit_time="10:00:00", last_limit_time="10:00:00",
                       open_count=0, is_valid_limit_up=True),
        ]
        deps: Any = _FakePremiumDeps(
            limit_stocks_by_date={"20260729": limit_stocks},
            stock_daily_by_date={},  # 今日 stock_daily 缺失
        )
        assert _compute_yesterday_premium("20260730", yesterday, deps) is None

    def test_yesterday_premium_no_yesterday_limit_up(self) -> None:
        """昨日 limit_stocks 为空（昨日无涨停）→ 返回 None。"""
        from domain.stock.models import EmotionIndicators
        from infrastructure.stock.emotion_daily_fetcher import _compute_yesterday_premium

        yesterday = EmotionIndicators(
            trade_date="20260729",
            limit_up_count=0, limit_down_count=0, valid_limit_up_count=0,
            broken_limit_ratio=0.0, max_consecutive_boards=0,
            yesterday_limit_up_today_premium=None, total_volume=None,
            volume_change_pct=None, phase=None, phase_confidence=None,
            phase_reason=None,
        )
        deps: Any = _FakePremiumDeps(
            limit_stocks_by_date={"20260729": []},
            stock_daily_by_date={"20260730": []},
        )
        assert _compute_yesterday_premium("20260730", yesterday, deps) is None


class TestEmotionCycleFetcherIntegration:
    """Task 3：fetcher 写入情绪周期字段（emotion_phase / emotion_score / 风格得分）。

    Task 3 仅改 fetcher 计算逻辑 + DTO 字段；读写路径（cache_repository 写 /
    sqlite_data_source 读）属 Task 4，故本测试通过 spy 捕获传给 upsert_emotion_daily
    的 EmotionIndicators 验证新字段，不依赖 DB 持久化读回。
    """

    @pytest.mark.asyncio
    async def test_emotion_phase_written(self, tmp_db) -> None:
        """完整 fetcher 流程 → 捕获 EmotionIndicators，验证情绪周期字段被写入。

        昨日 2 涨停（600000/600001），今日 stock_daily 涨幅 6.0%/-2.0%
        → 昨日涨停今日溢价 = (6.0 + -2.0) / 2 = 2.0。
        """
        from domain.stock.models import LimitStock, StockDaily
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.emotion_daily_fetcher_adapter import (
            EmotionDailyFetcherAdapter,
        )
        from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

        adapter = EmotionDailyFetcherAdapter(
            data_source=SqliteStockDataSource(conn=get_connection()),
        )
        repo = CacheRepository(conn=get_connection())

        # 1. 历史 emotion_daily（近 10 日，用于 day_3d_ago + percentile + trend）
        _seed_history_emotion(repo, end_date="20260729", days=10)

        # 2. 昨日 limit_stocks + 今日 stock_daily（用于溢价 + 韧性）
        yesterday_stocks = [
            LimitStock(trade_date="20260729", stock_code="600000", stock_name="A",
                       limit_type="up", consecutive_boards=2,
                       first_limit_time="10:00:00", last_limit_time="10:00:00",
                       open_count=0, is_valid_limit_up=True),
            LimitStock(trade_date="20260729", stock_code="600001", stock_name="B",
                       limit_type="up", consecutive_boards=1,
                       first_limit_time="10:30:00", last_limit_time="10:30:00",
                       open_count=0, is_valid_limit_up=True),
        ]
        repo.upsert_limit_stocks(trade_date="20260729", stocks=yesterday_stocks)
        today_stocks = [
            StockDaily(trade_date="20260730", stock_code="600000",
                       open=10.0, close=10.6, high=10.8, low=9.9,
                       volume=1e6, pct_chg=6.0, turnover=1e7),
            StockDaily(trade_date="20260730", stock_code="600001",
                       open=10.0, close=9.8, high=10.1, low=9.7,
                       volume=5e5, pct_chg=-2.0, turnover=5e6),
        ]
        repo.upsert_stock_daily(trade_date="20260730", rows=today_stocks)

        # 3. 今日 limit_stocks（用于 valid_count + max_boards）
        _seed_limit_stocks(repo, trade_date="20260730")

        # 4. mock akshare + spy 捕获 upsert 的 EmotionIndicators
        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            mock_ak.stock_market_activity_legu.return_value = _fake_activity_df()
            mock_ak.stock_zh_index_spot_em.return_value = pd.DataFrame(
                [{"code": "sh000001", "成交额": 1.2e12}]
            )
            mock_ak.stock_fund_flow_individual.return_value = _fake_fund_flow_df()
            with patch.object(
                repo, "upsert_emotion_daily", wraps=repo.upsert_emotion_daily
            ) as spy:
                count = await adapter.run(trade_date="20260730", repo=repo)

        assert count == 1
        # 捕获传给 upsert_emotion_daily 的 EmotionIndicators（不依赖读路径）
        captured = spy.call_args.kwargs["rows"][0]

        # 昨日涨停今日溢价：(6.0 + -2.0) / 2 = 2.0
        assert captured.yesterday_limit_up_today_premium == pytest.approx(2.0)

        # 三风格得分（打板 / 趋势始终可算；反包可能 None 但本场景有断板反包数据）
        assert captured.board_style_score is not None
        assert 0 <= captured.board_style_score <= 100
        assert captured.trend_style_score is not None
        assert 0 <= captured.trend_style_score <= 100

        # 全局情绪得分 0-100
        assert captured.emotion_score is not None
        assert 0 <= captured.emotion_score <= 100

        # 阶段为 6 阶段之一
        assert captured.emotion_phase in {
            "冰点", "强分歧", "弱分歧", "弱修复", "强修复", "高潮"
        }

    @pytest.mark.asyncio
    async def test_emotion_cycle_no_history_uses_neutral_momentum(self, tmp_db) -> None:
        """无历史 emotion_daily（冷启动）→ day_3d_ago=None，动量视为 0，阶段按得分粗判。

        此时 score_3d_ago=None → compute_raw_phase 动量=0；emotion_phase 仍为合法阶段。
        """
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.emotion_daily_fetcher_adapter import (
            EmotionDailyFetcherAdapter,
        )
        from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

        adapter = EmotionDailyFetcherAdapter(
            data_source=SqliteStockDataSource(conn=get_connection()),
        )
        repo = CacheRepository(conn=get_connection())
        # 不 seed 历史 emotion_daily（冷启动）
        _seed_limit_stocks(repo, trade_date="20260730")

        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            mock_ak.stock_market_activity_legu.return_value = _fake_activity_df()
            mock_ak.stock_zh_index_spot_em.return_value = pd.DataFrame(
                [{"code": "sh000001", "成交额": 1.0e12}]
            )
            mock_ak.stock_fund_flow_individual.return_value = _fake_fund_flow_df()
            with patch.object(
                repo, "upsert_emotion_daily", wraps=repo.upsert_emotion_daily
            ) as spy:
                count = await adapter.run(trade_date="20260730", repo=repo)

        assert count == 1
        captured = spy.call_args.kwargs["rows"][0]
        # 冷启动：昨日无数据 → 溢价 None
        assert captured.yesterday_limit_up_today_premium is None
        # 但得分与阶段仍可计算（board 用 limit_up_count 降级，trend 用 top20）
        assert captured.emotion_score is not None
        assert captured.emotion_phase in {
            "冰点", "强分歧", "弱分歧", "弱修复", "强修复", "高潮"
        }
