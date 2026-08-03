"""Task 4 集成测试：情绪周期 5 字段读写路径 round-trip。

覆盖：
- ``CacheRepository.upsert_emotion_daily`` 写入 5 个 v025 字段
- ``CacheRepository.select_emotion_daily`` 读回 5 个字段一致
- ``SqliteStockDataSource.get_emotion_indicators`` 读回 5 个字段一致
- ``SqliteStockDataSource.get_emotion_indicators_trend`` 趋势查询读回 5 个字段
- NULL 语义：老行（v025 之前）5 个字段为 NULL → 读回 None
- API ``GET /api/v1/stock/charts/emotion`` 响应包含 5 个新字段
"""

from __future__ import annotations

import os

import pytest

from infrastructure.persistence.connection import get_connection
from infrastructure.persistence.database import init_db, reset_connection


# ── fixtures ──────────────────────────────────────────────


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_emotion_cycle_roundtrip.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()
    if db_path.exists():
        os.unlink(db_path)


def _make_full_emotion(trade_date: str):
    """构造一个所有 v025 字段都填值的 EmotionIndicators。"""
    from domain.stock.models import EmotionIndicators

    return EmotionIndicators(
        trade_date=trade_date,
        limit_up_count=40,
        limit_down_count=5,
        valid_limit_up_count=35,
        broken_limit_ratio=0.15,
        max_consecutive_boards=4,
        yesterday_limit_up_today_premium=2.5,
        total_volume=1.2e12,
        volume_change_pct=0.08,
        phase=None,
        phase_confidence=None,
        phase_reason=None,
        # v025 情绪周期字段
        board_style_score=72.5,
        trend_style_score=58.0,
        rebound_style_score=45.0,
        emotion_score=58.5,
        emotion_phase="强修复",
    )


# ── CacheRepository round-trip ─────────────────────────────


class TestCacheRepositoryRoundTrip:
    """写路径 + 读路径 1（cache_repository.select_emotion_daily）。"""

    def test_v025_fields_round_trip(self, tmp_db) -> None:
        """upsert → select 全字段一致（含 5 个 v025 新字段）。"""
        from infrastructure.stock.cache_repository import CacheRepository

        repo = CacheRepository(conn=get_connection())
        row = _make_full_emotion("20260730")
        repo.upsert_emotion_daily(trade_date="20260730", rows=[row])

        read_back = repo.select_emotion_daily(trade_date="20260730")
        assert len(read_back) == 1
        r = read_back[0]
        # v025 新字段
        assert r.board_style_score == pytest.approx(72.5)
        assert r.trend_style_score == pytest.approx(58.0)
        assert r.rebound_style_score == pytest.approx(45.0)
        assert r.emotion_score == pytest.approx(58.5)
        assert r.emotion_phase == "强修复"
        # 既有字段不破坏
        assert r.yesterday_limit_up_today_premium == pytest.approx(2.5)
        assert r.limit_up_count == 40

    def test_v025_fields_none_round_trip(self, tmp_db) -> None:
        """v025 字段为 None 时 round-trip 仍为 None（不变 0/''）。"""
        from domain.stock.models import EmotionIndicators
        from infrastructure.stock.cache_repository import CacheRepository

        repo = CacheRepository(conn=get_connection())
        row = EmotionIndicators(
            trade_date="20260730",
            limit_up_count=10, limit_down_count=2,
            valid_limit_up_count=8, broken_limit_ratio=0.1,
            max_consecutive_boards=2,
            yesterday_limit_up_today_premium=None,
            total_volume=None, volume_change_pct=None,
            phase=None, phase_confidence=None, phase_reason=None,
            # v025 字段全部 None
            board_style_score=None,
            trend_style_score=None,
            rebound_style_score=None,
            emotion_score=None,
            emotion_phase=None,
        )
        repo.upsert_emotion_daily(trade_date="20260730", rows=[row])

        r = repo.select_emotion_daily(trade_date="20260730")[0]
        assert r.board_style_score is None
        assert r.trend_style_score is None
        assert r.rebound_style_score is None
        assert r.emotion_score is None
        assert r.emotion_phase is None

    def test_old_row_without_v025_columns_reads_none(self, tmp_db) -> None:
        """v025 迁移前的老行（5 列 NULL）读回 None。"""
        conn = get_connection()
        # 手动插入一行只填 v021 既有字段（模拟老行）
        conn.execute(
            "INSERT INTO emotion_daily "
            "(trade_date, limit_up_count, limit_down_count, "
            "valid_limit_up_count, broken_limit_ratio, max_consecutive_boards, "
            "yesterday_limit_up_today_premium, total_volume, volume_change_pct, "
            "phase, phase_confidence, phase_reason) "
            "VALUES (?, 50, 5, 40, 0.1, 3, NULL, 1e12, 0.05, NULL, NULL, NULL)",
            ("20260715",),
        )
        conn.commit()

        from infrastructure.stock.cache_repository import CacheRepository

        repo = CacheRepository(conn=get_connection())
        r = repo.select_emotion_daily(trade_date="20260715")[0]
        # 老行 5 个 v025 字段必须为 None
        assert r.board_style_score is None
        assert r.trend_style_score is None
        assert r.rebound_style_score is None
        assert r.emotion_score is None
        assert r.emotion_phase is None
        # 既有字段保留
        assert r.limit_up_count == 50


