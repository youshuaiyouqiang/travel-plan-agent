"""新闻来源治理 migration 19 集成测试。

覆盖：
- 启动 init_db 后 ``get_migration_status()['current_version'] == 19``
- 旧数据迁移：4 条内置域名升级为 builtin_whitelist + tier + ai_score=NULL
- 旧数据清理：``reason='初始化内置来源'`` 的占位审计行被删除
- ``news_source_inits`` 表存在且初始为空
- 直接塞旧数据到迁移前数据库，再 init_db 触发迁移，验证升级结果
"""

from __future__ import annotations

import os

import pytest

from application.news.models import Source
from infrastructure.persistence.database import (
    get_connection,
    get_migration_status,
    init_db,
    reset_connection,
)
from infrastructure.persistence.news_repository import NewsSourceRepository


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_migration_19.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    yield db_path
    reset_connection()
    if db_path.exists():
        os.unlink(db_path)


def _seed_legacy_data(db_path) -> None:
    """模拟旧版本数据库：4 条内置来源 + 4 条占位审计行。

    设计要点：
    - 旧版本 schema 没有 ``scoring_mode``/``ai_subscores`` 列。
    - 流程：先用 init_db 创建完整 schema → 抹掉 migration 19 记录 → 插入
      旧 schema 风格的数据（不带新列，依赖默认值 ``ai_candidate``）→ 关闭连接。
    - 下游测试再调用 ``init_db`` 重新应用 migration 19，触发 ALTER + UPDATE。
    """
    # 先用 init_db 把基础表建好
    init_db(db_path)
    # 把 migration 19 从 applied 集合里去掉，让下一次 init_db 真正再次执行它
    conn = get_connection(db_path)
    conn.execute("DELETE FROM schema_migrations WHERE version = 19")
    conn.commit()
    now = "2026-07-19T03:24:58+00:00"
    legacy = [
        ("zhihu.com", "知乎", "mainstream" if False else "unknown"),
        ("weibo.com", "微博", "unknown"),
        ("www.toutiao.com", "头条", "unknown"),
        ("top.baidu.com", "百度热搜", "unknown"),
    ]
    # 用旧 schema 风格 INSERT：不显式指定 scoring_mode / ai_subscores，
    # 由列默认值（``ai_candidate``/``{}``）填充，模拟"旧数据"状态。
    for idx, (domain, name, tier) in enumerate(legacy):
        src_id = f"legacy-{idx}"
        conn.execute(
            "INSERT INTO news_sources "
            "(id, name, domain, tier, status, ai_score, ai_reason, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'enabled', 0.9, '内置默认热搜来源', ?, ?)",
            (src_id, name, domain, tier, now, now),
        )
        conn.execute(
            "INSERT INTO news_source_audits "
            "(id, source_id, admin_id, previous_status, decision, reason, created_at) "
            "VALUES (?, ?, 'admin-1', 'pending', 'enabled', '初始化内置来源', ?)",
            (f"audit-{idx}", src_id, now),
        )
    conn.commit()
    conn.close()


def test_migration_19_upgrades_builtin_sources(tmp_db) -> None:
    _seed_legacy_data(tmp_db)

    # 触发 migration（init_db 在已存在 schema 时只跑 pending migrations）
    reset_connection()
    init_db(tmp_db)

    status = get_migration_status()
    assert status["current_version"] >= 19

    conn = get_connection(tmp_db)
    rows = conn.execute(
        "SELECT id, domain, tier, status, scoring_mode, ai_score, ai_reason, ai_subscores "
        "FROM news_sources ORDER BY domain"
    ).fetchall()
    by_domain = {r["domain"]: r for r in rows}

    assert set(by_domain.keys()) == {
        "zhihu.com",
        "weibo.com",
        "www.toutiao.com",
        "top.baidu.com",
    }
    for domain, row in by_domain.items():
        assert row["scoring_mode"] == "builtin_whitelist", domain
        assert row["ai_score"] is None, domain
        assert row["ai_reason"] == "产品内置白名单", domain
        assert row["ai_subscores"] == "{}", domain
        # tier 已被覆盖
        if domain == "top.baidu.com":
            assert row["tier"] == "aggregator"
        else:
            assert row["tier"] == "mainstream"
    conn.close()


def test_migration_19_deletes_placeholder_audits(tmp_db) -> None:
    _seed_legacy_data(tmp_db)

    # 触发 migration
    reset_connection()
    init_db(tmp_db)

    conn = get_connection(tmp_db)
    placeholder = conn.execute(
        "SELECT COUNT(*) AS n FROM news_source_audits WHERE reason='初始化内置来源'"
    ).fetchone()["n"]
    assert placeholder == 0
    conn.close()


def test_migration_19_creates_init_table(tmp_db) -> None:
    _seed_legacy_data(tmp_db)
    reset_connection()
    init_db(tmp_db)

    conn = get_connection(tmp_db)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='news_source_inits'"
    ).fetchall()
    assert len(rows) == 1
    # migration 自身不写 init 行；启动期 seed 才写
    init_count = conn.execute("SELECT COUNT(*) AS n FROM news_source_inits").fetchone()[
        "n"
    ]
    assert init_count == 0
    conn.close()


def test_migration_19_idempotent(tmp_db) -> None:
    """运行两次 init_db 不应报错。"""
    _seed_legacy_data(tmp_db)
    reset_connection()
    init_db(tmp_db)
    reset_connection()
    init_db(tmp_db)  # 第二次；不应抛错

    status = get_migration_status()
    assert status["current_version"] >= 19


def test_migration_19_keeps_real_audits(tmp_db) -> None:
    """仅删除 reason='初始化内置来源' 的占位行；真实审核行不应被波及。"""
    _seed_legacy_data(tmp_db)
    conn = get_connection(tmp_db)
    # 追加 1 条真实审核行
    conn.execute(
        "INSERT INTO news_source_audits "
        "(id, source_id, admin_id, previous_status, decision, reason, created_at) "
        "VALUES ('real-audit', 'legacy-0', 'admin-1', 'enabled', 'rejected', '不实信息', '2026-07-20T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()

    reset_connection()
    init_db(tmp_db)

    conn = get_connection(tmp_db)
    real = conn.execute(
        "SELECT COUNT(*) AS n FROM news_source_audits WHERE id='real-audit'"
    ).fetchone()["n"]
    assert real == 1
    conn.close()


def test_news_source_repository_handles_new_columns(tmp_db) -> None:
    """Migration 19 后，repository 能正确读写 scoring_mode / ai_subscores。"""
    init_db(tmp_db)
    repo = NewsSourceRepository()
    src = Source(
        id="s1",
        name="example",
        domain="example.com",
        tier="mainstream",
        status="enabled",
        scoring_mode="builtin_whitelist",
        ai_score=None,
        ai_reason="产品内置白名单",
        ai_subscores="{}",
        created_at="2026-07-20T00:00:00+00:00",
        updated_at="2026-07-20T00:00:00+00:00",
    )
    repo.insert_source(src)
    fetched = repo.get_source_by_id("s1")
    assert fetched is not None
    assert fetched.scoring_mode == "builtin_whitelist"
    assert fetched.ai_score is None
    assert fetched.ai_subscores == "{}"
