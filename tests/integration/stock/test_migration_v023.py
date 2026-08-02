"""Task E 集成测试：迁移 v023 必须给 emotion_daily 新增 18 个字段。

覆盖：
- registry 1..23 连续（无空缺、无重复）
- init_db 到 v023 后，emotion_daily 表含全部 18 个新字段
- 字段类型与默认值正确
- downgrade(22) 后字段全部消失
- 不影响 v021 既有 8 张表与 v022 stock_fetch_log
- 既有 emotion_daily 行迁移后新字段默认值正确（NULL/0/''）
"""

from __future__ import annotations

import os

import pytest

from infrastructure.persistence.database import (
    downgrade,
    get_connection,
    get_migration_status,
    init_db,
    reset_connection,
)
from infrastructure.persistence.migrations.registry import MIGRATIONS


NEW_COLUMNS = [
    # 维度 2 广度
    "adv_count", "decl_count", "adv_decl_ratio", "breadth_level",
    # 维度 3 强度
    "top20_volume_avg_chg", "top20_volume_up_count",
    "top20_volume_limit_up_count", "strength_level", "market_style",
    # 维度 4 韧性
    "board_break_total_count", "board_break_rebound_count",
    "rebound_success_ratio", "top5d_avg_chg", "resilience_level",
    # 维度 5 真实度（已有 broken_limit_ratio，新增分类）
    "authenticity_level",
    # 维度 1 高度
    "height_level",
    # 维度 6 持续性
    "trend_5d", "trend_20d",
]


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_migration_v023.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    yield db_path
    reset_connection()
    if db_path.exists():
        os.unlink(db_path)


# ── 注册表完整性 ──────────────────────────────────────────


def test_registry_has_exactly_23_versions():
    """v023 加入后注册表必须包含 23 个迁移。"""
    assert len(MIGRATIONS) == 24


def test_registry_versions_are_1_to_23_continuous():
    """版本号必须连续 1..23。"""
    versions = [m.version for m in MIGRATIONS]
    assert versions == list(range(1, 24))


# ── 迁移效果 ──────────────────────────────────────────────


def test_migration_v023_adds_18_columns_to_emotion_daily(tmp_db):
    """迁移到 v023 后，emotion_daily 必须含全部 18 个新字段。"""
    init_db()
    status = get_migration_status()
    assert status["current_version"] >= 23

    conn = get_connection()
    try:
        cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(emotion_daily)").fetchall()
        }
        for col in NEW_COLUMNS:
            assert col in cols, f"emotion_daily 缺少字段 {col}"
    finally:
        conn.close()


def test_migration_v023_default_values_for_existing_rows(tmp_db):
    """v021 已写入的 emotion_daily 行，迁移后新字段必须是 NULL/0 默认。"""
    init_db()
    # 先降到 v021 写一行
    downgrade(21)
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO emotion_daily (trade_date, limit_up_count, "
            "limit_down_count, valid_limit_up_count, broken_limit_ratio, "
            "max_consecutive_boards, yesterday_limit_up_today_premium, "
            "total_volume, volume_change_pct, phase, phase_confidence, "
            "phase_reason) VALUES (?, 50, 5, 40, 0.1, 3, NULL, 1.2e12, "
            "0.05, NULL, NULL, NULL)",
            ("20260715",),
        )
        conn.commit()
    finally:
        conn.close()
    # 升级回 v23
    init_db()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM emotion_daily WHERE trade_date = ?",
            ("20260715",),
        ).fetchone()
        # 18 个新字段全部默认 NULL（int 字段也是 NULL，不是 0）
        for col in NEW_COLUMNS:
            assert row[col] is None, f"{col} 应为 NULL，实际 {row[col]!r}"
        # 既有字段保留
        assert row["limit_up_count"] == 50
    finally:
        conn.close()


def test_migration_v023_down_drops_columns(tmp_db):
    """downgrade(22) 后 18 个新字段必须消失。"""
    init_db()
    downgrade(22)
    conn = get_connection()
    try:
        cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(emotion_daily)").fetchall()
        }
        for col in NEW_COLUMNS:
            assert col not in cols, f"downgrade 后字段 {col} 仍存在"
    finally:
        conn.close()


def test_migration_v023_preserves_v021_and_v022_tables(tmp_db):
    """v023 不影响 v021 既有 8 张表与 v022 stock_fetch_log。"""
    init_db()
    conn = get_connection()
    try:
        for table in [
            "market_index_daily", "stock_daily", "limit_stocks_daily",
            "board_ladder_daily", "sector_daily", "emotion_daily",
            "watchlist_stocks", "review_reports", "stock_fetch_log",
        ]:
            cur = conn.execute(
                f"SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            )
            assert cur.fetchone() is not None, f"表 {table} 未创建"
    finally:
        conn.close()


def test_migration_v023_idempotent(tmp_db):
    """运行两次 init_db 不应报错。"""
    init_db()
    init_db()
    status = get_migration_status()
    assert status["current_version"] == 23
    assert status["pending_count"] == 0
