from __future__ import annotations

import json
import logging
import sqlite3
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


def init_db(db_path: str | Path | None = None) -> None:
    conn = get_connection(db_path)
    conn.executescript(_SCHEMA)
    conn.commit()
    _run_migrations(conn)
    logger.info("Database initialized: %s", db_path or settings.database_path)


def _run_migrations(conn: Any) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(long_term_memories)").fetchall()}
    if "experience_tag" not in existing:
        conn.execute("ALTER TABLE long_term_memories ADD COLUMN experience_tag TEXT NOT NULL DEFAULT ''")
        conn.commit()
        logger.info("Migration: added experience_tag to long_term_memories")

    act_cols = {row[1] for row in conn.execute("PRAGMA table_info(itinerary_activities)").fetchall()}
    if "actual_cost" not in act_cols:
        conn.execute("ALTER TABLE itinerary_activities ADD COLUMN actual_cost REAL NOT NULL DEFAULT 0")
        conn.commit()
        logger.info("Migration: added actual_cost to itinerary_activities")

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
    logger.info("Migration: ensured custom_agents table exists")

    # 新增 mcp_servers 列（try/except 兼容已存在列）
    try:
        ca_cols = {row[1] for row in conn.execute("PRAGMA table_info(custom_agents)").fetchall()}
        if "mcp_servers" not in ca_cols:
            conn.execute("ALTER TABLE custom_agents ADD COLUMN mcp_servers TEXT DEFAULT '[]'")
            conn.commit()
            logger.info("Migration: added mcp_servers to custom_agents")
        if "status" not in ca_cols:
            conn.execute("ALTER TABLE custom_agents ADD COLUMN status TEXT DEFAULT 'published'")
            conn.commit()
            logger.info("Migration: added status to custom_agents")
    except Exception:
        logger.info("Migration: custom_agents columns already exist (skipped)")

    # sessions 表增加委派上下文字段（Phase 3 需要，提前迁移）
    try:
        s_cols = {row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
        if "delegation_agent_id" not in s_cols:
            conn.execute("ALTER TABLE sessions ADD COLUMN delegation_agent_id TEXT DEFAULT NULL")
            conn.commit()
            logger.info("Migration: added delegation_agent_id to sessions")
        if "delegation_started_at" not in s_cols:
            conn.execute("ALTER TABLE sessions ADD COLUMN delegation_started_at REAL DEFAULT NULL")
            conn.commit()
            logger.info("Migration: added delegation_started_at to sessions")
        if "delegation_last_interaction" not in s_cols:
            conn.execute("ALTER TABLE sessions ADD COLUMN delegation_last_interaction REAL DEFAULT NULL")
            conn.commit()
            logger.info("Migration: added delegation_last_interaction to sessions")
        if "disclosed_tools" not in s_cols:
            conn.execute("ALTER TABLE sessions ADD COLUMN disclosed_tools TEXT DEFAULT '[]'")
            conn.commit()
            logger.info("Migration: added disclosed_tools to sessions")
    except Exception:
        logger.info("Migration: sessions delegation/disclosed columns already exist (skipped)")

    # quality_issues 表（Phase 4 反馈机制）
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
    logger.info("Migration: ensured quality_issues table exists")

    # 新闻收藏表（热搜收藏功能）
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
    # 给已有表补充 content 列（兼容旧数据库）
    try:
        nf_cols = {row[1] for row in conn.execute("PRAGMA table_info(news_favorites)").fetchall()}
        if "content" not in nf_cols:
            conn.execute("ALTER TABLE news_favorites ADD COLUMN content TEXT NOT NULL DEFAULT ''")
            conn.commit()
            logger.info("Migration: added content to news_favorites")
    except Exception:
        logger.info("Migration: news_favorites content column already exists (skipped)")
    conn.commit()
    logger.info("Migration: ensured news_favorites table exists")

    # sessions 表增加 user_id 列（P0-4：替代 tasks 表作为 session↔user 映射）
    try:
        s_cols = {row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
        if "user_id" not in s_cols:
            conn.execute("ALTER TABLE sessions ADD COLUMN user_id TEXT NOT NULL DEFAULT ''")
            conn.commit()
            # 回填：从 tasks 表反查已知的 session↔user 映射
            rows = conn.execute(
                "SELECT DISTINCT session_id, user_id FROM tasks WHERE user_id != ''"
            ).fetchall()
            for row in rows:
                conn.execute(
                    "UPDATE sessions SET user_id = ? WHERE session_id = ?",
                    (row["user_id"], row["session_id"]),
                )
            conn.commit()
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)")
            conn.commit()
            logger.info("Migration: added user_id to sessions, backfilled %d rows", len(rows))
    except Exception:
        logger.info("Migration: sessions user_id column already exists (skipped)")

    # ★ 多方案升级：itinerary 表新增 plans_json / confirmed_plan / confirmed_at / recommended_plan 列
    try:
        it_cols = {row[1] for row in conn.execute("PRAGMA table_info(itineraries)").fetchall()}
        if "plans_json" not in it_cols:
            conn.execute("ALTER TABLE itineraries ADD COLUMN plans_json TEXT")
            conn.commit()
            logger.info("Migration: added plans_json to itineraries")
        if "confirmed_plan" not in it_cols:
            conn.execute("ALTER TABLE itineraries ADD COLUMN confirmed_plan VARCHAR(32) DEFAULT NULL")
            conn.commit()
            logger.info("Migration: added confirmed_plan to itineraries")
        if "confirmed_at" not in it_cols:
            conn.execute("ALTER TABLE itineraries ADD COLUMN confirmed_at VARCHAR(32) DEFAULT NULL")
            conn.commit()
            logger.info("Migration: added confirmed_at to itineraries")
        if "recommended_plan" not in it_cols:
            conn.execute("ALTER TABLE itineraries ADD COLUMN recommended_plan VARCHAR(32) DEFAULT NULL")
            conn.commit()
            logger.info("Migration: added recommended_plan to itineraries")
    except Exception:
        logger.info("Migration: itineraries multi-plan columns already exist (skipped)")

    # ★ sessions 表新增 confirmed_plan / confirmed_at 列（会话级方案确认状态）
    try:
        s_cols = {row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
        if "confirmed_plan" not in s_cols:
            conn.execute("ALTER TABLE sessions ADD COLUMN confirmed_plan VARCHAR(32) DEFAULT NULL")
            conn.commit()
            logger.info("Migration: added confirmed_plan to sessions")
        if "confirmed_at" not in s_cols:
            conn.execute("ALTER TABLE sessions ADD COLUMN confirmed_at VARCHAR(32) DEFAULT NULL")
            conn.commit()
            logger.info("Migration: added confirmed_at to sessions")
    except Exception:
        logger.info("Migration: sessions confirmed_plan/confirmed_at columns already exist (skipped)")


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
