"""板块轮动 fallback 单元测试。

Bug③ 修复：``SqliteStockDataSource.get_sector_rotation`` 当 trade_date
无 sector_daily 数据时（周末/节假日）回退到 <= trade_date 的最近
有数据交易日。
"""
from __future__ import annotations

import os

import pytest

from infrastructure.persistence.connection import get_connection
from infrastructure.persistence.database import init_db, reset_connection


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_sector_rotation_fallback.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()
    if db_path.exists():
        os.unlink(db_path)


def _insert_sector(
    conn, *, trade_date: str, sector_code: str, sector_name: str,
    pct_chg: float, leading_stock_codes: str = "[]",
    limit_up_count: int = 0,
) -> None:
    conn.execute(
        "INSERT INTO sector_daily "
        "(trade_date, sector_code, sector_name, pct_chg, "
        "leading_stock_codes, limit_up_count) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            trade_date, sector_code, sector_name, pct_chg,
            leading_stock_codes, limit_up_count,
        ),
    )
    conn.commit()


@pytest.mark.asyncio
async def test_get_sector_rotation_falls_back_to_latest_trading_day(tmp_db) -> None:
    """周六 8-2 查询 → fallback 到 7-31 的 sector_daily。"""
    from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

    conn = get_connection(tmp_db)
    _insert_sector(
        conn, trade_date="20260731", sector_code="881201",
        sector_name="IT 服务", pct_chg=6.28, limit_up_count=2,
    )
    _insert_sector(
        conn, trade_date="20260731", sector_code="881202",
        sector_name="半导体", pct_chg=4.5, limit_up_count=1,
    )

    ds = SqliteStockDataSource(conn=conn)
    rows = await ds.get_sector_rotation("20260802")  # 周六

    assert len(rows) == 2
    for r in rows:
        assert r.trade_date == "20260731"  # fallback 日期


@pytest.mark.asyncio
async def test_get_sector_rotation_no_data_returns_empty(tmp_db) -> None:
    """cache 完全为空 → fallback 失败 → 返空列表（行为同旧版）。"""
    from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

    conn = get_connection(tmp_db)
    ds = SqliteStockDataSource(conn=conn)

    rows = await ds.get_sector_rotation("20260802")

    assert rows == []


# ── get_sector_history 多日查询 SQL 修复 ──────────────────


@pytest.mark.asyncio
async def test_get_sector_history_returns_all_sectors_for_n_days(tmp_db) -> None:
    """Bug 修复：原 LIMIT ? 限制行数而非天数，90 板块 × 1 天 = 90 行，
    LIMIT 10 只返 10 行（1 天的部分板块）。

    修复后：子查询先取 N 个交易日，再关联全板块 → N 天 × 所有板块。
    """
    from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

    conn = get_connection(tmp_db)
    # 3 天 × 5 板块 = 15 行
    for dt in ("20260729", "20260730", "20260731"):
        for i in range(5):
            _insert_sector(
                conn, trade_date=dt, sector_code=f"88120{i}",
                sector_name=f"板块{i}", pct_chg=float(i),
            )

    ds = SqliteStockDataSource(conn=conn)
    # 请求 3 天全板块 → 应返回 3 × 5 = 15 行（而非 LIMIT 3 = 3 行）
    rows = await ds.get_sector_history("", 3, "20260731")

    assert len(rows) == 15
    dates = {r.trade_date for r in rows}
    assert dates == {"20260729", "20260730", "20260731"}


@pytest.mark.asyncio
async def test_get_sector_history_end_date_filters_future(tmp_db) -> None:
    """end_date=20260730 → 不返回 20260731 的数据。"""
    from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

    conn = get_connection(tmp_db)
    for dt in ("20260730", "20260731"):
        _insert_sector(
            conn, trade_date=dt, sector_code="881201",
            sector_name="IT 服务", pct_chg=1.0,
        )

    ds = SqliteStockDataSource(conn=conn)
    rows = await ds.get_sector_history("", 10, "20260730")

    dates = {r.trade_date for r in rows}
    assert dates == {"20260730"}
    assert "20260731" not in dates


@pytest.mark.asyncio
async def test_get_sector_history_by_name_filters_sector(tmp_db) -> None:
    """sector_name 非空 → 只返回该板块的多日数据。"""
    from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

    conn = get_connection(tmp_db)
    for dt in ("20260730", "20260731"):
        _insert_sector(
            conn, trade_date=dt, sector_code="881201",
            sector_name="IT 服务", pct_chg=1.0,
        )
        _insert_sector(
            conn, trade_date=dt, sector_code="881202",
            sector_name="半导体", pct_chg=2.0,
        )

    ds = SqliteStockDataSource(conn=conn)
    rows = await ds.get_sector_history("IT 服务", 10, "20260731")

    assert len(rows) == 2
    assert all(r.sector_name == "IT 服务" for r in rows)
