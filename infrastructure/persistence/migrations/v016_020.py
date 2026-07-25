"""迁移版本 16–20。

从 ``database.py`` 拆分（P1）；SQL 文本与逻辑完全保留，不得修改。
"""

from __future__ import annotations

import logging
from typing import Any

from infrastructure.persistence.migrations.types import Migration

logger = logging.getLogger(__name__)


def _upgrade_16(conn: Any) -> None:
    """Task 2（学术计划）: 重建 ``profiles`` 表，移除 ``emotion_history`` 列。

    业务红线：删除情感识别，不留兼容字段。SQLite 3.35 之前不支持 ``DROP COLUMN``，
    故采用重建表方式：
    1. 创建不含 ``emotion_history`` 列的新表 ``profiles_new``
    2. 从旧表拷贝允许的元数据（不拷贝 emotion_history）
    3. 删除旧表，重命名新表为 ``profiles``
    4. 全新部署（旧表不存在）时仅创建新表，不执行数据拷贝
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS profiles_new (
            user_id           TEXT PRIMARY KEY,
            tags              TEXT NOT NULL DEFAULT '[]',
            interaction_count INTEGER NOT NULL DEFAULT 0,
            last_intent       TEXT NOT NULL DEFAULT '',
            preferred_categories TEXT NOT NULL DEFAULT '[]',
            custom_attributes TEXT NOT NULL DEFAULT '{}',
            created_at        TEXT NOT NULL DEFAULT '',
            updated_at        TEXT NOT NULL DEFAULT ''
        )
        """
    )

    old_cols = {row[1] for row in conn.execute("PRAGMA table_info(profiles)").fetchall()}
    if "user_id" in old_cols:
        # 旧表存在：拷贝允许的元数据（emotion_history 被丢弃）
        conn.execute(
            "INSERT OR IGNORE INTO profiles_new "
            "(user_id, tags, interaction_count, last_intent, preferred_categories, "
            "custom_attributes, created_at, updated_at) "
            "SELECT user_id, tags, interaction_count, last_intent, preferred_categories, "
            "custom_attributes, created_at, updated_at FROM profiles"
        )
        conn.execute("DROP TABLE profiles")
        logger.info("Migration 16: migrated existing profiles rows (emotion_history dropped)")
    else:
        # 全新部署：旧表不存在，清理可能残留的占位
        conn.execute("DROP TABLE IF EXISTS profiles")

    conn.execute("ALTER TABLE profiles_new RENAME TO profiles")
    conn.commit()
    logger.info("Migration 16: rebuilt profiles without emotion_history column")


