"""初始数据库 schema 常量。

从 ``database.py`` 拆分（P1）。``init_db()`` 在运行迁移前先执行此 schema，
创建全部基础表。迁移随后按版本增量修改这些表。

P1 不修改任何 SQL 文本；此常量与拆分前完全一致。
"""

from __future__ import annotations

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
    tips         TEXT NOT NULL DEFAULT '',
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
