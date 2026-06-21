from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from threading import local

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

CREATE TABLE IF NOT EXISTS memories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    scope_id   TEXT NOT NULL DEFAULT 'default',
    text       TEXT NOT NULL,
    source     TEXT NOT NULL DEFAULT 'conversation',
    created_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_memories_scope ON memories(scope_id);

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
