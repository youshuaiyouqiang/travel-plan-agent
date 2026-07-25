"""迁移版本 1–5。

从 ``database.py`` 拆分（P1）；SQL 文本与逻辑完全保留，不得修改。
"""

from __future__ import annotations

import logging
from typing import Any

from infrastructure.persistence.migrations.types import Migration

logger = logging.getLogger(__name__)


def _upgrade_1(conn: Any) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(long_term_memories)").fetchall()}
    if "experience_tag" not in existing:
        conn.execute("ALTER TABLE long_term_memories ADD COLUMN experience_tag TEXT NOT NULL DEFAULT ''")
        conn.commit()
        logger.info("Migration 1: added experience_tag to long_term_memories")


def _downgrade_1(conn: Any) -> None:
    logger.warning(
        "Migration 1 downgrade: SQLite cannot DROP COLUMN before 3.35; skipping column removal for experience_tag"
    )


def _upgrade_2(conn: Any) -> None:
    act_cols = {row[1] for row in conn.execute("PRAGMA table_info(itinerary_activities)").fetchall()}
    if "actual_cost" not in act_cols:
        conn.execute("ALTER TABLE itinerary_activities ADD COLUMN actual_cost REAL NOT NULL DEFAULT 0")
        conn.commit()
        logger.info("Migration 2: added actual_cost to itinerary_activities")


def _downgrade_2(conn: Any) -> None:
    logger.warning(
        "Migration 2 downgrade: SQLite cannot DROP COLUMN before 3.35; skipping column removal for actual_cost"
    )


def _upgrade_3(conn: Any) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS custom_agents (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            icon TEXT DEFAULT '🤖',
            system_prompt TEXT NOT NULL,
            skills TEXT DEFAULT '[]',
            welcome_message TEXT,
            temperature REAL DEFAULT 0.7,
            is_public INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_custom_agents_user ON custom_agents(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_custom_agents_public ON custom_agents(is_public)")
    conn.commit()
    logger.info("Migration 3: ensured custom_agents table exists")


def _downgrade_3(conn: Any) -> None:
    conn.execute("DROP TABLE IF EXISTS custom_agents")
    conn.commit()
    logger.info("Migration 3 downgrade: dropped custom_agents table")


def _upgrade_4(conn: Any) -> None:
    ca_cols = {row[1] for row in conn.execute("PRAGMA table_info(custom_agents)").fetchall()}
    if "mcp_servers" not in ca_cols:
        conn.execute("ALTER TABLE custom_agents ADD COLUMN mcp_servers TEXT DEFAULT '[]'")
        conn.commit()
        logger.info("Migration 4: added mcp_servers to custom_agents")
    if "status" not in ca_cols:
        conn.execute("ALTER TABLE custom_agents ADD COLUMN status TEXT DEFAULT 'published'")
        conn.commit()
        logger.info("Migration 4: added status to custom_agents")


def _downgrade_4(conn: Any) -> None:
    logger.warning(
        "Migration 4 downgrade: SQLite cannot DROP COLUMN before 3.35; skipping column removal for mcp_servers / status"
    )


def _upgrade_5(conn: Any) -> None:
    s_cols = {row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
    if "delegation_agent_id" not in s_cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN delegation_agent_id TEXT DEFAULT NULL")
        conn.commit()
        logger.info("Migration 5: added delegation_agent_id to sessions")
    if "delegation_started_at" not in s_cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN delegation_started_at REAL DEFAULT NULL")
        conn.commit()
        logger.info("Migration 5: added delegation_started_at to sessions")
    if "delegation_last_interaction" not in s_cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN delegation_last_interaction REAL DEFAULT NULL")
        conn.commit()
        logger.info("Migration 5: added delegation_last_interaction to sessions")
    if "disclosed_tools" not in s_cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN disclosed_tools TEXT DEFAULT '[]'")
        conn.commit()
        logger.info("Migration 5: added disclosed_tools to sessions")


def _downgrade_5(conn: Any) -> None:
    logger.warning(
        "Migration 5 downgrade: SQLite cannot DROP COLUMN before 3.35; skipping column removal for delegation / disclosed columns"
    )


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=1,
        description="Add experience_tag to long_term_memories",
        upgrade=_upgrade_1,
        downgrade=_downgrade_1,
    ),
    Migration(
        version=2,
        description="Add actual_cost to itinerary_activities",
        upgrade=_upgrade_2,
        downgrade=_downgrade_2,
    ),
    Migration(
        version=3,
        description="Create custom_agents table",
        upgrade=_upgrade_3,
        downgrade=_downgrade_3,
    ),
    Migration(
        version=4,
        description="Add mcp_servers and status to custom_agents",
        upgrade=_upgrade_4,
        downgrade=_downgrade_4,
    ),
    Migration(
        version=5,
        description="Add delegation context to sessions",
        upgrade=_upgrade_5,
        downgrade=_downgrade_5,
    ),
)
