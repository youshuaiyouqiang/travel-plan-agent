"""domain/feedback/repository.py 单元测试。

覆盖 FeedbackRepository 的 init_table / record / list_by_user / count_by_rating。
"""

from __future__ import annotations

import pytest

from domain.feedback.repository import FeedbackRepository
from infrastructure.persistence.database import init_db, reset_connection


class TestFeedbackRepository:
    @pytest.fixture(autouse=True)
    def _setup_db(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.db"
        monkeypatch.setattr("config.settings.database_path", db_path)
        reset_connection()
        init_db(db_path)

    @pytest.fixture
    def repo(self):
        r = FeedbackRepository()
        r.init_table()
        return r

    def test_init_table_creates_table_and_indexes(self, repo):
        from infrastructure.persistence.database import get_connection

        conn = get_connection()
        # 表存在
        cols = conn.execute("PRAGMA table_info(quality_issues)").fetchall()
        col_names = [c[1] for c in cols]
        assert "session_id" in col_names
        assert "rating" in col_names
        assert "issue_type" in col_names
        # 索引存在
        idx = conn.execute("PRAGMA index_list(quality_issues)").fetchall()
        idx_names = {i[1] for i in idx}
        assert "idx_quality_issues_user" in idx_names
        assert "idx_quality_issues_rating" in idx_names

    def test_record_returns_id(self, repo):
        rid = repo.record(
            session_id="s1",
            user_id="u1",
            rating="bad",
            issue_type="inaccurate",
            comment="回复不准",
            agent_id="travel",
            message_snippet="我要去北京",
        )
        assert rid > 0

    def test_record_truncates_long_message_snippet(self, repo):
        long_snippet = "x" * 1000
        rid = repo.record(
            session_id="s1",
            user_id="u1",
            rating="bad",
            message_snippet=long_snippet,
        )
        assert rid > 0
        rows = repo.list_by_user("u1")
        assert len(rows) == 1
        assert len(rows[0]["message_snippet"]) <= 500

    def test_list_by_user_returns_records_desc(self, repo):
        repo.record(session_id="s1", user_id="u1", rating="bad")
        repo.record(session_id="s2", user_id="u1", rating="good")
        repo.record(session_id="s3", user_id="u2", rating="bad")

        rows = repo.list_by_user("u1")
        assert len(rows) == 2

    def test_list_by_user_respects_limit(self, repo):
        for i in range(10):
            repo.record(session_id=f"s{i}", user_id="u1", rating="bad")
        rows = repo.list_by_user("u1", limit=3)
        assert len(rows) == 3

    def test_count_by_rating(self, repo):
        repo.record(session_id="s1", user_id="u1", rating="bad")
        repo.record(session_id="s2", user_id="u1", rating="good")
        repo.record(session_id="s3", user_id="u1", rating="bad")

        assert repo.count_by_rating("bad") == 2
        assert repo.count_by_rating("good") == 1
        assert repo.count_by_rating("other") == 0

    def test_count_by_rating_empty_table(self, repo):
        assert repo.count_by_rating("bad") == 0
