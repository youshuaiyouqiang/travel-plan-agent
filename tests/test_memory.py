"""Tests for core/memory.py — MemoryRecord, MemoryManager, DualLayerMemoryManager, SessionMemory"""
import pytest

from domain.memory.manager import MemoryRecord, MemoryManager, DualLayerMemoryManager, ShortTermMemory, LongTermMemory, SessionMemory
from domain.user.session.manager import Session
from infrastructure.persistence.database import init_db, reset_connection, _json_dumps


class TestMemoryRecord:
    def test_construction(self):
        record = MemoryRecord(text="我喜欢Python", source="user", scope_id="u1")
        assert record.text == "我喜欢Python"
        assert record.source == "user"
        assert record.scope_id == "u1"
        assert record.created_at

    def test_defaults(self):
        record = MemoryRecord(text="some fact", source="conversation")
        assert record.scope_id == "default"
        assert record.created_at


class TestMemoryManager:
    @pytest.fixture(autouse=True)
    def _setup_db(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.db"
        monkeypatch.setattr("config.settings.database_path", db_path)
        reset_connection()
        init_db(db_path)

    def test_remember_and_search(self):
        manager = MemoryManager()
        manager.remember("我喜欢编程", source="user", scope_id="u1")
        manager.remember("我的名字是小明", source="user", scope_id="u1")

        results = manager.search("编程", scope_id="u1")
        assert len(results) == 1
        assert results[0].text == "我喜欢编程"

    def test_search_no_match(self):
        manager = MemoryManager()
        manager.remember("我喜欢编程", source="user", scope_id="u1")

        results = manager.search("天气", scope_id="u1")
        assert len(results) == 0

    def test_search_across_scopes(self):
        manager = MemoryManager()
        manager.remember("u1的爱好", source="user", scope_id="u1")
        manager.remember("u2的爱好", source="user", scope_id="u2")

        results = manager.search("爱好", scope_id="u1")
        assert len(results) == 1
        assert results[0].text == "u1的爱好"

    def test_remember_skips_duplicate(self):
        manager = MemoryManager()
        manager.remember("相同的记忆", source="user", scope_id="u1")
        manager.remember("相同的记忆", source="user", scope_id="u1")

        results = manager.search("记忆", scope_id="u1")
        assert len(results) == 1

    def test_remember_skips_empty(self):
        manager = MemoryManager()
        manager.remember("", source="user", scope_id="u1")
        manager.remember("   ", source="user", scope_id="u1")

        results = manager.list_recent(scope_id="u1")
        assert len(results) == 0

    def test_build_context(self):
        manager = MemoryManager()
        manager.remember("我喜欢Python", source="user", scope_id="u1")
        manager.remember("我喜欢编程", source="user", scope_id="u1")

        context = manager.build_context("编程", scope_id="u1")
        assert "我喜欢Python" in context or "我喜欢编程" in context

    def test_build_context_empty(self):
        manager = MemoryManager()
        context = manager.build_context("anything", scope_id="empty_scope")
        assert context == ""

    def test_list_recent(self):
        manager = MemoryManager()
        for i in range(5):
            manager.remember(f"记忆 {i}", source="user", scope_id="u1")

        recent = manager.list_recent(limit=2, scope_id="u1")
        assert len(recent) == 2
        assert recent[0].text == "记忆 3"
        assert recent[1].text == "记忆 4"

    def test_maybe_learn_from_message_triggers(self):
        manager = MemoryManager()

        manager.maybe_learn_from_message("我叫小明", scope_id="u1")
        manager.maybe_learn_from_message("我喜欢编程", scope_id="u1")
        manager.maybe_learn_from_message("请记住密码是abc", scope_id="u1")
        manager.maybe_learn_from_message("记住今天的会议", scope_id="u1")
        manager.maybe_learn_from_message("my name is Alice", scope_id="u1")
        manager.maybe_learn_from_message("i prefer dark mode", scope_id="u1")
        manager.maybe_learn_from_message("i like coffee", scope_id="u1")
        manager.maybe_learn_from_message("remember that deadline is Friday", scope_id="u1")

        results = manager.list_recent(limit=10, scope_id="u1")
        assert len(results) == 8

    def test_maybe_learn_from_message_no_trigger(self):
        manager = MemoryManager()

        manager.maybe_learn_from_message("今天天气怎么样", scope_id="u1")
        manager.maybe_learn_from_message("帮我查一下新闻", scope_id="u1")

        results = manager.list_recent(scope_id="u1")
        assert len(results) == 0

    def test_persistence(self):
        manager1 = MemoryManager()
        manager1.remember("持久化记忆", source="user", scope_id="u1")

        manager2 = MemoryManager()
        results = manager2.search("持久化", scope_id="u1")
        assert len(results) == 1
        assert results[0].text == "持久化记忆"


class TestDualLayerMemoryManager:
    @pytest.fixture(autouse=True)
    def _setup_db(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.db"
        monkeypatch.setattr("config.settings.database_path", db_path)
        reset_connection()
        init_db(db_path)

    def _seed_short_term(self, user_id="u1"):
        from infra.db import get_connection
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
        from infra.db import get_connection
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
        from infra.db import get_connection
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
        from infra.db import get_connection
        conn = get_connection()
        row = conn.execute(
            "SELECT extraction_count FROM short_term_memories WHERE id = 1"
        ).fetchone()
        assert row["extraction_count"] == 1

    def test_legacy_compat(self):
        mgr = DualLayerMemoryManager()
        mgr.remember("test memory", source="user", scope_id="u1")
        results = mgr.search("test", scope_id="u1")
        assert len(results) == 1
        assert results[0].text == "test memory"

    def test_build_context_delegates_to_legacy(self):
        mgr = DualLayerMemoryManager()
        mgr.remember("legacy test", source="user", scope_id="u1")
        context = mgr.build_context("legacy", scope_id="u1")
        assert "legacy test" in context


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
