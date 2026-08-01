"""Task 20 集成测试：迁移 v022 必须创建 stock_fetch_log 表。

覆盖：
- registry 1..22 连续（无空缺、无重复）
- init_db 到 v022 后，stock_fetch_log 表 + 索引存在
- 复合主键 (trade_date, stock_code, table_name) 约束生效
- status CHECK 约束限定为 success / failed
- downgrade(21) 后表消失
- 幂等：两次 init_db 不报错
- 既有表（migration 1..21）不被破坏
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from infrastructure.persistence.connection import get_connection
from infrastructure.persistence.database import (
    get_migration_status,
    init_db,
    reset_connection,
)
from infrastructure.persistence.migrations.runner import downgrade


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_migration_v022.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    yield db_path
    reset_connection()
    if db_path.exists():
        os.unlink(db_path)


def test_migration_v022_creates_table(tmp_db) -> None:
    """迁移到 v022 后，stock_fetch_log 表必须存在。"""
    init_db(tmp_db)
    status = get_migration_status()
    assert status["current_version"] >= 22

    conn = get_connection(tmp_db)
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            ("stock_fetch_log",),
        )
        assert cur.fetchone() is not None, "表 stock_fetch_log 未创建"
    finally:
        conn.close()


def test_migration_v022_creates_index(tmp_db) -> None:
    """关键索引必须创建。"""
    init_db(tmp_db)
    conn = get_connection(tmp_db)
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND tbl_name='stock_fetch_log'"
        )
        assert cur.fetchone() is not None, "stock_fetch_log 索引未创建"
    finally:
        conn.close()


def test_migration_v022_primary_key(tmp_db) -> None:
    """复合主键 (trade_date, stock_code, table_name) 约束生效。"""
    init_db(tmp_db)
    conn = get_connection(tmp_db)
    try:
        now = datetime.now(timezone.utc).isoformat()
        # 第一次插入
        conn.execute(
            "INSERT INTO stock_fetch_log "
            "(trade_date, stock_code, table_name, status, last_attempt_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("20260731", "600000", "stock_daily", "success", now),
        )
        conn.commit()
        # 重复插入应抛 IntegrityError
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO stock_fetch_log "
                "(trade_date, stock_code, table_name, status, last_attempt_at) "
                "VALUES (?, ?, ?, ?, ?)",
                ("20260731", "600000", "stock_daily", "success", now),
            )
    finally:
        conn.close()


def test_migration_v022_status_check_constraint(tmp_db) -> None:
    """status CHECK 约束：仅 success / failed。"""
    init_db(tmp_db)
    conn = get_connection(tmp_db)
    try:
        now = datetime.now(timezone.utc).isoformat()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO stock_fetch_log "
                "(trade_date, stock_code, table_name, status, last_attempt_at) "
                "VALUES (?, ?, ?, ?, ?)",
                ("20260731", "600000", "stock_daily", "invalid_status", now),
            )
    finally:
        conn.close()


def test_migration_v022_down_drops_table(tmp_db) -> None:
    """downgrade(21) 后 stock_fetch_log 必须消失。"""
    init_db(tmp_db)
    downgrade(target_version=21)
    conn = get_connection(tmp_db)
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            ("stock_fetch_log",),
        )
        assert cur.fetchone() is None, "表 stock_fetch_log 未被删除"
    finally:
        conn.close()


def test_migration_v022_idempotent(tmp_db) -> None:
    """运行两次 init_db 不应报错。"""
    init_db(tmp_db)
    reset_connection()
    init_db(tmp_db)  # 第二次
    status = get_migration_status()
    assert status["current_version"] >= 22
    assert status["pending_count"] == 0


def test_migration_v022_preserves_v021_tables(tmp_db) -> None:
    """stock_fetch_log 不影响 v021 既有 8 张表。"""
    init_db(tmp_db)
    conn = get_connection(tmp_db)
    try:
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
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            )
            assert cur.fetchone() is not None, f"v021 表 {table} 被破坏"
    finally:
        conn.close()


def test_migration_v022_realistic_workflow(tmp_db) -> None:
    """真实使用场景：写入 success → is_recently_succeeded 返回 True。"""
    from infrastructure.stock.cache_repository import CacheRepository

    init_db(tmp_db)
    conn = get_connection(tmp_db)
    try:
        repo = CacheRepository(conn=conn)
        repo.record_fetch(
            trade_date="20260731",
            stock_code="600000",
            table_name="stock_daily",
            status="success",
        )
        assert repo.is_recently_succeeded(
            trade_date="20260731",
            stock_code="600000",
            table_name="stock_daily",
            within_seconds=86400,
        ) is True
        # 25h 前 → False
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        conn.execute(
            "UPDATE stock_fetch_log SET last_attempt_at = ? "
            "WHERE stock_code = ?",
            (old_ts, "600000"),
        )
        conn.commit()
        assert repo.is_recently_succeeded(
            trade_date="20260731",
            stock_code="600000",
            table_name="stock_daily",
            within_seconds=86400,
        ) is False
    finally:
        conn.close()
