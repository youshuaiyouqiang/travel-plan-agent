"""大盘快照读取路径回归测试。

覆盖：
- ``SqliteStockDataSource.get_market_snapshot`` 必须取 ``market_index_daily.volume``
  并把 sh_volume + sz_volume 求和写入 ``MarketSnapshot.total_volume``。

回归历史：原 SELECT 漏了 volume 列，导致前端"两市成交额"一直显示 ``—``。
"""

from __future__ import annotations

import os

import pytest

from infrastructure.persistence.connection import get_connection
from infrastructure.persistence.database import init_db, reset_connection


# ── fixtures ──────────────────────────────────────────────


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_market_snapshot.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()
    if db_path.exists():
        os.unlink(db_path)


def _insert_index(
    conn,
    *,
    trade_date: str,
    index_code: str,
    close: float,
    volume: float,
    pct_chg: float,
) -> None:
    conn.execute(
        "INSERT INTO market_index_daily "
        "(trade_date, index_code, open, close, high, low, volume, pct_chg) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            trade_date,
            index_code,
            close * 0.99,   # open
            close,
            close * 1.01,   # high
            close * 0.98,   # low
            volume,
            pct_chg,
        ),
    )
    conn.commit()


def _seed_emotion(conn, trade_date: str, total_volume: float | None) -> None:
    """emotion_daily.total_volume 用作 get_market_snapshot 的 fallback。"""
    conn.execute(
        "INSERT INTO emotion_daily "
        "(trade_date, limit_up_count, limit_down_count, "
        "valid_limit_up_count, broken_limit_ratio, max_consecutive_boards, "
        "total_volume) "
        "VALUES (?, 0, 0, 0, 0.0, 0, ?)",
        (trade_date, total_volume),
    )
    conn.commit()


# ── tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_market_snapshot_sums_sh_sz_volume(tmp_db) -> None:
    """market_index_daily.volume 在 sh+sz 求和 → MarketSnapshot.total_volume（元）。"""
    from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

    conn = get_connection(tmp_db)
    _insert_index(
        conn,
        trade_date="20260731",
        index_code="sh000001",
        close=3833.536,
        volume=5_975_294_2700.0,
        pct_chg=0.72,
    )
    _insert_index(
        conn,
        trade_date="20260731",
        index_code="sz399001",
        close=13689.995,
        volume=7_193_959_4436.0,
        pct_chg=2.21,
    )
    _insert_index(
        conn,
        trade_date="20260731",
        index_code="sz399006",
        close=3411.612,
        volume=2_361_709_4508.0,
        pct_chg=3.06,
    )

    ds = SqliteStockDataSource(conn=conn)
    snapshot = await ds.get_market_snapshot("20260731")

    assert snapshot.trade_date == "20260731"
    assert snapshot.sh_index == pytest.approx(3833.536)
    assert snapshot.sz_index == pytest.approx(13689.995)
    assert snapshot.cyb_index == pytest.approx(3411.612)
    # sh_volume + sz_volume（包含创业板，因为创业板的 volume 算深市）
    expected_total = 5_975_294_2700.0 + 7_193_959_4436.0 + 2_361_709_4508.0
    assert snapshot.total_volume == pytest.approx(expected_total)


@pytest.mark.asyncio
async def test_get_market_snapshot_missing_volume_falls_back(tmp_db) -> None:
    """market_index_daily 没 volume（极端空表）→ fallback emotion_daily.total_volume。"""
    from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

    conn = get_connection(tmp_db)
    _insert_index(
        conn,
        trade_date="20260731",
        index_code="sh000001",
        close=3500.0,
        volume=0.0,  # 故意 0，触发 fallback
        pct_chg=0.0,
    )
    _seed_emotion(conn, "20260731", total_volume=1.2e12)

    ds = SqliteStockDataSource(conn=conn)
    snapshot = await ds.get_market_snapshot("20260731")

    # sh 与 sz/cyb 都没 volume → total_volume 仍能从 emotion_daily 兜底
    assert snapshot.sh_index == pytest.approx(3500.0)
    assert snapshot.total_volume == pytest.approx(1.2e12)


@pytest.mark.asyncio
async def test_get_market_snapshot_no_data_returns_zeros(tmp_db) -> None:
    """cache 完全为空（warmup 未跑过）→ 返回 None 主键，但 status 字段是 int 默认 0 不爆。"""
    from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

    conn = get_connection(tmp_db)
    ds = SqliteStockDataSource(conn=conn)
    snapshot = await ds.get_market_snapshot("20260802")  # 周六，无数据

    assert snapshot.trade_date == "20260802"
    assert snapshot.sh_index is None
    assert snapshot.sz_index is None
    assert snapshot.cyb_index is None
    assert snapshot.total_volume is None
    assert snapshot.consecutive_down_days == 0


@pytest.mark.asyncio
async def test_get_market_snapshot_falls_back_to_latest_trading_day(tmp_db) -> None:
    """周六查询 → fallback 到最近交易日 20260731（market_index_daily 中最新 <= target）。

    修复：原版本直接 SELECT ... WHERE trade_date=周六 → 返空 → 前端所有卡片显示"—"。
    现在先 resolve 实际有数据的最近交易日，再用该日期查。
    """
    from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

    conn = get_connection(tmp_db)
    # seed 7-31 数据
    _insert_index(
        conn, trade_date="20260731", index_code="sh000001",
        close=3832.262, volume=5_975_294_2700.0, pct_chg=0.72,
    )
    _insert_index(
        conn, trade_date="20260731", index_code="sz399001",
        close=13578.93, volume=7_193_959_4436.0, pct_chg=2.21,
    )

    ds = SqliteStockDataSource(conn=conn)
    # 周六 8-2 查询 → 应 fallback 到 7-31
    snapshot = await ds.get_market_snapshot("20260802")

    assert snapshot.trade_date == "20260731"  # 已 fallback
    assert snapshot.sh_index == pytest.approx(3832.262)
    assert snapshot.sz_index == pytest.approx(13578.93)


@pytest.mark.asyncio
async def test_get_market_snapshot_does_not_fall_back_to_future(tmp_db) -> None:
    """target_date 早于 cache 中所有数据时 → 不回退到 target 之后。

    边界：forward-only 防御，避免被 cache 偷换为未来的数据。
    """
    from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

    conn = get_connection(tmp_db)
    _insert_index(
        conn, trade_date="20260731", index_code="sh000001",
        close=3832.262, volume=5e10, pct_chg=0.5,
    )

    ds = SqliteStockDataSource(conn=conn)
    # 查询 20260101（远早于 cache）→ cache 中只有 7-31 > 20260101 → 不应该 fallback 到 7-31
    snapshot = await ds.get_market_snapshot("20260101")

    assert snapshot.trade_date == "20260101"  # 保留 target
    assert snapshot.sh_index is None  # 无 fallback 数据
