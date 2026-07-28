"""Task 1 集成测试：迁移 v021 必须创建 8 张股票数据表。

覆盖：
- registry 1..21 连续（无空缺、无重复）
- init_db 到 v021 后，8 张表全部存在
- 关键索引存在
- downgrade(20) 后，8 张表全部消失
- 幂等：两次 init_db 不报错
- 既有表（migration 1..20）不被破坏
"""

from __future__ import annotations

import os

import pytest

from infrastructure.persistence.connection import get_connection
from infrastructure.persistence.database import (
    get_migration_status,
    init_db,
    reset_connection,
)
from infrastructure.persistence.migrations.runner import downgrade


EXPECTED_TABLES = [
    "market_index_daily",
    "stock_daily",
    "limit_stocks_daily",
    "board_ladder_daily",
    "sector_daily",
    "emotion_daily",
    "watchlist_stocks",
    "review_reports",
]

EXPECTED_INDEXES = [
    "idx_market_index_date",
    "idx_stock_daily_code_date",
    "idx_limit_stocks_date",
    "idx_board_ladder_date",
    "idx_sector_daily_date",
    "idx_emotion_daily_date",
    "idx_watchlist_stocks_status",
    "idx_review_reports_user_date",
]


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_migration_v021.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    yield db_path
    reset_connection()
    if db_path.exists():
        os.unlink(db_path)


def test_registry_validates_1_to_21() -> None:
    """registry 必须包含 1..21 连续版本。"""
    from infrastructure.persistence.migrations.registry import MIGRATIONS

    versions = [m.version for m in MIGRATIONS]
    assert versions == list(range(1, 22)), f"版本不连续或重复: {versions}"


def test_migration_v021_creates_all_tables(tmp_db) -> None:
    """迁移到 v021 后，8 张表必须存在。"""
    init_db(tmp_db)

    status = get_migration_status()
    assert status["current_version"] >= 21, f"current_version={status['current_version']}"

    conn = get_connection(tmp_db)
    try:
        for table in EXPECTED_TABLES:
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            )
            assert cur.fetchone() is not None, f"表 {table} 未创建"
    finally:
        conn.close()


def test_migration_v021_creates_indexes(tmp_db) -> None:
    """关键索引必须创建。"""
    init_db(tmp_db)

    conn = get_connection(tmp_db)
    try:
        for index in EXPECTED_INDEXES:
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
                (index,),
            )
            assert cur.fetchone() is not None, f"索引 {index} 未创建"
    finally:
        conn.close()


def test_migration_v021_down_drops_tables(tmp_db) -> None:
    """downgrade(20) 后 8 张表必须消失。"""
    init_db(tmp_db)
    downgrade(target_version=20)

    conn = get_connection(tmp_db)
    try:
        for table in EXPECTED_TABLES:
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            )
            assert cur.fetchone() is None, f"表 {table} 未被删除"
    finally:
        conn.close()


def test_migration_v021_idempotent(tmp_db) -> None:
    """运行两次 init_db 不应报错。"""
    init_db(tmp_db)
    reset_connection()
    init_db(tmp_db)

    status = get_migration_status()
    assert status["current_version"] >= 21


def test_migration_v021_preserves_existing_tables(tmp_db) -> None:
    """既有表（users / news_sources 等）必须保留。"""
    init_db(tmp_db)

    conn = get_connection(tmp_db)
    try:
        for table in ("users", "sessions", "news_sources"):
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            )
            assert cur.fetchone() is not None, f"既有表 {table} 不应被破坏"
    finally:
        conn.close()
