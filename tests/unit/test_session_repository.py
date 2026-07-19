"""infrastructure/persistence/session_repository.py 单元测试。

覆盖 SessionRepository 的 create / list_by_user / get_messages / delete 路径。
"""

from __future__ import annotations

import pytest

from infrastructure.persistence.database import init_db, reset_connection
from infrastructure.persistence.session_repository import SessionRepository


class TestSessionRepository:
    @pytest.fixture(autouse=True)
    def _setup_db(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.db"
        monkeypatch.setattr("config.settings.database_path", db_path)
        reset_connection()
        init_db(db_path)

    def test_create_inserts_session_and_task(self):
        SessionRepository.create("s1", "u1", summary="hello")
        sessions = SessionRepository.list_by_user("u1")
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == "s1"
        assert sessions[0]["title"] == "hello"

    def test_list_by_user_uses_first_user_message_as_title(self):
        SessionRepository.create("s1", "u1")
        # 模拟插入一条 user 消息
        from infrastructure.persistence.database import get_connection

        conn = get_connection()
        conn.execute(
            "INSERT INTO session_turns (session_id, role, content, created_at) "
            "VALUES (?, 'user', '帮我去北京', ?)",
            ("s1", "2026-07-19T00:00:00"),
        )
        conn.commit()

        sessions = SessionRepository.list_by_user("u1")
        assert len(sessions) == 1
        assert sessions[0]["title"] == "帮我去北京"

    def test_list_by_user_returns_empty_for_unknown_user(self):
        SessionRepository.create("s1", "u1")
        sessions = SessionRepository.list_by_user("other")
        assert sessions == []

    def test_get_messages_returns_turns_in_order(self):
        SessionRepository.create("s1", "u1")
        from infrastructure.persistence.database import get_connection

        conn = get_connection()
        conn.execute(
            "INSERT INTO session_turns (session_id, role, content, created_at) "
            "VALUES (?, 'user', 'first', ?)",
            ("s1", "2026-07-19T00:00:00"),
        )
        conn.execute(
            "INSERT INTO session_turns (session_id, role, content, created_at) "
            "VALUES (?, 'assistant', 'second', ?)",
            ("s1", "2026-07-19T00:00:01"),
        )
        conn.commit()

        msgs = SessionRepository.get_messages("s1")
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "first"
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["content"] == "second"

    def test_get_messages_empty_for_unknown_session(self):
        msgs = SessionRepository.get_messages("nope")
        assert msgs == []

    def test_delete_cascades_session_task_turns(self):
        SessionRepository.create("s1", "u1")
        from infrastructure.persistence.database import get_connection

        conn = get_connection()
        conn.execute(
            "INSERT INTO session_turns (session_id, role, content, created_at) "
            "VALUES (?, 'user', 'hi', ?)",
            ("s1", "2026-07-19T00:00:00"),
        )
        conn.commit()

        SessionRepository.delete("s1")

        # sessions/tasks/turns 三表都应为空
        conn = get_connection()
        assert conn.execute("SELECT COUNT(*) FROM sessions WHERE session_id = ?", ("s1",)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM tasks WHERE session_id = ?", ("s1",)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM session_turns WHERE session_id = ?", ("s1",)).fetchone()[0] == 0

    def test_delete_unknown_session_is_noop(self):
        # 不应抛错
        SessionRepository.delete("does-not-exist")
