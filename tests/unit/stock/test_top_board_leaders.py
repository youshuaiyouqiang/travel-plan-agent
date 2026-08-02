"""情绪指标 DTO 回归测试。

覆盖：
- ``CacheRepository.select_emotion_daily`` 返 ``EmotionIndicators.top_board_leaders``
  应包含 max_consecutive_boards 对应股票代码（不止 1 个，支持同日并列龙头）。
- ``SqliteStockDataSource.get_emotion_indicators`` 同样补齐 leaders。
- ``SqliteStockDataSource.get_emotion_indicators_trend`` 在趋势查询中也返回 leaders。
"""

from __future__ import annotations

import os

import pytest

from infrastructure.persistence.connection import get_connection
from infrastructure.persistence.database import init_db, reset_connection


# ── fixtures ──────────────────────────────────────────────


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_top_board.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()
    if db_path.exists():
        os.unlink(db_path)


def _seed_emotion_row(conn, trade_date: str, max_boards: int) -> None:
    """只填 emotion_daily 必要字段（不触 limit_stocks_daily join 不便）。"""
    conn.execute(
        "INSERT INTO emotion_daily "
        "(trade_date, limit_up_count, limit_down_count, "
        "valid_limit_up_count, broken_limit_ratio, max_consecutive_boards) "
        "VALUES (?, 0, 0, 0, 0.0, ?)",
        (trade_date, max_boards),
    )
    conn.commit()


def _seed_limit_stock(
    conn,
    *,
    trade_date: str,
    stock_code: str,
    stock_name: str,
    consecutive_boards: int,
) -> None:
    conn.execute(
        "INSERT INTO limit_stocks_daily "
        "(trade_date, stock_code, stock_name, limit_type, "
        "consecutive_boards, first_limit_time, last_limit_time, "
        "open_count, is_valid_limit_up) "
        "VALUES (?, ?, ?, 'up', ?, '10:00:00', '10:00:00', 0, 1)",
        (trade_date, stock_code, stock_name, consecutive_boards),
    )
    conn.commit()


# ── 测试 ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cache_select_emotion_daily_includes_top_board_leaders(tmp_db) -> None:
    """读到 emotion_daily 时必须把 max_boards 对应股票代码填到 DTO。"""
    from infrastructure.stock.cache_repository import CacheRepository

    conn = get_connection(tmp_db)
    _seed_emotion_row(conn, "20260731", max_boards=9)
    _seed_limit_stock(
        conn,
        trade_date="20260731",
        stock_code="603221",
        stock_name="某 9 板股",
        consecutive_boards=9,
    )
    _seed_limit_stock(
        conn,
        trade_date="20260731",
        stock_code="603222",
        stock_name="另一 9 板股",
        consecutive_boards=9,  # 同日并列龙头
    )
    _seed_limit_stock(
        conn,
        trade_date="20260731",
        stock_code="605179",
        stock_name="某 4 板股",
        consecutive_boards=4,  # 不是龙头，不应进入 leaders
    )

    repo = CacheRepository(conn=conn)
    rows = repo.select_emotion_daily(trade_date="20260731")

    assert len(rows) == 1
    leaders = rows[0].top_board_leaders
    assert isinstance(leaders, list)
    assert sorted(leaders) == ["603221", "603222"]
    assert "605179" not in leaders


@pytest.mark.asyncio
async def test_data_source_get_emotion_indicators_includes_leaders(tmp_db) -> None:
    """SqliteStockDataSource.get_emotion_indicators 同样补 leaders。"""
    from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

    conn = get_connection(tmp_db)
    _seed_emotion_row(conn, "20260731", max_boards=5)
    _seed_limit_stock(
        conn,
        trade_date="20260731",
        stock_code="000003",
        stock_name="A",
        consecutive_boards=5,
    )

    ds = SqliteStockDataSource(conn=conn)
    emo = await ds.get_emotion_indicators("20260731")

    assert emo.top_board_leaders == ["000003"]


@pytest.mark.asyncio
async def test_data_source_get_emotion_trend_includes_leaders(tmp_db) -> None:
    """get_emotion_indicators_trend 多日趋势，每行各自带 leaders。"""
    from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

    conn = get_connection(tmp_db)
    _seed_emotion_row(conn, "20260730", max_boards=8)
    _seed_emotion_row(conn, "20260731", max_boards=9)
    _seed_limit_stock(
        conn,
        trade_date="20260730",
        stock_code="111111",
        stock_name="X",
        consecutive_boards=8,
    )
    _seed_limit_stock(
        conn,
        trade_date="20260731",
        stock_code="222222",
        stock_name="Y",
        consecutive_boards=9,
    )

    ds = SqliteStockDataSource(conn=conn)
    trend = await ds.get_emotion_indicators_trend("20260731", days=5)

    by_date = {e.trade_date: e for e in trend}
    assert by_date["20260730"].top_board_leaders == ["111111"]
    assert by_date["20260731"].top_board_leaders == ["222222"]


@pytest.mark.asyncio
async def test_leaders_empty_when_no_limit_stocks(tmp_db) -> None:
    """limit_stocks_daily 没该日行（冰点期）→ leaders 为空列表，不抛错。"""
    from infrastructure.stock.cache_repository import CacheRepository

    conn = get_connection(tmp_db)
    _seed_emotion_row(conn, "20260731", max_boards=0)

    repo = CacheRepository(conn=conn)
    rows = repo.select_emotion_daily(trade_date="20260731")

    assert rows[0].top_board_leaders == []