def _downgrade_16(conn: Any) -> None:
    """回滚迁移 16 — 重建带 ``emotion_history`` 列的 ``profiles`` 表。

    降级是单向不可逆的：已被丢弃的 emotion_history 无法恢复。
    重建空列仅保证 schema 兼容旧版本。
    """
    conn.execute("DROP TABLE IF EXISTS profiles")
    conn.execute(
        """
        CREATE TABLE profiles (
            user_id           TEXT PRIMARY KEY,
            tags              TEXT NOT NULL DEFAULT '[]',
            interaction_count INTEGER NOT NULL DEFAULT 0,
            last_intent       TEXT NOT NULL DEFAULT '',
            preferred_categories TEXT NOT NULL DEFAULT '[]',
            emotion_history   TEXT NOT NULL DEFAULT '[]',
            custom_attributes TEXT NOT NULL DEFAULT '{}',
            created_at        TEXT NOT NULL DEFAULT '',
            updated_at        TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.commit()
    logger.warning(
        "Migration 16 downgrade: rebuilt profiles with emotion_history column (empty; "
        "previously dropped data cannot be restored)"
    )


def _upgrade_17(conn: Any) -> None:
    """P1-1: 重建 ``itinerary_activities`` 表，移除 ``actual_cost`` / ``checked_in`` 列。

    业务红线：删除打卡与实际费用，不留兼容字段。SQLite 3.35 之前不支持
    ``DROP COLUMN``，故采用重建表方式：

    1. 创建不含 ``actual_cost`` / ``checked_in`` 列的新表 ``itinerary_activities_new``
    2. 从旧表拷贝允许的字段（丢弃 actual_cost / checked_in）
    3. 删除旧表，重命名新表为 ``itinerary_activities``
    4. 重建索引
    5. 全新部署（旧表不存在）时仅创建新表，不执行数据拷贝
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS itinerary_activities_new (
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
        )
        """
    )

    old_cols = {row[1] for row in conn.execute("PRAGMA table_info(itinerary_activities)").fetchall()}
    if "id" in old_cols:
        # 旧表存在：拷贝允许的字段（actual_cost / checked_in 被丢弃）
        conn.execute(
            "INSERT OR IGNORE INTO itinerary_activities_new "
            "(id, day_id, activity_index, time_slot, title, location, description, "
            "image_url, cost, tips) "
            "SELECT id, day_id, activity_index, time_slot, title, location, description, "
            "image_url, cost, tips FROM itinerary_activities"
        )
        conn.execute("DROP TABLE itinerary_activities")
        logger.info("Migration 17: migrated existing itinerary_activities rows (actual_cost/checked_in dropped)")
    else:
        conn.execute("DROP TABLE IF EXISTS itinerary_activities")

    conn.execute("ALTER TABLE itinerary_activities_new RENAME TO itinerary_activities")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_activities_day ON itinerary_activities(day_id)")
    conn.commit()
    logger.info("Migration 17: rebuilt itinerary_activities without actual_cost/checked_in columns")


def _downgrade_17(conn: Any) -> None:
    """回滚迁移 17 — 重建带 ``actual_cost`` / ``checked_in`` 列的 ``itinerary_activities`` 表。

    降级是单向不可逆的：已被丢弃的打卡/实际费用数据无法恢复。
    重建空列仅保证 schema 兼容旧版本。
    """
    conn.execute("DROP TABLE IF EXISTS itinerary_activities")
    conn.execute(
        """
        CREATE TABLE itinerary_activities (
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
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_activities_day ON itinerary_activities(day_id)")
    conn.commit()
    logger.warning(
        "Migration 17 downgrade: rebuilt itinerary_activities with actual_cost/checked_in columns (empty; "
        "previously dropped data cannot be restored)"
    )


def _upgrade_18(conn: Any) -> None:
    """P1-3: 修复 ``custom_agents`` 表的外键引用错误。

    迁移 3 创建表时误用 ``FOREIGN KEY (user_id) REFERENCES users(id)``，
    但 ``users`` 表的主键列名是 ``user_id`` 而非 ``id``。当 ``PRAGMA foreign_keys=ON``
    时，任何 INSERT/UPDATE/DELETE 都会抛 ``foreign key mismatch`` 错误。

    修复方式（SQLite 3.35 之前不支持 DROP COLUMN，采用重建）：
    1. 创建带正确外键引用的 ``custom_agents_new`` 表
    2. 从旧表拷贝全部字段
    3. 删除旧表，重命名新表为 ``custom_agents``
    4. 重建索引
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS custom_agents_new (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            icon TEXT DEFAULT '🤖',
            system_prompt TEXT NOT NULL,
            skills TEXT DEFAULT '[]',
            mcp_servers TEXT DEFAULT '[]',
            status TEXT DEFAULT 'published',
            welcome_message TEXT,
            temperature REAL DEFAULT 0.7,
            is_public INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        """
    )

    old_cols = {row[1] for row in conn.execute("PRAGMA table_info(custom_agents)").fetchall()}
    if "id" in old_cols:
        # 旧表存在：拷贝所有字段
        conn.execute(
            "INSERT OR IGNORE INTO custom_agents_new "
            "(id, user_id, name, description, icon, system_prompt, skills, mcp_servers, "
            "status, welcome_message, temperature, is_public, created_at, updated_at) "
            "SELECT id, user_id, name, description, icon, system_prompt, skills, mcp_servers, "
            "status, welcome_message, temperature, is_public, created_at, updated_at FROM custom_agents"
        )
        conn.execute("DROP TABLE custom_agents")
        logger.info("Migration 18: migrated existing custom_agents rows with corrected FK")
    else:
        conn.execute("DROP TABLE IF EXISTS custom_agents")

    conn.execute("ALTER TABLE custom_agents_new RENAME TO custom_agents")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_custom_agents_user ON custom_agents(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_custom_agents_public ON custom_agents(is_public)")
    conn.commit()
    logger.info("Migration 18: rebuilt custom_agents with correct FK reference to users(user_id)")


def _downgrade_18(conn: Any) -> None:
    """回滚迁移 18 — 重建带错误外键的 ``custom_agents`` 表（仅用于回滚兼容）。

    注意：回滚后表恢复到错误状态（FK 指向 users(id)），生产环境不应回滚。
    """
    conn.execute("DROP TABLE IF EXISTS custom_agents")
    conn.execute(
        """
        CREATE TABLE custom_agents (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            icon TEXT DEFAULT '🤖',
            system_prompt TEXT NOT NULL,
            skills TEXT DEFAULT '[]',
            mcp_servers TEXT DEFAULT '[]',
            status TEXT DEFAULT 'published',
            welcome_message TEXT,
            temperature REAL DEFAULT 0.7,
            is_public INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_custom_agents_user ON custom_agents(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_custom_agents_public ON custom_agents(is_public)")
    conn.commit()
    logger.warning("Migration 18 downgrade: restored custom_agents with original (broken) FK")


def _upgrade_19(conn: Any) -> None:
    """新闻来源治理：分离内置白名单与 AI 评分候选。

    业务背景：当前 ``news_sources.ai_score/ai_reason`` 被双重使用——
    既承载 AI 评分候选，也被内置白名单占用为伪 AI 评分（``ai_score=0.9`` +
    ``ai_reason="内置默认热搜来源"``），语义错位；且 4 条占位审计行
    （``reason="初始化内置来源"``）没有承载真实审核信息。

    变更：
    1. 给 ``news_sources`` 加 ``scoring_mode`` 和 ``ai_subscores`` 两列（幂等）。
    2. 把内置 4 条域名升级为 ``scoring_mode=builtin_whitelist``：
       ``ai_score=NULL``、``ai_reason='产品内置白名单'``、tier 改为
       ``mainstream`` / ``aggregator``。
    3. 删除 ``news_source_audits`` 里 ``reason='初始化内置来源'`` 的占位行。
    4. 新建 ``news_source_inits`` 表，承载"系统初始化事件"，替代占位审计。
    """
    # 1) ALTER TABLE 幂等添加新列
    cols = {row[1] for row in conn.execute("PRAGMA table_info(news_sources)").fetchall()}
    if "scoring_mode" not in cols:
        conn.execute(
            "ALTER TABLE news_sources ADD COLUMN scoring_mode TEXT "
            "NOT NULL DEFAULT 'ai_candidate'"
        )
        logger.info("Migration 19: added news_sources.scoring_mode")
    if "ai_subscores" not in cols:
        conn.execute(
            "ALTER TABLE news_sources ADD COLUMN ai_subscores TEXT "
            "NOT NULL DEFAULT '{}'"
        )
        logger.info("Migration 19: added news_sources.ai_subscores")

    # 2) 迁移 4 条内置来源
    cur = conn.execute(
        "SELECT COUNT(*) AS n FROM news_sources "
        "WHERE domain IN ('zhihu.com','weibo.com','www.toutiao.com','top.baidu.com')"
    )
    builtin_count = cur.fetchone()["n"]
    if builtin_count > 0:
        conn.execute(
            "UPDATE news_sources "
            "SET scoring_mode='builtin_whitelist', "
            "    ai_score=NULL, "
            "    ai_reason='产品内置白名单', "
            "    ai_subscores='{}', "
            "    tier=CASE domain "
            "        WHEN 'top.baidu.com' THEN 'aggregator' "
            "        ELSE 'mainstream' END, "
            "    updated_at=strftime('%Y-%m-%dT%H:%M:%f+00:00','now') "
            "WHERE domain IN ('zhihu.com','weibo.com','www.toutiao.com','top.baidu.com')"
        )
        logger.info(
            "Migration 19: upgraded %d built-in sources to scoring_mode=builtin_whitelist",
            builtin_count,
        )

    # 3) 清理占位审计行
    cur = conn.execute(
        "SELECT COUNT(*) AS n FROM news_source_audits WHERE reason='初始化内置来源'"
    )
    placeholder_audits = cur.fetchone()["n"]
    if placeholder_audits > 0:
        conn.execute("DELETE FROM news_source_audits WHERE reason='初始化内置来源'")
        logger.info(
            "Migration 19: deleted %d placeholder audit rows with reason='初始化内置来源'",
            placeholder_audits,
        )

    # 4) 新建 news_source_inits 表
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS news_source_inits (
            id           TEXT PRIMARY KEY,
            source_id    TEXT NOT NULL,
            tier         TEXT NOT NULL,
            scoring_mode TEXT NOT NULL,
            init_at      TEXT NOT NULL,
            init_reason  TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (source_id) REFERENCES news_sources(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_news_source_inits_source "
        "ON news_source_inits(source_id)"
    )
    conn.commit()
    logger.info("Migration 19: ensured news_source_inits table + news_sources scoring_mode columns")


def _downgrade_19(conn: Any) -> None:
    """回滚迁移 19 — 仅删除 ``news_source_inits`` 表。

    注意：``news_sources`` 上新增的 ``scoring_mode`` / ``ai_subscores`` 列
    无法在 SQLite <3.35 中 DROP。回滚后这两列会保留为无业务语义的状态。
    业务上不应回滚；占位审计行已删除也无法恢复。
    """
    conn.execute("DROP TABLE IF EXISTS news_source_inits")
    conn.commit()
    logger.warning(
        "Migration 19 downgrade: dropped news_source_inits. "
        "scoring_mode/ai_subscores columns remain on news_sources."
    )


def _upgrade_20(conn: Any) -> None:
    """新闻来源治理：清理 migration 19 漏掉的脏数据。

    业务背景：migration 19 把 ``domain IN
    ('zhihu.com','weibo.com','www.toutiao.com','top.baidu.com')`` 的
    4 条内置来源升级为 ``scoring_mode=builtin_whitelist``，但遗漏了：

    1. ``www.zhihu.com``：旧版种子用 ``www.`` 前缀创建的脏行（功能上与
       ``zhihu.com`` 重复），仍保留着 ``ai_score=0.9``、
       ``ai_reason='内置默认热搜来源'``、``tier=unknown`` 等旧占位值。
    2. 任何 ``ai_reason='内置默认热搜来源'`` 且 ``ai_score IS NOT NULL``
       的行：这种组合只能是旧版占位数据，因为内置白名单现在固定是
       ``ai_reason='产品内置白名单'`` + ``ai_score=NULL``。这一条是兜底，
       任何未来出现的同类脏行都会被扫到。

    行为：直接 DELETE 这两类行；不动真实 AI 候选（``ai_reason`` 不匹配）
    和真实内置白名单（``ai_reason='产品内置白名单'``）。删除前记录日志
    便于运维追溯。
    """
    # 1) 精准清理 www.zhihu.com（zhihu.com 的 www. 重复行）
    www_rows = conn.execute(
        "SELECT id, domain, ai_score, ai_reason FROM news_sources "
        "WHERE domain = 'www.zhihu.com'"
    ).fetchall()
    for row in www_rows:
        logger.warning(
            "Migration 20: deleting duplicate www.zhihu.com source row "
            "id=%s ai_score=%s ai_reason=%r",
            row["id"],
            row["ai_score"],
            row["ai_reason"],
        )
    if www_rows:
        conn.execute("DELETE FROM news_sources WHERE domain = 'www.zhihu.com'")

    # 2) 防御性清理：旧版占位文案 + 非 NULL ai_score 的组合
    legacy_rows = conn.execute(
        "SELECT id, domain, ai_score, ai_reason FROM news_sources "
        "WHERE ai_reason = '内置默认热搜来源' AND ai_score IS NOT NULL "
        "AND domain != 'www.zhihu.com'"  # 第一步已删
    ).fetchall()
    for row in legacy_rows:
        logger.warning(
            "Migration 20: deleting legacy placeholder source row "
            "id=%s domain=%s ai_score=%s",
            row["id"],
            row["domain"],
            row["ai_score"],
        )
    if legacy_rows:
        conn.execute(
            "DELETE FROM news_sources "
            "WHERE ai_reason = '内置默认热搜来源' AND ai_score IS NOT NULL"
        )

    conn.commit()
    logger.info(
        "Migration 20: cleaned %d www.zhihu.com rows and %d legacy placeholder rows",
        len(www_rows),
        len(legacy_rows),
    )


def _downgrade_20(conn: Any) -> None:
    """回滚迁移 20 — 数据删除单向不可逆。

    业务上不应回滚；如需恢复，只能从备份还原 ``news_sources`` 表。
    """
    logger.warning(
        "Migration 20 downgrade: no-op. Deleted dirty source rows cannot be "
        "recovered without a database backup."
    )


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=16,
        description="Rebuild profiles without emotion_history column",
        upgrade=_upgrade_16,
        downgrade=_downgrade_16,
    ),
    Migration(
        version=17,
        description="Rebuild itinerary_activities without actual_cost/checked_in columns",
        upgrade=_upgrade_17,
        downgrade=_downgrade_17,
    ),
    Migration(
        version=18,
        description="Fix custom_agents FK to reference users(user_id)",
        upgrade=_upgrade_18,
        downgrade=_downgrade_18,
    ),
    Migration(
        version=19,
        description="News source governance: separate builtin_whitelist vs ai_candidate; cleanup placeholder audits",
        upgrade=_upgrade_19,
        downgrade=_downgrade_19,
    ),
    Migration(
        version=20,
        description="News source governance: cleanup www.zhihu.com + legacy placeholder rows missed by migration 19",
        upgrade=_upgrade_20,
        downgrade=_downgrade_20,
    ),
)
