"""Tests for core/session.py — Session, Turn, SessionManager"""
import pytest

from domain.user.session.manager import Session, Turn, SessionManager
from infrastructure.persistence.database import init_db, reset_connection


class TestTurn:
    def test_construction(self):
        turn = Turn(role="user", content="hello")
        assert turn.role == "user"
        assert turn.content == "hello"
        assert turn.created_at

    def test_created_at_format(self):
        turn = Turn(role="assistant", content="hi there", created_at="2025-01-01T00:00:00")
        assert turn.created_at == "2025-01-01T00:00:00"


class TestSession:
    def test_construction(self):
        session = Session(session_id="test_session")
        assert session.session_id == "test_session"
        assert session.turns == []
        assert session.summary == ""
        assert session.created_at
        assert session.updated_at

    def test_append(self):
        session = Session(session_id="s1")
        session.append("user", "你好")
        session.append("assistant", "你好！")
        assert len(session.turns) == 2
        assert session.turns[0].role == "user"
        assert session.turns[0].content == "你好"
        assert session.turns[1].role == "assistant"
        assert session.turns[1].content == "你好！"

    def test_recent_messages(self):
        session = Session(session_id="s1")
        for i in range(10):
            session.append("user", f"msg {i}")
        recent = session.recent_messages(3)
        assert len(recent) == 3
        assert recent[0].content == "msg 7"
        assert recent[2].content == "msg 9"

    def test_recent_messages_zero_limit(self):
        session = Session(session_id="s1")
        session.append("user", "hello")
        recent = session.recent_messages(0)
        assert len(recent) == 1


class TestSessionManager:
    @pytest.fixture(autouse=True)
    def _setup_db(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.db"
        monkeypatch.setattr("config.settings.database_path", db_path)
        reset_connection()
        init_db(db_path)

    def test_get_creates_new_session(self):
        manager = SessionManager()
        session = manager.get("new_session")
        assert session.session_id == "new_session"
        assert session.turns == []

    def test_save_and_reload(self):
        manager = SessionManager()
        session = manager.get("persist_test")
        session.append("user", "hello")
        session.append("assistant", "hi")
        session.summary = "a short chat"
        manager.save(session)

        manager2 = SessionManager()
        loaded = manager2.get("persist_test")
        assert loaded.session_id == "persist_test"
        assert len(loaded.turns) == 2
        assert loaded.turns[0].content == "hello"
        assert loaded.turns[1].content == "hi"
        assert loaded.summary == "a short chat"

    def test_snapshot(self):
        manager = SessionManager()
        session = manager.get("snap_test")
        session.append("user", "test msg")
        manager.save(session)

        snap = manager.snapshot("snap_test")
        assert snap is not None
        assert snap["session_id"] == "snap_test"
        assert len(snap["turns"]) == 1
        assert "task" in snap
