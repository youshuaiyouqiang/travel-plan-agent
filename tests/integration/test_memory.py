"""Tests for domain/memory/manager.py — DualLayerMemoryManager, SessionMemory"""
import pytest

from domain.memory.manager import DualLayerMemoryManager, ShortTermMemory, LongTermMemory, SessionMemory
from domain.user.session.manager import Session
from infrastructure.persistence.database import init_db, reset_connection, _json_dumps


class TestDualLayerMemoryManager:
    @pytest.fixture(autouse=True)
    def _setup_db(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.db"
        monkeypatch.setattr("config.settings.database_path", db_path)
        reset_connection()
        init_db(db_path)

    def _seed_short_term(self, user_id="u1"):
        from infrastructure.persistence.database import get_connection
        from datetime import datetime
        conn = get_connection()
        now = datetime.utcnow().isoformat()
        items = [
            (user_id, "preference", "喜欢吃辣", "", 0, now, now),
            (user_id, "fact", "住在成都", "", 0, now, now),
            (user_id, "experience", "携程退票需提前24小时", "failure", 0, now, now),
        ]
        for item in items:
            conn.execute(
                "INSERT INTO short_term_memories (user_id, category, content, experience_tag, "
                "extraction_count, last_accessed_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                item,
            )
        conn.commit()

    def _seed_long_term(self, user_id="u1"):
        from infrastructure.persistence.database import get_connection
        from datetime import datetime
        conn = get_connection()
        now = datetime.utcnow().isoformat()
        items = [
            (user_id, "preference", "偏好川菜", _json_dumps([1]), 5, now, "active", now, now),
            (user_id, "fact", "姓名张三", _json_dumps([2]), 3, now, "active", now, now),
        ]
        for item in items:
            conn.execute(
                "INSERT INTO long_term_memories (user_id, category, content, source_ids, "
                "extraction_count, last_accessed_at, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                item,
            )
        conn.commit()

    def test_get_long_term_memories(self):
        self._seed_long_term("u1")
        mgr = DualLayerMemoryManager()
        ltm = mgr.get_long_term_memories("u1")
        assert len(ltm) == 2
        assert ltm[0].category in ("preference", "fact")
        assert ltm[0].status == "active"

    def test_get_long_term_excludes_stale(self):
        from infrastructure.persistence.database import get_connection
        from datetime import datetime
        conn = get_connection()
        now = datetime.utcnow().isoformat()
        conn.execute(
            "INSERT INTO long_term_memories (user_id, category, content, source_ids, "
            "extraction_count, last_accessed_at, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("u1", "fact", "旧记忆", "[]", 1, now, "stale", now, now),
        )
        conn.commit()

        mgr = DualLayerMemoryManager()
        ltm = mgr.get_long_term_memories("u1")
        assert all(m.status == "active" for m in ltm)

    def test_get_short_term_memories(self):
        self._seed_short_term("u1")
        mgr = DualLayerMemoryManager()
        stm = mgr.get_short_term_memories("u1")
        assert len(stm) == 3

    def test_get_short_term_with_query(self):
        self._seed_short_term("u1")
        mgr = DualLayerMemoryManager()
        stm = mgr.get_short_term_memories("u1", query="辣")
        assert len(stm) == 1
        assert "辣" in stm[0].content

    def test_build_full_context(self):
        self._seed_long_term("u1")
        self._seed_short_term("u1")
        mgr = DualLayerMemoryManager()
        context = mgr.build_full_context("u1", query="辣")
        assert "长期记忆" in context
        assert "近期记忆" in context

    def test_build_full_context_empty(self):
        mgr = DualLayerMemoryManager()
        context = mgr.build_full_context("nonexistent")
        assert context == ""

    def test_save_conversation(self):
        mgr = DualLayerMemoryManager()
        conv_id = mgr.save_conversation("s1", "u1", summary="test summary")
        assert conv_id > 0

    def test_record_extraction(self):
        self._seed_short_term("u1")
        mgr = DualLayerMemoryManager()
        conv_id = mgr.save_conversation("s1", "u1")
        mgr.record_extraction(conv_id, "short_term", 1)
        from infrastructure.persistence.database import get_connection
        conn = get_connection()
        row = conn.execute(
            "SELECT extraction_count FROM short_term_memories WHERE id = 1"
        ).fetchone()
        assert row["extraction_count"] == 1


class TestSessionMemory:
    def test_refresh_summary_with_turns(self):
        session = Session(session_id="s1")
        session.append("user", "hello")
        session.append("assistant", "hi there")
        session.append("user", "how are you")
        session.append("assistant", "I'm fine")

        SessionMemory().refresh_summary(session)
        assert session.summary
        assert "user" in session.summary or "assistant" in session.summary

    def test_refresh_summary_empty_session(self):
        session = Session(session_id="s1")
        SessionMemory().refresh_summary(session)
        assert session.summary == ""
