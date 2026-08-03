"""P1 迁移注册表与执行器拆分的单元/集成测试。

覆盖：
- 注册版本恰为 1..25、不重复
- 空库升级到版本 25
- 已升级库重复初始化幂等
- 从版本 25 降级再升级保持现有迁移测试断言
- 每个迁移文件少于 800 行
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


# ── 注册表完整性 ──────────────────────────────────────────


def test_registry_has_exactly_25_versions():
    """注册表必须恰好包含 25 个迁移（v025 新增情绪周期 5 字段）。"""
    assert len(MIGRATIONS) == 25


def test_registry_versions_are_1_to_25_continuous():
    """版本号必须连续 1..25。"""
    versions = [m.version for m in MIGRATIONS]
    assert versions == list(range(1, 26))


def test_registry_versions_are_unique():
    """版本号不得重复。"""
    versions = [m.version for m in MIGRATIONS]
    assert len(versions) == len(set(versions))


def test_registry_is_immutable_tuple():
    """注册表必须是不可变 tuple。"""
    assert isinstance(MIGRATIONS, tuple)


def test_every_migration_has_upgrade_and_downgrade():
    """每个迁移必须有 upgrade 和 downgrade 可调用对象。"""
    for m in MIGRATIONS:
        assert callable(m.upgrade), f"migration {m.version} upgrade not callable"
        assert callable(m.downgrade), f"migration {m.version} downgrade not callable"
        assert isinstance(m.description, str) and m.description, f"migration {m.version} empty description"


# ── 迁移文件行数 ──────────────────────────────────────────


_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "infrastructure" / "persistence" / "migrations"


@pytest.mark.parametrize(
    "filename",
    ["v001_005.py", "v006_010.py", "v011_015.py", "v016_020.py"],
)
def test_migration_file_under_800_lines(filename: str):
    """每个迁移文件必须少于 800 行（P1 验收标准）。"""
    filepath = _MIGRATIONS_DIR / filename
    assert filepath.exists(), f"{filename} not found"
    line_count = sum(1 for _ in filepath.open(encoding="utf-8"))
    assert line_count < 800, f"{filename} has {line_count} lines, must be < 800"


# ── 空库升级与幂等 ────────────────────────────────────────


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """临时数据库 fixture；每个测试独立隔离。"""
    db_path = tmp_path / "test_p1_migrations.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    yield db_path
    reset_connection()
    if db_path.exists():
        os.unlink(db_path)


def test_empty_db_upgrades_to_version_25(tmp_db):
    """空库 init_db 后 current_version 必须为 25。"""
    init_db()
    status = get_migration_status()
    assert status["current_version"] == 25
    assert status["pending_count"] == 0


def test_repeated_init_db_is_idempotent(tmp_db):
    """已升级库重复 init_db 不报错，版本仍为 25。"""
    init_db()
    init_db()
    init_db()
    status = get_migration_status()
    assert status["current_version"] == 25
    assert status["pending_count"] == 0


def test_all_25_versions_recorded_in_schema_migrations(tmp_db):
    """schema_migrations 表必须记录全部 25 个版本。"""
    init_db()
    conn = get_connection()
    rows = conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
    versions = [row["version"] for row in rows]
    assert versions == list(range(1, 26))


# ── 降级与再升级 ──────────────────────────────────────────


def test_downgrade_from_25_to_15_then_upgrade_restores_25(tmp_db):
    """从版本 25 降级到 15，再升级应恢复到 25。"""
    init_db()
    assert get_migration_status()["current_version"] == 25

    # 降级到 15（保留 1..15，删除 16..25）
    downgrade(15)
    status_after_downgrade = get_migration_status()
    assert status_after_downgrade["current_version"] == 15
    assert status_after_downgrade["pending_count"] == 10

    # 再升级
    init_db()
    status_after_upgrade = get_migration_status()
    assert status_after_upgrade["current_version"] == 25
    assert status_after_upgrade["pending_count"] == 0


def test_downgrade_to_0_then_full_upgrade_restores_25(tmp_db):
    """从版本 25 全部降级到 0，再全量升级应恢复到 25。"""
    init_db()
    assert get_migration_status()["current_version"] == 25

    # 全部降级
    downgrade(0)
    status_after_downgrade = get_migration_status()
    assert status_after_downgrade["current_version"] == 0

    # 全量升级
    init_db()
    status_after_upgrade = get_migration_status()
    assert status_after_upgrade["current_version"] == 25


def test_migration_status_reports_pending_correctly(tmp_db):
    """get_migration_status 在部分升级时正确报告 pending。"""
    init_db()
    # 降级到 19（留下 1..19，pending 20..25 = 6 个）
    downgrade(19)
    status = get_migration_status()
    assert status["current_version"] == 19
    assert status["pending_count"] == 6
    pending_versions = [p["version"] for p in status["pending"]]
    assert pending_versions == [20, 21, 22, 23, 24, 25]
