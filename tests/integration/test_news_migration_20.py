"""新闻来源治理 migration 20 集成测试。

覆盖：
- 启动 init_db 后 ``get_migration_status()['current_version'] >= 20``
- ``www.zhihu.com`` 脏行被删除
- ``ai_reason='内置默认热搜来源'`` + ``ai_score IS NOT NULL`` 的占位行被删除
- 真实内置白名单行（``ai_reason='产品内置白名单'``）不被波及
- 真实 AI 候选行（``ai_reason`` 是 LLM rubric 输出的内容）不被波及
- migration 19 已经修过的 4 条 builtin 行不被波及
- 幂等：运行两次 init_db 不报错
- 真实审核审计行不被波及
"""

from __future__ import annotations

import os

import pytest

from infrastructure.persistence.database import (
    get_connection,
    get_migration_status,
    init_db,
    reset_connection,
)


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_migration_20.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    yield db_path
    reset_connection()
    if db_path.exists():
        os.unlink(db_path)


def _seed_dirty_state(db_path) -> None:
    """模拟 migration 19 跑完后的脏状态。

    设计要点：
    - 先用 init_db 跑到 migration 19，把 4 条内置来源升级为 builtin_whitelist；
      然后抹掉 migration 20 记录，让下一次 init_db 重新执行 migration 20。
    - 注入 5 类测试数据：
      a) 4 条 migration 19 已修过的 builtin_whitelist 行（不应被删）
      b) 1 条 www.zhihu.com 脏行（migration 19 漏掉）
      c) 1 条 legacy 占位行（ai_reason='内置默认热搜来源' + ai_score=0.7）
      d) 1 条真实 AI 候选行（ai_reason 是 LLM rubric 输出的内容；不应被删）
      e) 1 条 news_source_audits 真实审核行（不应被删）
    """
    # 跑到 migration 19
    init_db(db_path)
    conn = get_connection(db_path)
    conn.execute("DELETE FROM schema_migrations WHERE version = 20")
    conn.commit()
    conn.close()

    conn = get_connection(db_path)
    now = "2026-07-20T00:00:00+00:00"

    # a) 4 条 migration 19 已升级的 builtin_whitelist 行
    builtin = [
        ("zhihu.com", "知乎热榜", "mainstream"),
        ("weibo.com", "微博热搜", "mainstream"),
        ("www.toutiao.com", "今日头条", "mainstream"),
        ("top.baidu.com", "百度热搜", "aggregator"),
    ]
    for idx, (domain, name, tier) in enumerate(builtin):
        conn.execute(
            "INSERT INTO news_sources "
            "(id, name, domain, tier, status, scoring_mode, ai_score, ai_reason, "
            "ai_subscores, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'enabled', 'builtin_whitelist', NULL, "
            "'产品内置白名单', '{}', ?, ?)",
            (f"builtin-{idx}", name, domain, tier, now, now),
        )

    # b) www.zhihu.com 脏行（migration 19 没命中）
    conn.execute(
        "INSERT INTO news_sources "
        "(id, name, domain, tier, status, scoring_mode, ai_score, ai_reason, "
        "ai_subscores, created_at, updated_at) "
        "VALUES ('dirty-www-zhihu', 'www.zhihu.com', 'www.zhihu.com', 'unknown', "
        "'enabled', 'ai_candidate', 0.9, '内置默认热搜来源', '{}', ?, ?)",
        (now, now),
    )

    # c) 其他域名但同样是旧版占位文案的脏行
    conn.execute(
        "INSERT INTO news_sources "
        "(id, name, domain, tier, status, scoring_mode, ai_score, ai_reason, "
        "ai_subscores, created_at, updated_at) "
        "VALUES ('dirty-legacy', 'some-other.com', 'some-other.com', 'unknown', "
        "'enabled', 'ai_candidate', 0.7, '内置默认热搜来源', '{}', ?, ?)",
        (now, now),
    )

    # d) 真实 AI 候选行 — ai_reason 不是 '内置默认热搜来源'
    conn.execute(
        "INSERT INTO news_sources "
        "(id, name, domain, tier, status, scoring_mode, ai_score, ai_reason, "
        "ai_subscores, created_at, updated_at) "
        "VALUES ('real-ai-candidate', 'somenewssite.com', 'somenewssite.com', 'mainstream', "
        "'pending', 'ai_candidate', 0.65, 'LLM rubric · 总分 0.65 · 建议 needs_review', '{}', ?, ?)",
        (now, now),
    )

    # e) 真实审核审计行
    conn.execute(
        "INSERT INTO news_source_audits "
        "(id, source_id, admin_id, previous_status, decision, reason, created_at) "
        "VALUES ('real-audit', 'real-ai-candidate', 'admin-1', 'pending', 'enabled', "
        "'资料齐全，启用', ?)",
        (now,),
    )
    conn.commit()
    conn.close()


