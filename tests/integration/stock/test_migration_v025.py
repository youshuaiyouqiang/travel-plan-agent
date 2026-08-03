"""情绪周期折线图集成测试：迁移 v025 必须给 emotion_daily 新增 5 个字段。

覆盖（开发文档 §9.2）：
- v025 新增 5 字段：PRAGMA table_info(emotion_daily) 含 5 列及正确类型
- 既有行新字段默认 NULL：v024 写入的老行升级后 5 字段为 NULL
- upgrade→downgrade(24)→upgrade 幂等：降级后 5 列消失，再升级恢复
- 迁移文件行数 < 800：v021_025.py 仍满足 P1 行数约束
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from infrastructure.persistence.database import (
    downgrade,
    get_connection,
    get_migration_status,
    init_db,
    reset_connection,
)
from infrastructure.persistence.migrations.registry import MIGRATIONS


# v025 新增的 5 个情绪周期字段（开发文档 §6.2）
NEW_COLUMNS: list[tuple[str, str]] = [
    ("board_style_score", "REAL"),
    ("trend_style_score", "REAL"),
    ("rebound_style_score", "REAL"),
    ("emotion_score", "REAL"),
    ("emotion_phase", "TEXT"),
]


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """临时数据库 fixture；每个测试独立隔离。"""
    db_path = tmp_path / "test_migration_v025.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    yield db_path
    reset_connection()
    if db_path.exists():
        os.unlink(db_path)


# ── 注册表完整性 ──────────────────────────────────────────


def test_registry_has_exactly_25_versions():
    """v025 加入后注册表必须包含 25 个迁移。"""
    assert len(MIGRATIONS) == 25


def test_registry_versions_are_1_to_25_continuous():
    """版本号必须连续 1..25。"""
    versions = [m.version for m in MIGRATIONS]
    assert versions == list(range(1, 26))


# ── 迁移效果 ──────────────────────────────────────────────


def test_migration_v025_adds_5_columns_to_emotion_daily(tmp_db):
    """迁移到 v025 后，emotion_daily 必须含全部 5 个新字段及正确类型。"""
    init_db()
    status = get_migration_status()
    assert status["current_version"] == 25

    conn = get_connection()
    try:
        col_info = {
            row["name"]: row["type"]
            for row in conn.execute("PRAGMA table_info(emotion_daily)").fetchall()
        }
        for col, expected_type in NEW_COLUMNS:
            assert col in col_info, f"emotion_daily 缺少字段 {col}"
            actual_type = col_info[col].upper()
            assert actual_type == expected_type.upper(), (
                f"字段 {col} 类型应为 {expected_type}，实际 {col_info[col]}"
            )
    finally:
        conn.close()


def test_migration_v025_default_values_for_existing_rows(tmp_db):
    """v024 已写入的 emotion_daily 行，升级到 v025 后 5 个新字段必须为 NULL。"""
    init_db()
    # 降到 v024 写一行（确保不带 v025 新列）
    downgrade(24)
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO emotion_daily (trade_date, limit_up_count, "
            "limit_down_count, valid_limit_up_count, broken_limit_ratio, "
            "max_consecutive_boards, yesterday_limit_up_today_premium, "
            "total_volume, volume_change_pct, phase, phase_confidence, "
            "phase_reason, top_board_leaders) VALUES "
            "(?, 50, 5, 40, 0.1, 3, NULL, 1.2e12, 0.05, NULL, NULL, NULL, NULL)",
            ("20260715",),
        )
        conn.commit()
    finally:
        conn.close()
    # 升级回 v025
    init_db()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM emotion_daily WHERE trade_date = ?",
            ("20260715",),
        ).fetchone()
        # 5 个新字段全部默认 NULL
        for col, _ in NEW_COLUMNS:
            assert row[col] is None, f"{col} 应为 NULL，实际 {row[col]!r}"
        # 既有字段保留
        assert row["limit_up_count"] == 50
        assert row["top_board_leaders"] is None
    finally:
        conn.close()


def test_migration_v025_down_drops_columns(tmp_db):
    """downgrade(24) 后 5 个新字段必须消失；再 init_db 升级恢复。"""
    init_db()
    # 降级到 v024
    downgrade(24)
    conn = get_connection()
    try:
        cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(emotion_daily)").fetchall()
        }
        for col, _ in NEW_COLUMNS:
            assert col not in cols, f"downgrade(24) 后字段 {col} 仍存在"
    finally:
        conn.close()

    # 再升级回 v025（幂等）
    init_db()
    status = get_migration_status()
    assert status["current_version"] == 25
    conn = get_connection()
    try:
        cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(emotion_daily)").fetchall()
        }
        for col, _ in NEW_COLUMNS:
            assert col in cols, f"再升级后字段 {col} 未恢复"
    finally:
        conn.close()


def test_migration_v025_preserves_other_tables(tmp_db):
    """v025 不影响 v021 既有 8 张表与 v022 stock_fetch_log。"""
    init_db()
    conn = get_connection()
    try:
        for table in [
            "market_index_daily", "stock_daily", "limit_stocks_daily",
            "board_ladder_daily", "sector_daily", "emotion_daily",
            "watchlist_stocks", "review_reports", "stock_fetch_log",
        ]:
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            )
            assert cur.fetchone() is not None, f"表 {table} 未创建"
    finally:
        conn.close()


def test_migration_v025_idempotent(tmp_db):
    """运行两次 init_db 不应报错，版本仍为 25。"""
    init_db()
    init_db()
    status = get_migration_status()
    assert status["current_version"] == 25
    assert status["pending_count"] == 0


def test_migration_file_v021_025_under_800_lines():
    """v021_025.py 必须少于 800 行（P1 行数约束）。"""
    filepath = (
        Path(__file__).resolve().parents[3]
        / "infrastructure" / "persistence" / "migrations" / "v021_025.py"
    )
    assert filepath.exists(), "v021_025.py not found"
    line_count = sum(1 for _ in filepath.open(encoding="utf-8"))
    assert line_count < 800, f"v021_025.py has {line_count} lines, must be < 800"
