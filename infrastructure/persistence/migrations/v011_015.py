"""迁移版本 11–15。

从 ``database.py`` 拆分（P1）；SQL 文本与逻辑完全保留，不得修改。
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from infrastructure.persistence.migrations.types import Migration

logger = logging.getLogger(__name__)


def _upgrade_11(conn: Any) -> None:
    """Task 1: 为 sessions 表增加 mode/locked_agent_id/news_id 三列。

    - ``mode``：会话模式，默认 ``yunhe_default``；旧数据回填为默认值。
    - ``locked_agent_id``：``agent_locked`` 或 ``news_analysis_locked`` 模式下的锚定 Agent。
    - ``news_id``：仅 ``news_analysis_locked`` 模式下非空，新闻研判锚点。
    """
    s_cols = {row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
    if "mode" not in s_cols:
        conn.execute(
            "ALTER TABLE sessions ADD COLUMN mode TEXT NOT NULL DEFAULT 'yunhe_default'"
        )
        conn.commit()
        logger.info("Migration 11: added mode to sessions")
    if "locked_agent_id" not in s_cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN locked_agent_id TEXT DEFAULT NULL")
        conn.commit()
        logger.info("Migration 11: added locked_agent_id to sessions")
    if "news_id" not in s_cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN news_id TEXT DEFAULT NULL")
        conn.commit()
        logger.info("Migration 11: added news_id to sessions")


def _downgrade_11(conn: Any) -> None:
    logger.warning(
        "Migration 11 downgrade: SQLite cannot DROP COLUMN before 3.35; "
        "skipping column removal for mode/locked_agent_id/news_id"
    )


def _upgrade_12(conn: Any) -> None:
    """Task 4: 令牌安全 — 用 ``auth_token_hashes`` 表替代旧 ``auth_tokens``。

    - 新表只存 ``sha256(token)``，原 token 明文不入库。
    - 旧表 ``auth_tokens`` 数据迁移到新表（对每行 token 取 sha256 后入库）。
    - 旧表 ``auth_tokens`` 在数据迁移完成后删除，避免误存明文。
    - 旧表不存在的环境（全新部署）直接建新表。
    """
    import hashlib as _hashlib

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_token_hashes (
            token_hash TEXT PRIMARY KEY,
            user_id    TEXT NOT NULL,
            expires_at REAL NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_auth_token_hashes_user ON auth_token_hashes(user_id)"
    )

    # 旧表存在时迁移历史数据
    legacy_rows: list[Any] = []
    try:
        legacy_rows = conn.execute(
            "SELECT token, user_id, expires_at FROM auth_tokens"
        ).fetchall()
    except sqlite3.OperationalError:
        # 旧表不存在 — 全新部署，无需迁移
        legacy_rows = []

    migrated = 0
    for row in legacy_rows:
        token_value = row["token"] if isinstance(row, sqlite3.Row) else row[0]
        user_id = row["user_id"] if isinstance(row, sqlite3.Row) else row[1]
        expires_at = row["expires_at"] if isinstance(row, sqlite3.Row) else row[2]
        token_hash = _hashlib.sha256(token_value.encode("utf-8")).hexdigest()
        conn.execute(
            "INSERT OR IGNORE INTO auth_token_hashes (token_hash, user_id, expires_at) "
            "VALUES (?, ?, ?)",
            (token_hash, user_id, expires_at),
        )
        migrated += 1

    # 旧表迁移完成后删除，避免明文残留
    conn.execute("DROP TABLE IF EXISTS auth_tokens")
    conn.commit()
    logger.info(
        "Migration 12: ensured auth_token_hashes table exists, migrated %d legacy tokens, dropped auth_tokens",
        migrated,
    )


def _downgrade_12(conn: Any) -> None:
    """回滚迁移 12 — 重建 ``auth_tokens`` 表，但无法从哈希还原原 token。

    降级是单向不可逆的：哈希无法还原明文。重建空表仅保证 schema 兼容旧版本。
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_tokens (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            expires_at REAL NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_tokens_user ON auth_tokens(user_id)")
    conn.execute("DROP TABLE IF EXISTS auth_token_hashes")
    conn.commit()
    logger.warning(
        "Migration 12 downgrade: dropped auth_token_hashes; auth_tokens rebuilt empty "
        "(hashed tokens cannot be reversed to plaintext)"
    )


def _upgrade_13(conn: Any) -> None:
    """Task 1（新闻计划）: 创建新闻来源治理表。

    - ``news_sources``: 受治理的来源元数据 + AI 评分 + 状态。
    - ``news_source_audits``: 管理员审核审计链。

    两表均不保存新闻全文；仅保存来源元数据与审核决策。
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS news_sources (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            domain      TEXT NOT NULL UNIQUE,
            tier        TEXT NOT NULL,
            status      TEXT NOT NULL,
            ai_score    REAL,
            ai_reason   TEXT NOT NULL DEFAULT '',
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_news_sources_status ON news_sources(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_news_sources_domain ON news_sources(domain)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS news_source_audits (
            id              TEXT PRIMARY KEY,
            source_id       TEXT NOT NULL,
            admin_id        TEXT NOT NULL,
            previous_status TEXT NOT NULL,
            decision        TEXT NOT NULL,
            reason          TEXT NOT NULL,
            created_at      TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_news_source_audits_source ON news_source_audits(source_id)"
    )
    conn.commit()
    logger.info("Migration 13: ensured news_sources + news_source_audits tables exist")


def _downgrade_13(conn: Any) -> None:
    conn.execute("DROP TABLE IF EXISTS news_source_audits")
    conn.execute("DROP TABLE IF EXISTS news_sources")
    conn.commit()
    logger.info("Migration 13 downgrade: dropped news_sources + news_source_audits tables")


def _upgrade_14(conn: Any) -> None:
    """Task 1（新闻计划）: 重建 ``news_favorites`` 表，移除 ``content`` 列。

    业务红线：不保存新闻全文；收藏仅保存标题、来源、URL、摘要、标签与时间。

    SQLite 3.35 之前不支持 ``DROP COLUMN``，故采用重建表方式：
    1. 创建不含 ``content`` 列的新表 ``news_favorites_new``
    2. 从旧表拷贝允许的元数据（不拷贝 content）
    3. 删除旧表，重命名新表为 ``news_favorites``
    4. 重建索引

    全新部署（旧表不存在）时仅创建新表，不执行数据拷贝。
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS news_favorites_new (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     TEXT NOT NULL,
            title       TEXT NOT NULL,
            summary     TEXT NOT NULL DEFAULT '',
            url         TEXT NOT NULL DEFAULT '',
            source      TEXT NOT NULL DEFAULT '',
            tag         TEXT NOT NULL DEFAULT '',
            created_at  TEXT NOT NULL,
            UNIQUE(user_id, title)
        )
        """
    )

    # 检查旧表是否存在（通过是否有 id 列判断）
    old_cols = {
        row[1] for row in conn.execute("PRAGMA table_info(news_favorites)").fetchall()
    }
    if "id" in old_cols:
        # 旧表存在：拷贝允许的元数据（content 被丢弃）
        conn.execute(
            "INSERT OR IGNORE INTO news_favorites_new "
            "(id, user_id, title, summary, url, source, tag, created_at) "
            "SELECT id, user_id, title, summary, url, source, tag, created_at "
            "FROM news_favorites"
        )
        conn.execute("DROP TABLE news_favorites")
        logger.info("Migration 14: migrated existing news_favorites rows (content dropped)")
    else:
        # 全新部署：旧表不存在，清理可能残留的占位
        conn.execute("DROP TABLE IF EXISTS news_favorites")

    conn.execute("ALTER TABLE news_favorites_new RENAME TO news_favorites")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_news_fav_user ON news_favorites(user_id)")
    conn.commit()
    logger.info("Migration 14: rebuilt news_favorites without content column")


def _downgrade_14(conn: Any) -> None:
    """回滚迁移 14 — 重建带 ``content`` 列的 ``news_favorites`` 表。

    降级是单向不可逆的：已被丢弃的 content 无法恢复。重建空表仅保证 schema 兼容旧版本。
    """
    conn.execute("DROP TABLE IF EXISTS news_favorites")
    conn.execute(
        """
        CREATE TABLE news_favorites (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     TEXT NOT NULL,
            title       TEXT NOT NULL,
            summary     TEXT NOT NULL DEFAULT '',
            content     TEXT NOT NULL DEFAULT '',
            url         TEXT NOT NULL DEFAULT '',
            source      TEXT NOT NULL DEFAULT '',
            tag         TEXT NOT NULL DEFAULT '',
            created_at  TEXT NOT NULL,
            UNIQUE(user_id, title)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_news_fav_user ON news_favorites(user_id)")
    conn.commit()
    logger.warning(
        "Migration 14 downgrade: rebuilt news_favorites with content column (empty; "
        "previously dropped content cannot be restored)"
    )


def _upgrade_15(conn: Any) -> None:
    """Task 1（旅行计划）: 创建旅行草稿与存档表。

    - ``travel_drafts``: 可编辑的当前草稿；``is_read_only`` 在确认后置 1。
      ``manual_edit_fields`` 以 JSON 数组保存用户手工编辑过的字段路径，
      供后续任务保护手工编辑不被 Agent 覆盖。
      ``source_archive_id`` 仅在该草稿由存档续编而来时非空。
    - ``travel_archives``: 不可变的确认存档快照；只保存行程 JSON 与来源草稿 id。

    两表均不保存原始外部数据；行程外部信息仅在用户点击"更新信息"时查询。
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS travel_drafts (
            id                  TEXT PRIMARY KEY,
            user_id             TEXT NOT NULL,
            session_id          TEXT NOT NULL,
            plan_json           TEXT NOT NULL DEFAULT '{}',
            manual_edit_fields  TEXT NOT NULL DEFAULT '[]',
            is_read_only        INTEGER NOT NULL DEFAULT 0,
            source_archive_id   TEXT,
            created_at          TEXT NOT NULL,
            updated_at          TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_travel_drafts_user_session "
        "ON travel_drafts(user_id, session_id)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS travel_archives (
            id              TEXT PRIMARY KEY,
            user_id         TEXT NOT NULL,
            source_draft_id TEXT NOT NULL,
            plan_json       TEXT NOT NULL,
            confirmed_at    TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_travel_archives_user ON travel_archives(user_id)"
    )
    conn.commit()
    logger.info("Migration 15: ensured travel_drafts + travel_archives tables exist")


def _downgrade_15(conn: Any) -> None:
    conn.execute("DROP TABLE IF EXISTS travel_archives")
    conn.execute("DROP TABLE IF EXISTS travel_drafts")
    conn.commit()
    logger.info("Migration 15 downgrade: dropped travel_drafts + travel_archives tables")


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=11,
        description="Add mode/locked_agent_id/news_id to sessions",
        upgrade=_upgrade_11,
        downgrade=_downgrade_11,
    ),
    Migration(
        version=12,
        description="Replace auth_tokens with auth_token_hashes (sha256 only)",
        upgrade=_upgrade_12,
        downgrade=_downgrade_12,
    ),
    Migration(
        version=13,
        description="Create news_sources + news_source_audits tables",
        upgrade=_upgrade_13,
        downgrade=_downgrade_13,
    ),
    Migration(
        version=14,
        description="Rebuild news_favorites without content column",
        upgrade=_upgrade_14,
        downgrade=_downgrade_14,
    ),
    Migration(
        version=15,
        description="Create travel_drafts + travel_archives tables",
        upgrade=_upgrade_15,
        downgrade=_downgrade_15,
    ),
)