def test_migration_20_cleans_www_zhihu(tmp_db) -> None:
    _seed_dirty_state(tmp_db)

    reset_connection()
    init_db(tmp_db)

    status = get_migration_status()
    assert status["current_version"] >= 20

    conn = get_connection(tmp_db)
    rows = conn.execute(
        "SELECT id, domain FROM news_sources WHERE domain = 'www.zhihu.com'"
    ).fetchall()
    assert rows == [], f"www.zhihu.com should be deleted, found: {rows}"
    conn.close()


def test_migration_20_cleans_legacy_placeholder(tmp_db) -> None:
    _seed_dirty_state(tmp_db)

    reset_connection()
    init_db(tmp_db)

    conn = get_connection(tmp_db)
    rows = conn.execute(
        "SELECT id, domain, ai_reason FROM news_sources "
        "WHERE ai_reason = '内置默认热搜来源' AND ai_score IS NOT NULL"
    ).fetchall()
    assert rows == [], (
        f"legacy placeholder rows should be deleted, found: {rows}"
    )
    conn.close()


def test_migration_20_preserves_builtin_whitelist(tmp_db) -> None:
    """migration 19 已升级的 4 条 builtin_whitelist 行必须保留。"""
    _seed_dirty_state(tmp_db)

    reset_connection()
    init_db(tmp_db)

    conn = get_connection(tmp_db)
    rows = conn.execute(
        "SELECT domain, scoring_mode, ai_score, ai_reason FROM news_sources "
        "WHERE scoring_mode = 'builtin_whitelist' ORDER BY domain"
    ).fetchall()
    domains = {r["domain"] for r in rows}
    assert domains == {
        "zhihu.com",
        "weibo.com",
        "www.toutiao.com",
        "top.baidu.com",
    }
    for r in rows:
        assert r["ai_score"] is None
        assert r["ai_reason"] == "产品内置白名单"
    conn.close()


def test_migration_20_preserves_real_ai_candidate(tmp_db) -> None:
    """真实 AI 候选（ai_reason 是 LLM rubric 输出）必须保留。"""
    _seed_dirty_state(tmp_db)

    reset_connection()
    init_db(tmp_db)

    conn = get_connection(tmp_db)
    row = conn.execute(
        "SELECT id, domain, scoring_mode, ai_score, ai_reason "
        "FROM news_sources WHERE id = 'real-ai-candidate'"
    ).fetchone()
    assert row is not None
    assert row["scoring_mode"] == "ai_candidate"
    assert row["ai_score"] == 0.65
    assert "LLM rubric" in row["ai_reason"]
    conn.close()


def test_migration_20_preserves_real_audits(tmp_db) -> None:
    """真实审核审计行（与 news_sources 脏数据无关）必须保留。"""
    _seed_dirty_state(tmp_db)

    reset_connection()
    init_db(tmp_db)

    conn = get_connection(tmp_db)
    row = conn.execute(
        "SELECT id, reason FROM news_source_audits WHERE id = 'real-audit'"
    ).fetchone()
    assert row is not None
    assert row["reason"] == "资料齐全，启用"
    conn.close()


def test_migration_20_idempotent(tmp_db) -> None:
    """运行两次 init_db 不应报错。"""
    _seed_dirty_state(tmp_db)
    reset_connection()
    init_db(tmp_db)
    reset_connection()
    init_db(tmp_db)  # 第二次；不应抛错

    status = get_migration_status()
    assert status["current_version"] >= 20


def test_migration_20_no_dirty_rows_means_noop(tmp_db) -> None:
    """全新部署没有脏数据时，migration 20 应为 no-op（不报错、不删行）。"""
    init_db(tmp_db)

    conn = get_connection(tmp_db)
    before = conn.execute("SELECT COUNT(*) AS n FROM news_sources").fetchone()["n"]
    conn.close()

    reset_connection()
    init_db(tmp_db)  # 应当幂等通过

    conn = get_connection(tmp_db)
    after = conn.execute("SELECT COUNT(*) AS n FROM news_sources").fetchone()["n"]
    assert before == after
    conn.close()
