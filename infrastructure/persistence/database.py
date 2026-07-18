from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import local
from typing import Any

from config import settings

logger = logging.getLogger(__name__)

_local = local()


def reset_connection() -> None:
    conn = getattr(_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
    _local.conn = None
    _local.db_path_str = None


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    db_path = Path(db_path) if db_path else settings.database_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path_str = str(db_path.resolve())
    conn = getattr(_local, "conn", None)
    current_path = getattr(_local, "db_path_str", None)
    if conn is not None and current_path == db_path_str:
        try:
            conn.execute("SELECT 1")
            return conn
        except sqlite3.Error:
            pass
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
    conn = sqlite3.connect(db_path_str, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    _local.conn = conn
    _local.db_path_str = db_path_str
    return conn


# ---------------------------------------------------------------------------
# Schema migrations tracking
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Migration upgrade / downgrade functions
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Migration registry
# ---------------------------------------------------------------------------

_MIGRATIONS: list[dict[str, Any]] = [
    {
        "version": 1,
        "description": "Add experience_tag to long_term_memories",
        "upgrade": _upgrade_1,
        "downgrade": _downgrade_1,
    },
    {
        "version": 2,
        "description": "Add actual_cost to itinerary_activities",
        "upgrade": _upgrade_2,
        "downgrade": _downgrade_2,
    },
    {
        "version": 3,
        "description": "Create custom_agents table",
        "upgrade": _upgrade_3,
        "downgrade": _downgrade_3,
    },
    {
        "version": 4,
        "description": "Add mcp_servers and status to custom_agents",
        "upgrade": _upgrade_4,
        "downgrade": _downgrade_4,
    },
    {
        "version": 5,
        "description": "Add delegation context to sessions",
        "upgrade": _upgrade_5,
        "downgrade": _downgrade_5,
    },
    {
        "version": 6,
        "description": "Create quality_issues table",
        "upgrade": _upgrade_6,
        "downgrade": _downgrade_6,
    },
    {
        "version": 7,
        "description": "Create news_favorites table + content column",
        "upgrade": _upgrade_7,
        "downgrade": _downgrade_7,
    },
    {
        "version": 8,
        "description": "Add user_id to sessions + backfill",
        "upgrade": _upgrade_8,
        "downgrade": _downgrade_8,
    },
    {
        "version": 9,
        "description": "Add multi-plan columns to itineraries",
        "upgrade": _upgrade_9,
        "downgrade": _downgrade_9,
    },
    {
        "version": 10,
        "description": "Add confirmed_plan/confirmed_at to sessions",
        "upgrade": _upgrade_10,
        "downgrade": _downgrade_10,
    },
    {
        "version": 11,
        "description": "Add mode/locked_agent_id/news_id to sessions",
        "upgrade": _upgrade_11,
        "downgrade": _downgrade_11,
    },
    {
        "version": 12,
        "description": "Replace auth_tokens with auth_token_hashes (sha256 only)",
        "upgrade": _upgrade_12,
        "downgrade": _downgrade_12,
    },
    {
        "version": 13,
        "description": "Create news_sources + news_source_audits tables",
        "upgrade": _upgrade_13,
        "downgrade": _downgrade_13,
    },
    {
        "version": 14,
        "description": "Rebuild news_favorites without content column",
        "upgrade": _upgrade_14,
        "downgrade": _downgrade_14,
    },
]


def _run_migrations(conn: Any) -> None:
    """Run all pending upgrade migrations and record them in schema_migrations."""
    _ensure_migrations_table(conn)
    applied = _get_applied_versions(conn)
    for migration in _MIGRATIONS:
        version = migration["version"]
        if version in applied:
            continue
        try:
            migration["upgrade"](conn)
            applied_at = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO schema_migrations (version, description, applied_at) VALUES (?, ?, ?)",
                (version, migration["description"], applied_at),
            )
            conn.commit()
            logger.info("Migration %d (%s) applied successfully", version, migration["description"])
        except Exception:
            logger.exception("Migration %d (%s) failed", version, migration["description"])
            raise


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def init_db(db_path: str | Path | None = None) -> None:
    conn = get_connection(db_path)
    conn.executescript(_SCHEMA)
    conn.commit()
    _run_migrations(conn)
    logger.info("Database initialized: %s", db_path or settings.database_path)


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
    for migration in reversed(_MIGRATIONS):
        version = migration["version"]
        if version <= target_version:
            break
        if version not in applied:
            continue
        try:
            migration["downgrade"](conn)
            conn.execute("DELETE FROM schema_migrations WHERE version = ?", (version,))
            conn.commit()
            logger.info("Migration %d (%s) downgraded successfully", version, migration["description"])
        except Exception:
            logger.exception("Migration %d (%s) downgrade failed", version, migration["description"])
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
    pending = [m for m in _MIGRATIONS if m["version"] not in {row["version"] for row in rows}]
    return {
        "current_version": current_version,
        "applied": applied,
        "pending_count": len(pending),
        "pending": [{"version": m["version"], "description": m["description"]} for m in pending],
    }


_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id   TEXT PRIMARY KEY,
    username  TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL DEFAULT '',
    summary    TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS session_turns (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_turns_session ON session_turns(session_id);

CREATE TABLE IF NOT EXISTS tasks (
    session_id  TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'idle',
    goal        TEXT NOT NULL DEFAULT '',
    latest_user_message TEXT NOT NULL DEFAULT '',
    latest_reply TEXT NOT NULL DEFAULT '',
    pending_prompt TEXT NOT NULL DEFAULT '',
    trace_summary TEXT NOT NULL DEFAULT '',
    metadata    TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL DEFAULT '',
    updated_at  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS profiles (
    user_id           TEXT PRIMARY KEY,
    tags              TEXT NOT NULL DEFAULT '[]',
    interaction_count INTEGER NOT NULL DEFAULT 0,
    last_intent       TEXT NOT NULL DEFAULT '',
    preferred_categories TEXT NOT NULL DEFAULT '[]',
    emotion_history   TEXT NOT NULL DEFAULT '[]',
    custom_attributes TEXT NOT NULL DEFAULT '{}',
    created_at        TEXT NOT NULL DEFAULT '',
    updated_at        TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS conversations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT NOT NULL,
    user_id       TEXT NOT NULL,
    summary       TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations(session_id);

CREATE TABLE IF NOT EXISTS short_term_memories (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT NOT NULL,
    category        TEXT NOT NULL DEFAULT 'fact',
    content         TEXT NOT NULL,
    source_conv_id  INTEGER,
    experience_tag  TEXT NOT NULL DEFAULT '',
    extraction_count INTEGER NOT NULL DEFAULT 0,
    last_accessed_at TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_stm_user ON short_term_memories(user_id);
CREATE INDEX IF NOT EXISTS idx_stm_user_category ON short_term_memories(user_id, category);

CREATE TABLE IF NOT EXISTS long_term_memories (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT NOT NULL,
    category        TEXT NOT NULL DEFAULT 'fact',
    content         TEXT NOT NULL,
    source_ids      TEXT NOT NULL DEFAULT '[]',
    extraction_count INTEGER NOT NULL DEFAULT 0,
    last_accessed_at TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'active',
    created_at      TEXT NOT NULL DEFAULT '',
    updated_at      TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_ltm_user ON long_term_memories(user_id);
CREATE INDEX IF NOT EXISTS idx_ltm_user_status ON long_term_memories(user_id, status);

CREATE TABLE IF NOT EXISTS memory_extractions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    memory_type     TEXT NOT NULL,
    memory_id       INTEGER NOT NULL,
    relevance       REAL NOT NULL DEFAULT 0.0,
    created_at      TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_extractions_conv ON memory_extractions(conversation_id);
CREATE INDEX IF NOT EXISTS idx_extractions_memory ON memory_extractions(memory_type, memory_id);

CREATE TABLE IF NOT EXISTS itineraries (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    session_id   TEXT NOT NULL DEFAULT '',
    title        TEXT NOT NULL DEFAULT '',
    destination  TEXT NOT NULL DEFAULT '',
    start_date   TEXT NOT NULL DEFAULT '',
    end_date     TEXT NOT NULL DEFAULT '',
    budget       TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'planning',
    raw_content  TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL DEFAULT '',
    updated_at   TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_itineraries_user ON itineraries(user_id);
CREATE INDEX IF NOT EXISTS idx_itineraries_session ON itineraries(session_id);

CREATE TABLE IF NOT EXISTS itinerary_days (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    itinerary_id TEXT NOT NULL,
    day_index    INTEGER NOT NULL DEFAULT 0,
    date         TEXT NOT NULL DEFAULT '',
    title        TEXT NOT NULL DEFAULT '',
    summary      TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (itinerary_id) REFERENCES itineraries(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_days_itinerary ON itinerary_days(itinerary_id);

CREATE TABLE IF NOT EXISTS itinerary_activities (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    day_id       INTEGER NOT NULL,
    activity_index INTEGER NOT NULL DEFAULT 0,
    time_slot    TEXT NOT NULL DEFAULT '',
    title        TEXT NOT NULL DEFAULT '',
    location     TEXT NOT NULL DEFAULT '',
    description  TEXT NOT NULL DEFAULT '',
    image_url    TEXT NOT NULL DEFAULT '',
    cost         REAL NOT NULL DEFAULT 0,
    actual_cost  REAL NOT NULL DEFAULT 0,
    tips         TEXT NOT NULL DEFAULT '',
    checked_in   INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (day_id) REFERENCES itinerary_days(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_activities_day ON itinerary_activities(day_id);

CREATE TABLE IF NOT EXISTS shared_links (
    token        TEXT PRIMARY KEY,
    itinerary_id TEXT NOT NULL,
    user_id      TEXT NOT NULL,
    expires_at   TEXT NOT NULL DEFAULT '',
    view_count   INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_shared_itinerary ON shared_links(itinerary_id);

CREATE TABLE IF NOT EXISTS album_photos (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    itinerary_id   TEXT NOT NULL,
    user_id        TEXT NOT NULL,
    file_name      TEXT NOT NULL DEFAULT '',
    file_size      INTEGER NOT NULL DEFAULT 0,
    mime_type      TEXT NOT NULL DEFAULT '',
    description    TEXT NOT NULL DEFAULT '',
    storage_path   TEXT NOT NULL DEFAULT '',
    thumbnail_path TEXT NOT NULL DEFAULT '',
    day_index      INTEGER NOT NULL DEFAULT 0,
    tags           TEXT NOT NULL DEFAULT '[]',
    ai_description TEXT NOT NULL DEFAULT '',
    latitude       REAL,
    longitude      REAL,
    is_cover       INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (itinerary_id) REFERENCES itineraries(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_photos_itinerary ON album_photos(itinerary_id);
CREATE INDEX IF NOT EXISTS idx_photos_user ON album_photos(user_id);
CREATE INDEX IF NOT EXISTS idx_photos_day ON album_photos(itinerary_id, day_index);
"""


def _json_dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _json_loads(text: str, default=None):
    if not text:
        return default if default is not None else {}
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return default if default is not None else {}
