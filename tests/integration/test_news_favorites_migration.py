"""Task 1 — news_favorites 表去全文迁移的集成测试。

覆盖范围：
- ``init_db`` 应用所有迁移后，``news_favorites`` 表不再含 ``content`` 列
- 迁移 14 单独执行时，从旧 schema（含 content）升级到新 schema（无 content）
- 已有收藏行被保留（content 字段被丢弃），仅保留允许的元数据
- ``UNIQUE(user_id, title)`` 约束被保留

业务红线：
- 不抓取、保存或注入新闻全文；收藏仅保存标题、来源、URL、摘要、标签与时间。
- 迁移必须重建表结构以彻底移除 ``content`` 列，不可仅置空。
"""

from __future__ import annotations

import sqlite3

import pytest

from infrastructure.persistence.database import (
    _upgrade_7,
    get_connection,
    init_db,
    reset_connection,
)


def _columns(conn, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


_REQUIRED_COLUMNS = {
    "id",
    "user_id",
    "title",
    "summary",
    "url",
    "source",
    "tag",
    "created_at",
}


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    db_path = tmp_path / "test_news_fav_migration.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()


# ---------------------------------------------------------------------------
# init_db 后表已迁移到位
# ---------------------------------------------------------------------------


def test_favorite_migration_removes_full_content(db_path):
    """``init_db`` 应用所有迁移后，``content`` 列已不存在。"""
    conn = get_connection()
    cols = _columns(conn, "news_favorites")
    conn.close()
    assert "content" not in cols
    assert _REQUIRED_COLUMNS.issubset(cols)


def test_favorite_migration_preserves_required_metadata_columns(db_path):
    """迁移后允许的元数据列仍然存在。"""
    conn = get_connection()
    cols = _columns(conn, "news_favorites")
    conn.close()
    for required in _REQUIRED_COLUMNS:
        assert required in cols


def test_favorite_can_be_inserted_without_content_field(db_path):
    """迁移后插入收藏不再需要（也不接受）content 字段。"""
    conn = get_connection()
    conn.execute(
        "INSERT INTO news_favorites (user_id, title, summary, url, source, tag, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("u1", "T1", "S1", "https://e/1", "src", "tag1", "2026-01-01"),
    )
    conn.commit()
    row = conn.execute(
        "SELECT user_id, title, summary FROM news_favorites WHERE user_id = ?",
        ("u1",),
    ).fetchone()
    conn.close()
    assert row is not None
    assert row["title"] == "T1"
    assert row["summary"] == "S1"


# ---------------------------------------------------------------------------
# 迁移 14 单独执行 — 模拟从旧 schema 升级
# ---------------------------------------------------------------------------


def test_migration_14_removes_content_column_and_preserves_rows(tmp_path, monkeypatch):
    """从空白 schema 起步，仅运行迁移 7（含 content），再运行迁移 14，content 列被移除。"""
    from infrastructure.persistence.database import _upgrade_14

    db_path = tmp_path / "raw_migration.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # 仅运行迁移 7（创建带 content 的 news_favorites）
    _upgrade_7(conn)
    assert "content" in _columns(conn, "news_favorites")

    # 插入一行带 content 的旧收藏
    conn.execute(
        "INSERT INTO news_favorites (user_id, title, summary, content, url, source, tag, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("u1", "T1", "S1", "FULL BODY MUST BE DROPPED", "https://e/1", "src", "tag1", "2026-01-01"),
    )
    conn.commit()

    # 运行迁移 14（去 content）
    _upgrade_14(conn)

    cols = _columns(conn, "news_favorites")
    assert "content" not in cols
    assert _REQUIRED_COLUMNS.issubset(cols)

    # 旧行被保留（content 已丢弃）
    row = conn.execute(
        "SELECT user_id, title, summary, url, source, tag, created_at "
        "FROM news_favorites WHERE user_id = ?",
        ("u1",),
    ).fetchone()
    assert row is not None
    assert row["title"] == "T1"
    assert row["summary"] == "S1"

    # UNIQUE(user_id, title) 仍然生效
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO news_favorites (user_id, title, summary, url, source, tag, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("u1", "T1", "dup", "https://e/2", "src", "tag2", "2026-01-02"),
        )

    conn.close()
    reset_connection()