# ── SqliteStockDataSource round-trip ───────────────────────


class TestSqliteDataSourceRoundTrip:
    """读路径 2（sqlite_data_source.get_emotion_indicators / _trend）。"""

    @pytest.mark.asyncio
    async def test_get_emotion_indicators_reads_v025(self, tmp_db) -> None:
        """get_emotion_indicators 读回 5 个 v025 字段。"""
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

        repo = CacheRepository(conn=get_connection())
        repo.upsert_emotion_daily(
            trade_date="20260730", rows=[_make_full_emotion("20260730")]
        )

        ds = SqliteStockDataSource(conn=get_connection())
        emo = await ds.get_emotion_indicators("20260730")
        assert emo is not None
        assert emo.board_style_score == pytest.approx(72.5)
        assert emo.trend_style_score == pytest.approx(58.0)
        assert emo.rebound_style_score == pytest.approx(45.0)
        assert emo.emotion_score == pytest.approx(58.5)
        assert emo.emotion_phase == "强修复"

    @pytest.mark.asyncio
    async def test_get_emotion_indicators_before_reads_v025(self, tmp_db) -> None:
        """get_emotion_indicators_before 读回 5 个 v025 字段。"""
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

        repo = CacheRepository(conn=get_connection())
        repo.upsert_emotion_daily(
            trade_date="20260729", rows=[_make_full_emotion("20260729")]
        )

        ds = SqliteStockDataSource(conn=get_connection())
        emo = await ds.get_emotion_indicators_before("20260730")
        assert emo is not None
        assert emo.board_style_score == pytest.approx(72.5)
        assert emo.emotion_phase == "强修复"

    @pytest.mark.asyncio
    async def test_get_emotion_indicators_trend_reads_v025(self, tmp_db) -> None:
        """get_emotion_indicators_trend 趋势查询读回 5 个 v025 字段。"""
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

        repo = CacheRepository(conn=get_connection())
        # 写 3 日数据
        for d, score in [("20260728", 30.0), ("20260729", 50.0), ("20260730", 70.0)]:
            row = _make_full_emotion(d)
            # 覆盖 emotion_score 便于区分
            object.__setattr__(row, "emotion_score", score)
            object.__setattr__(row, "emotion_phase", "弱修复" if score < 50 else "强修复")
            repo.upsert_emotion_daily(trade_date=d, rows=[row])

        ds = SqliteStockDataSource(conn=get_connection())
        trend = await ds.get_emotion_indicators_trend("20260730", days=3)
        by_date = {e.trade_date: e for e in trend}
        assert by_date["20260730"].emotion_score == pytest.approx(70.0)
        assert by_date["20260729"].emotion_score == pytest.approx(50.0)
        assert by_date["20260728"].emotion_score == pytest.approx(30.0)
        assert by_date["20260730"].emotion_phase == "强修复"
        assert by_date["20260728"].emotion_phase == "弱修复"


# ── API 序列化验证 ─────────────────────────────────────────


class TestEmotionCycleApiSerialization:
    """API ``GET /api/v1/stock/charts/emotion`` 序列化包含 5 个 v025 字段。

    直接测 ``api.v1.stock._emotion_dict`` 序列化函数——该函数是
    ``GET /charts/emotion`` 端点把 EmotionIndicators 转 dict 的唯一入口，
    覆盖它即覆盖 API 响应字段（开发文档 §7.4：无需新增端点，序列化自动包含）。
    """

    def test_emotion_dict_includes_v025_fields(self) -> None:
        """_emotion_dict 输出 dict 含 5 个 v025 字段且值与 DTO 一致。"""
        from api.v1.stock import _emotion_dict

        row = _make_full_emotion("20260730")
        d = _emotion_dict(row)
        # v025 字段
        assert d["board_style_score"] == pytest.approx(72.5)
        assert d["trend_style_score"] == pytest.approx(58.0)
        assert d["rebound_style_score"] == pytest.approx(45.0)
        assert d["emotion_score"] == pytest.approx(58.5)
        assert d["emotion_phase"] == "强修复"
        # 既有字段不破坏
        assert d["limit_up_count"] == 40
        assert d["yesterday_limit_up_today_premium"] == pytest.approx(2.5)

    def test_emotion_dict_v025_none_passes_through(self) -> None:
        """_emotion_dict 对 None 字段输出 None（不转 0/''）。"""
        from domain.stock.models import EmotionIndicators
        from api.v1.stock import _emotion_dict

        row = EmotionIndicators(
            trade_date="20260730",
            limit_up_count=10, limit_down_count=2,
            valid_limit_up_count=8, broken_limit_ratio=0.1,
            max_consecutive_boards=2,
            yesterday_limit_up_today_premium=None,
            total_volume=None, volume_change_pct=None,
            phase=None, phase_confidence=None, phase_reason=None,
        )
        d = _emotion_dict(row)
        assert d["board_style_score"] is None
        assert d["trend_style_score"] is None
        assert d["rebound_style_score"] is None
        assert d["emotion_score"] is None
        assert d["emotion_phase"] is None
