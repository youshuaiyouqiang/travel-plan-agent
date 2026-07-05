"""Tests for core/memory_extractor.py and core/memory_distiller.py"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from domain.memory.memory_extractor import MemoryExtractor, ExtractedMemory
from domain.memory.memory_distiller import MemoryDistiller
from infrastructure.persistence.database import init_db, reset_connection, _json_dumps


class TestExtractedMemory:
    def test_defaults(self):
        mem = ExtractedMemory(category="fact", content="住在成都")
        assert mem.experience_tag == ""

    def test_with_experience_tag(self):
        mem = ExtractedMemory(category="experience", content="退票需提前", experience_tag="failure")
        assert mem.experience_tag == "failure"


class TestMemoryExtractor:
    @pytest.fixture(autouse=True)
    def _setup_db(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.db"
        monkeypatch.setattr("config.settings.database_path", db_path)
        reset_connection()
        init_db(db_path)

    @pytest.fixture
    def mock_llm(self):
        llm = MagicMock()
        llm.complete_json = AsyncMock()
        return llm

    @pytest.fixture
    def extractor(self, mock_llm):
        return MemoryExtractor(mock_llm)

    @pytest.mark.asyncio
    async def test_extract_empty_turns(self, extractor):
        result = await extractor.extract([], user_id="u1", session_id="s1")
        assert result == []

    @pytest.mark.asyncio
    async def test_extract_short_conversation(self, extractor):
        result = await extractor.extract(
            [{"role": "user", "content": "hi"}],
            user_id="u1",
            session_id="s1",
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_extract_with_llm_response(self, extractor, mock_llm):
        mock_llm.complete_json.return_value = [
            {"category": "preference", "content": "喜欢吃辣", "experience_tag": ""},
            {"category": "fact", "content": "住在成都", "experience_tag": ""},
            {"category": "experience", "content": "携程退票需提前24小时", "experience_tag": "failure"},
        ]

        turns = [
            {"role": "user", "content": "我喜欢吃辣，住在成都"},
            {"role": "assistant", "content": "好的，了解了"},
        ]
        result = await extractor.extract(turns, user_id="u1", session_id="s1")

        assert len(result) == 3
        assert result[0].category == "preference"
        assert result[0].content == "喜欢吃辣"
        assert result[2].category == "experience"
        assert result[2].experience_tag == "failure"

    @pytest.mark.asyncio
    async def test_extract_llm_returns_empty(self, extractor, mock_llm):
        mock_llm.complete_json.return_value = []

        turns = [
            {"role": "user", "content": "今天天气怎么样"},
            {"role": "assistant", "content": "今天晴天"},
        ]
        result = await extractor.extract(turns, user_id="u1", session_id="s1")
        assert result == []

    @pytest.mark.asyncio
    async def test_extract_llm_failure(self, extractor, mock_llm):
        mock_llm.complete_json.side_effect = Exception("LLM error")

        turns = [
            {"role": "user", "content": "我喜欢编程"},
            {"role": "assistant", "content": "好的"},
        ]
        result = await extractor.extract(turns, user_id="u1", session_id="s1")
        assert result == []

    @pytest.mark.asyncio
    async def test_extract_llm_returns_dict_with_memories(self, extractor, mock_llm):
        mock_llm.complete_json.return_value = {
            "memories": [{"category": "fact", "content": "名字叫小明", "experience_tag": ""}]
        }

        turns = [
            {"role": "user", "content": "我叫小明"},
            {"role": "assistant", "content": "你好小明"},
        ]
        result = await extractor.extract(turns, user_id="u1", session_id="s1")
        assert len(result) == 1
        assert result[0].content == "名字叫小明"

    @pytest.mark.asyncio
    async def test_extract_invalid_category_normalized(self, extractor, mock_llm):
        mock_llm.complete_json.return_value = [
            {"category": "hobby", "content": "打篮球", "experience_tag": ""},
        ]

        turns = [{"role": "user", "content": "我喜欢打篮球"}]
        result = await extractor.extract(turns, user_id="u1", session_id="s1")
        assert len(result) == 1
        assert result[0].category == "fact"

    @pytest.mark.asyncio
    async def test_extract_experience_without_tag(self, extractor, mock_llm):
        mock_llm.complete_json.return_value = [
            {"category": "experience", "content": "某次经历", "experience_tag": "invalid"},
        ]

        turns = [
            {"role": "user", "content": "上次经历了一些事情"},
            {"role": "assistant", "content": "好的，了解了"},
        ]
        result = await extractor.extract(turns, user_id="u1", session_id="s1")
        assert len(result) == 1
        assert result[0].experience_tag == ""

    def test_save_extracted(self, extractor):
        from infrastructure.persistence.database import get_connection

        conn = get_connection()
        conn.execute(
            "INSERT INTO conversations (session_id, user_id, summary, created_at) VALUES (?, ?, ?, datetime('now'))",
            (
                "s1",
                "u1",
                "test",
            ),
        )
        conn.commit()
        conv_id = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]

        memories = [
            ExtractedMemory(category="preference", content="喜欢吃辣"),
            ExtractedMemory(category="fact", content="住在成都"),
        ]
        ids = extractor.save_extracted(memories, user_id="u1", conversation_id=conv_id)
        assert len(ids) == 2
        assert all(isinstance(i, int) for i in ids)

        row = conn.execute("SELECT COUNT(*) as cnt FROM short_term_memories WHERE user_id = 'u1'").fetchone()
        assert row["cnt"] == 2

    def test_save_extracted_dedup(self, extractor):
        from infrastructure.persistence.database import get_connection

        conn = get_connection()
        conn.execute(
            "INSERT INTO conversations (session_id, user_id, summary, created_at) VALUES (?, ?, ?, datetime('now'))",
            (
                "s1",
                "u1",
                "test",
            ),
        )
        conn.commit()
        conv_id = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]

        memories = [ExtractedMemory(category="preference", content="喜欢吃辣")]
        ids1 = extractor.save_extracted(memories, user_id="u1", conversation_id=conv_id)
        ids2 = extractor.save_extracted(memories, user_id="u1", conversation_id=conv_id)

        row = conn.execute("SELECT COUNT(*) as cnt FROM short_term_memories WHERE user_id = 'u1'").fetchone()
        assert row["cnt"] == 1

    def test_format_turns(self, extractor):
        turns = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！"},
            {"role": "user", "content": "帮我查机票"},
        ]
        text = extractor._format_turns(turns)
        assert "用户: 你好" in text
        assert "助手: 你好！" in text
        assert "用户: 帮我查机票" in text


class TestMemoryDistiller:
    @pytest.fixture(autouse=True)
    def _setup_db(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.db"
        monkeypatch.setattr("config.settings.database_path", db_path)
        reset_connection()
        init_db(db_path)

    @pytest.fixture
    def distiller(self):
        mock_llm = MagicMock()
        return MemoryDistiller(mock_llm)

    def _seed_data_for_distillation(self, user_id="u1"):
        from infrastructure.persistence.database import get_connection
        from datetime import datetime

        conn = get_connection()
        now = datetime.utcnow().isoformat()

        conn.execute(
            "INSERT INTO conversations (session_id, user_id, summary, created_at) VALUES (?, ?, ?, ?)",
            ("s1", user_id, "conv1", now),
        )
        conv1_id = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]

        conn.execute(
            "INSERT INTO conversations (session_id, user_id, summary, created_at) VALUES (?, ?, ?, ?)",
            ("s2", user_id, "conv2", now),
        )
        conv2_id = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]

        cursor = conn.execute(
            "INSERT INTO short_term_memories "
            "(user_id, category, content, source_conv_id, experience_tag, "
            "extraction_count, last_accessed_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, "preference", "喜欢吃辣", conv1_id, "", 3, now, now),
        )
        stm_id = cursor.lastrowid

        for conv_id in [conv1_id, conv2_id]:
            conn.execute(
                "INSERT INTO memory_extractions (conversation_id, memory_type, memory_id, relevance, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (conv_id, "short_term", stm_id, 0.8, now),
            )

        conn.commit()
        return stm_id, conv1_id, conv2_id

    def test_find_candidates(self, distiller):
        self._seed_data_for_distillation("u1")
        candidates = distiller._find_candidates("u1")
        assert len(candidates) == 1
        assert candidates[0]["content"] == "喜欢吃辣"

    def test_find_candidates_no_match(self, distiller):
        from infrastructure.persistence.database import get_connection
        from datetime import datetime

        conn = get_connection()
        now = datetime.utcnow().isoformat()
        conn.execute(
            "INSERT INTO short_term_memories "
            "(user_id, category, content, source_conv_id, experience_tag, "
            "extraction_count, last_accessed_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("u1", "fact", "低频记忆", 0, "", 1, now, now),
        )
        conn.commit()

        candidates = distiller._find_candidates("u1")
        assert len(candidates) == 0

    def test_run_distillation(self, distiller):
        from infrastructure.persistence.database import get_connection

        self._seed_data_for_distillation("u1")

        count = distiller.run_distillation("u1")
        assert count == 1

        conn = get_connection()
        ltm = conn.execute("SELECT * FROM long_term_memories WHERE user_id = 'u1'").fetchone()
        assert ltm is not None
        assert ltm["content"] == "喜欢吃辣"
        assert ltm["status"] == "active"

        stm = conn.execute("SELECT * FROM short_term_memories WHERE user_id = 'u1'").fetchone()
        assert stm is None

    def test_run_distillation_dedup_ltm(self, distiller):
        from infrastructure.persistence.database import get_connection
        from datetime import datetime

        conn = get_connection()
        now = datetime.utcnow().isoformat()

        conn.execute(
            "INSERT INTO long_term_memories "
            "(user_id, category, content, source_ids, extraction_count, "
            "last_accessed_at, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("u1", "preference", "喜欢吃辣", "[]", 1, now, "active", now, now),
        )
        conn.commit()

        self._seed_data_for_distillation("u1")

        count = distiller.run_distillation("u1")
        assert count == 1

        ltm_rows = conn.execute(
            "SELECT * FROM long_term_memories WHERE user_id = 'u1' AND content = '喜欢吃辣'"
        ).fetchall()
        assert len(ltm_rows) == 1
        assert ltm_rows[0]["extraction_count"] == 2

    def test_run_distillation_no_candidates(self, distiller):
        count = distiller.run_distillation("nonexistent_user")
        assert count == 0

    def test_run_decay_stale(self, distiller, monkeypatch):
        from infrastructure.persistence.database import get_connection
        from datetime import datetime, timedelta

        conn = get_connection()
        old_date = (datetime.utcnow() - timedelta(days=100)).isoformat()
        now = datetime.utcnow().isoformat()

        conn.execute(
            "INSERT INTO long_term_memories "
            "(user_id, category, content, source_ids, extraction_count, "
            "last_accessed_at, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("u1", "fact", "旧记忆", "[]", 1, old_date, "active", old_date, now),
        )
        conn.commit()

        monkeypatch.setattr("config.settings.memory_stale_days", 90)
        decayed = distiller.run_decay("u1")
        assert decayed == 1

        row = conn.execute("SELECT status FROM long_term_memories WHERE user_id = 'u1'").fetchone()
        assert row["status"] == "stale"

    def test_run_decay_deprecated(self, distiller, monkeypatch):
        from infrastructure.persistence.database import get_connection
        from datetime import datetime, timedelta

        conn = get_connection()
        old_date = (datetime.utcnow() - timedelta(days=130)).isoformat()
        now = datetime.utcnow().isoformat()

        conn.execute(
            "INSERT INTO long_term_memories "
            "(user_id, category, content, source_ids, extraction_count, "
            "last_accessed_at, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("u1", "fact", "很旧记忆", "[]", 1, old_date, "stale", old_date, now),
        )
        conn.commit()

        monkeypatch.setattr("config.settings.memory_stale_days", 90)
        decayed = distiller.run_decay("u1")
        assert decayed >= 1

        row = conn.execute("SELECT status FROM long_term_memories WHERE user_id = 'u1'").fetchone()
        assert row["status"] == "deprecated"

    def test_run_decay_stm_expired(self, distiller, monkeypatch):
        from infrastructure.persistence.database import get_connection
        from datetime import datetime, timedelta

        conn = get_connection()
        old_date = (datetime.utcnow() - timedelta(days=45)).isoformat()
        now = datetime.utcnow().isoformat()

        conn.execute(
            "INSERT INTO short_term_memories "
            "(user_id, category, content, source_conv_id, experience_tag, "
            "extraction_count, last_accessed_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("u1", "fact", "过期短期记忆", 0, "", 1, old_date, now),
        )
        conn.commit()

        monkeypatch.setattr("config.settings.memory_stm_expire_days", 30)
        decayed = distiller.run_decay("u1")
        assert decayed >= 1

        row = conn.execute("SELECT COUNT(*) as cnt FROM short_term_memories WHERE user_id = 'u1'").fetchone()
        assert row["cnt"] == 0

    def test_run_decay_active_not_decayed(self, distiller, monkeypatch):
        from infrastructure.persistence.database import get_connection
        from datetime import datetime

        conn = get_connection()
        now = datetime.utcnow().isoformat()

        conn.execute(
            "INSERT INTO long_term_memories "
            "(user_id, category, content, source_ids, extraction_count, "
            "last_accessed_at, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("u1", "fact", "活跃记忆", "[]", 1, now, "active", now, now),
        )
        conn.commit()

        monkeypatch.setattr("config.settings.memory_stale_days", 90)
        decayed = distiller.run_decay("u1")
        assert decayed == 0

        row = conn.execute("SELECT status FROM long_term_memories WHERE user_id = 'u1'").fetchone()
        assert row["status"] == "active"

    def test_compress_content_fallback(self):
        distiller = MemoryDistiller(None)
        result = distiller._compress_content("这是一段很长的记忆内容需要被压缩", "fact")
        assert len(result) <= 30
