"""迁移执行器。

负责 ``schema_migrations`` 表维护、升级、降级与状态查询。
从 ``database.py`` 拆分（P1）；逻辑与原实现一致，仅将 dict 访问改为
``Migration`` 属性访问。
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any

from infrastructure.persistence.connection import get_connection
from infrastructure.persistence.migrations.registry import MIGRATIONS
from infrastructure.persistence.migrations.types import Migration

logger = logging.getLogger(__name__)


_MIGRATIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at  TEXT NOT NULL
)
"""


def _ensure_migrations_table(conn: Any) -> None:
    """Create the schema_migrations tracking table if it does not exist."""
    conn.execute(_MIGRATIONS_TABLE_SQL)
    conn.commit()


def _get_applied_versions(conn: Any) -> set[int]:
    """Return the set of migration versions already applied."""
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {row["version"] for row in rows}


def _run_migrations(conn: Any) -> None:
    """Run all pending upgrade migrations and record them in schema_migrations."""
    _ensure_migrations_table(conn)
    applied = _get_applied_versions(conn)
    for migration in MIGRATIONS:
        version = migration.version
        if version in applied:
            continue
        try:
            migration.upgrade(conn)
            applied_at = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO schema_migrations (version, description, applied_at) VALUES (?, ?, ?)",
                (version, migration.description, applied_at),
            )
            conn.commit()
            logger.info("Migration %d (%s) applied successfully", version, migration.description)
        except Exception:
            logger.exception("Migration %d (%s) failed", version, migration.description)
            raise


def run_upgrade(conn: sqlite3.Connection | None = None) -> None:
    """Run pending upgrade migrations. Can be called independently."""
    if conn is None:
        conn = get_connection()
    _run_migrations(conn)


def downgrade(target_version: int, conn: sqlite3.Connection | None = None) -> None:
    """Roll back migrations down to (but not including) *target_version*.

    For SQLite, column drops are not supported before version 3.35 so those
    downgrade steps are recorded but the actual column removal is skipped.
    Table-level downgrades (DROP TABLE) are fully supported.
    """
    if conn is None:
        conn = get_connection()
    _ensure_migrations_table(conn)
    applied = _get_applied_versions(conn)

    # Iterate migrations in reverse order
    for migration in reversed(MIGRATIONS):
        version = migration.version
        if version <= target_version:
            break
        if version not in applied:
            continue
        try:
            migration.downgrade(conn)
            conn.execute("DELETE FROM schema_migrations WHERE version = ?", (version,))
            conn.commit()
            logger.info("Migration %d (%s) downgraded successfully", version, migration.description)
        except Exception:
            logger.exception("Migration %d (%s) downgrade failed", version, migration.description)
            raise


def get_migration_status(conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """Return current schema version and list of applied migrations."""
    if conn is None:
        conn = get_connection()
    _ensure_migrations_table(conn)
    rows = conn.execute("SELECT version, description, applied_at FROM schema_migrations ORDER BY version").fetchall()
    applied = [
        {"version": row["version"], "description": row["description"], "applied_at": row["applied_at"]} for row in rows
    ]
    current_version = max((row["version"] for row in rows), default=0)
    applied_versions = {row["version"] for row in rows}
    pending = [m for m in MIGRATIONS if m.version not in applied_versions]
    return {
        "current_version": current_version,
        "applied": applied,
        "pending_count": len(pending),
        "pending": [{"version": m.version, "description": m.description} for m in pending],
    }
