"""Task 3 失败测试：缓存仓储 SQL 注入防护 + 表名白名单 + 基础 upsert/select。

覆盖：
- ALLOWED_TABLES 包含 8 张业务表且拒绝未知表名
- SQL 注入尝试：stock_code 含 DROP TABLE 语句时表必须保留、数据按字面量存储
- 基础 upsert + select round-trip

运行前 infrastructure/stock/cache_repository.py 不存在，本测试应全部失败。
"""

from __future__ import annotations

import os

import pytest

from infrastructure.persistence.connection import get_connection
from infrastructure.persistence.database import init_db, reset_connection


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_cache_repo.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()
    if db_path.exists():
        os.unlink(db_path)


def test_table_name_whitelist_includes_business_tables() -> None:
    """ALLOWED_TABLES 必须包含 8 张业务表。"""
    from infrastructure.stock.cache_repository import ALLOWED_TABLES

    for table in (
        "market_index_daily",
        "stock_daily",
        "limit_stocks_daily",
        "board_ladder_daily",
        "sector_daily",
        "emotion_daily",
        "watchlist_stocks",
        "review_reports",
    ):
        assert table in ALLOWED_TABLES, f"白名单缺失业务表 {table}"


def test_table_name_whitelist_rejects_unknown_table() -> None:
    """动态表名不在白名单时必须拒绝（AGENTS.md §4 安全与数据）。"""
    from infrastructure.stock.cache_repository import ALLOWED_TABLES

    assert "evil_table" not in ALLOWED_TABLES
    assert "users" not in ALLOWED_TABLES  # 业务表外的核心表也禁


def test_parameterized_sql_prevents_injection(tmp_db) -> None:
    """SQL 必须参数化：恶意 stock_code 不能 DROP 表。"""
    from infrastructure.stock.cache_repository import CacheRepository
    from domain.stock.models import LimitStock

    repo = CacheRepository(get_connection(tmp_db))
    malicious_code = "'; DROP TABLE market_index_daily; --"
    repo.upsert_limit_stocks(
        trade_date="20260728",
        stocks=[
            LimitStock(
                trade_date="20260728",
                stock_code=malicious_code,
                stock_name="X",
                limit_type="up",
                consecutive_boards=1,
                first_limit_time="09:30:00",
                last_limit_time="09:30:00",
                open_count=0,
                is_valid_limit_up=True,
            )
        ],
    )

    conn = get_connection(tmp_db)
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='market_index_daily'"
        )
        assert cur.fetchone() is not None, "market_index_daily 表被 SQL 注入删除"
        row = conn.execute(
            "SELECT stock_code FROM limit_stocks_daily WHERE trade_date=?",
            ("20260728",),
        ).fetchone()
        assert row is not None
        assert row["stock_code"] == malicious_code  # 数据按字面量存储
    finally:
        conn.close()


def test_upsert_and_select_limit_stocks_roundtrip(tmp_db) -> None:
    """upsert 后 select 必须能读到一致数据。"""
    from infrastructure.stock.cache_repository import CacheRepository
    from domain.stock.models import LimitStock

    repo = CacheRepository(get_connection(tmp_db))
    stocks = [
        LimitStock(
            trade_date="20260728",
            stock_code="000001",
            stock_name="平安银行",
            limit_type="up",
            consecutive_boards=1,
            first_limit_time="09:30:00",
            last_limit_time="09:30:00",
            open_count=0,
            is_valid_limit_up=True,
        ),
        LimitStock(
            trade_date="20260728",
            stock_code="000002",
            stock_name="万科A",
            limit_type="up",
            consecutive_boards=3,
            first_limit_time="09:30:00",
            last_limit_time="14:20:00",
            open_count=1,
            is_valid_limit_up=False,
        ),
    ]
    repo.upsert_limit_stocks(trade_date="20260728", stocks=stocks)

    rows = repo.select_limit_stocks(trade_date="20260728")
    assert len(rows) == 2
    codes = {r.stock_code for r in rows}
    assert codes == {"000001", "000002"}
    by_code = {r.stock_code: r for r in rows}
    assert by_code["000001"].is_valid_limit_up is True
    assert by_code["000002"].is_valid_limit_up is False
