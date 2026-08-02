"""股票数据源 SQLite 实现的回归测试。

覆盖：
- ``SqliteStockDataSource.get_stock_daily`` 必须能取到 ``turnover`` 字段；
  历史版本 SELECT 列表漏选 ``turnover`` 导致 ``sqlite3.Row`` 抛 IndexError。

不依赖任何网络或 akshare，全部走内存化 sqlite。
"""

from __future__ import annotations

import os

import pytest

from infrastructure.persistence.connection import get_connection
from infrastructure.persistence.database import init_db, reset_connection


# ── fixtures ──────────────────────────────────────────────


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_sqlite_stock_ds.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()
    if db_path.exists():
        os.unlink(db_path)


def _insert_stock_daily(
    conn,
    *,
    stock_code: str,
    trade_date: str,
    turnover: float | None,
) -> None:
    """直接往 stock_daily 写一行（含 turnover）。"""
    conn.execute(
        "INSERT INTO stock_daily "
        "(trade_date, stock_code, open, close, high, low, volume, pct_chg, turnover) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            trade_date,
            stock_code,
            10.0,  # open
            10.5,  # close
            10.8,  # high
            9.9,   # low
            1_000_000.0,  # volume
            5.0,   # pct_chg
            turnover,
        ),
    )
    conn.commit()


# ── get_stock_daily ───────────────────────────────────────


async def test_get_stock_daily_reads_turnover_column(tmp_db) -> None:
    """``get_stock_daily`` SELECT 必须含 turnover；历史上漏选导致 IndexError。

    回归场景：用户调用工具 ``get_stock_daily(stock_code='603221', days=15)``，
    数据源 SELECT 列表漏掉 turnover 列，``sqlite3.Row['turnover']`` 直接抛
    ``IndexError: No item with that key``，工具结果被打包成 is_error。
    """
    from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

    conn = get_connection(tmp_db)
    _insert_stock_daily(
        conn,
        stock_code="603221",
        trade_date="20260801",
        turnover=12_950_000.0,
    )

    ds = SqliteStockDataSource(conn=conn)
    rows = await ds.get_stock_daily(stock_code="603221", days=15)

    assert len(rows) == 1
    assert rows[0].stock_code == "603221"
    assert rows[0].trade_date == "20260801"
    # 关键断言：turnover 字段不能丢失；修复前 SELECT 漏列会抛 IndexError。
    assert rows[0].turnover == pytest.approx(12_950_000.0)


async def test_get_stock_daily_handles_none_turnover(tmp_db) -> None:
    """turnover 允许为 NULL，模型字段是 ``float | None``，不能因 None 报错。"""
    from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

    conn = get_connection(tmp_db)
    _insert_stock_daily(
        conn,
        stock_code="603221",
        trade_date="20260801",
        turnover=None,
    )

    ds = SqliteStockDataSource(conn=conn)
    rows = await ds.get_stock_daily(stock_code="603221", days=15)

    assert len(rows) == 1
    assert rows[0].turnover is None


async def test_get_stock_daily_orders_by_trade_date_desc(tmp_db) -> None:
    """多日数据时按 trade_date DESC 取最近 N 天（与 LIMIT 行为一致）。"""
    from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

    conn = get_connection(tmp_db)
    for d, to in (
        ("20260730", 1_000_000.0),
        ("20260731", 2_000_000.0),
        ("20260801", 3_000_000.0),
    ):
        _insert_stock_daily(
            conn,
            stock_code="603221",
            trade_date=d,
            turnover=to,
        )

    ds = SqliteStockDataSource(conn=conn)
    rows = await ds.get_stock_daily(stock_code="603221", days=2)

    # LIMIT 2 DESC → 取最近两天
    assert [r.trade_date for r in rows] == ["20260801", "20260731"]
    assert [r.turnover for r in rows] == [pytest.approx(3_000_000.0), pytest.approx(2_000_000.0)]
