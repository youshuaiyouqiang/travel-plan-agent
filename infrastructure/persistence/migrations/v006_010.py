"""迁移版本 6–10。

从 ``database.py`` 拆分（P1）；SQL 文本与逻辑完全保留，不得修改。
"""

from __future__ import annotations

import logging
from typing import Any

from infrastructure.persistence.migrations.types import Migration

logger = logging.getLogger(__name__)


def _upgrade_6(conn: Any) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS quality_issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            rating TEXT NOT NULL DEFAULT 'bad',
            issue_type TEXT NOT NULL DEFAULT 'other',
            comment TEXT DEFAULT '',
            agent_id TEXT DEFAULT '',
            message_snippet TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_quality_issues_user ON quality_issues(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_quality_issues_rating ON quality_issues(rating)")
    conn.commit()
    logger.info("Migration 6: ensured quality_issues table exists")


def _downgrade_6(conn: Any) -> None:
    conn.execute("DROP TABLE IF EXISTS quality_issues")
    conn.commit()
    logger.info("Migration 6 downgrade: dropped quality_issues table")


def _upgrade_7(conn: Any) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS news_favorites (
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
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_news_fav_user ON news_favorites(user_id)")
    nf_cols = {row[1] for row in conn.execute("PRAGMA table_info(news_favorites)").fetchall()}
    if "content" not in nf_cols:
        conn.execute("ALTER TABLE news_favorites ADD COLUMN content TEXT NOT NULL DEFAULT ''")
        conn.commit()
        logger.info("Migration 7: added content to news_favorites")
    conn.commit()
    logger.info("Migration 7: ensured news_favorites table exists")


def _downgrade_7(conn: Any) -> None:
    conn.execute("DROP TABLE IF EXISTS news_favorites")
    conn.commit()
    logger.info("Migration 7 downgrade: dropped news_favorites table")


def _upgrade_8(conn: Any) -> None:
    s_cols = {row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
    if "user_id" not in s_cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN user_id TEXT NOT NULL DEFAULT ''")
        conn.commit()
        rows = conn.execute("SELECT DISTINCT session_id, user_id FROM tasks WHERE user_id != ''").fetchall()
        for row in rows:
            conn.execute(
                "UPDATE sessions SET user_id = ? WHERE session_id = ?",
                (row["user_id"], row["session_id"]),
            )
        conn.commit()
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)")
        conn.commit()
        logger.info("Migration 8: added user_id to sessions, backfilled %d rows", len(rows))


def _downgrade_8(conn: Any) -> None:
    logger.warning(
        "Migration 8 downgrade: SQLite cannot DROP COLUMN before 3.35; skipping column removal for user_id (data migration, cannot reverse)"
    )


def _upgrade_9(conn: Any) -> None:
    it_cols = {row[1] for row in conn.execute("PRAGMA table_info(itineraries)").fetchall()}
    if "plans_json" not in it_cols:
        conn.execute("ALTER TABLE itineraries ADD COLUMN plans_json TEXT")
        conn.commit()
        logger.info("Migration 9: added plans_json to itineraries")
    if "confirmed_plan" not in it_cols:
        conn.execute("ALTER TABLE itineraries ADD COLUMN confirmed_plan VARCHAR(32) DEFAULT NULL")
        conn.commit()
        logger.info("Migration 9: added confirmed_plan to itineraries")
    if "confirmed_at" not in it_cols:
        conn.execute("ALTER TABLE itineraries ADD COLUMN confirmed_at VARCHAR(32) DEFAULT NULL")
        conn.commit()
        logger.info("Migration 9: added confirmed_at to itineraries")
    if "recommended_plan" not in it_cols:
        conn.execute("ALTER TABLE itineraries ADD COLUMN recommended_plan VARCHAR(32) DEFAULT NULL")
        conn.commit()
        logger.info("Migration 9: added recommended_plan to itineraries")


def _downgrade_9(conn: Any) -> None:
    logger.warning(
        "Migration 9 downgrade: SQLite cannot DROP COLUMN before 3.35; skipping column removal for multi-plan columns"
    )


def _upgrade_10(conn: Any) -> None:
    s_cols = {row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
    if "confirmed_plan" not in s_cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN confirmed_plan VARCHAR(32) DEFAULT NULL")
        conn.commit()
        logger.info("Migration 10: added confirmed_plan to sessions")
    if "confirmed_at" not in s_cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN confirmed_at VARCHAR(32) DEFAULT NULL")
        conn.commit()
        logger.info("Migration 10: added confirmed_at to sessions")


def _downgrade_10(conn: Any) -> None:
    logger.warning(
        "Migration 10 downgrade: SQLite cannot DROP COLUMN before 3.35; skipping column removal for confirmed_plan / confirmed_at"
    )


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=6,
        description="Create quality_issues table",
        upgrade=_upgrade_6,
        downgrade=_downgrade_6,
    ),
    Migration(
        version=7,
        description="Create news_favorites table + content column",
        upgrade=_upgrade_7,
        downgrade=_downgrade_7,
    ),
    Migration(
        version=8,
        description="Add user_id to sessions + backfill",
        upgrade=_upgrade_8,
        downgrade=_downgrade_8,
    ),
    Migration(
        version=9,
        description="Add multi-plan columns to itineraries",
        upgrade=_upgrade_9,
        downgrade=_downgrade_9,
    ),
    Migration(
        version=10,
        description="Add confirmed_plan/confirmed_at to sessions",
        upgrade=_upgrade_10,
        downgrade=_downgrade_10,
    ),
)
