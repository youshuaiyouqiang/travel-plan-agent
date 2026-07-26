"""``MemoryRepositoryPort`` 的 SQLite 实现。

P2.4 将原本散落在以下位置的裸 SQL 收敛到此：
- ``domain/memory/manager.py`` — ``DualLayerMemoryManager`` 的 LTM/STM 读取、
  last_accessed_at 批量更新、``record_extraction``、``save_conversation``
- ``domain/memory/memory_distiller.py`` — ``MemoryDistiller`` 的候选查找、
  蒸馏晋升（STM→LTM）、衰减状态变迁
- ``domain/memory/memory_extractor.py`` — ``MemoryExtractor.save_extracted`` 的
  去重查询与插入

SQL 文本、参数化方式与事务边界完全保留；不改变表结构或迁移版本。

原子事务方法（``merge_stm_into_existing_ltm`` / ``promote_stm_to_ltm`` /
``record_extraction``）在单连接内执行多语句后统一 commit，保证蒸馏与提取
过程中不会出现 STM 与 LTM 并存的中间态。
"""

from __future__ import annotations

from typing import Any

from domain.memory.manager import LongTermMemory, ShortTermMemory
from infrastructure.persistence.connection import get_connection
from infrastructure.persistence.serialization import _json_dumps, _json_loads

# record_extraction 按 memory_type 选择更新的表名；硬编码白名单，不接受外部输入。
_MEMORY_TABLES = {"short_term": "short_term_memories", "long_term": "long_term_memories"}


class SqliteMemoryRepository:
    """``MemoryRepositoryPort`` 的 SQLite 实现。

    无状态，可单例复用。通过 ``get_connection()`` 获取当前连接，
    支持测试隔离的 ``reset_connection()`` 模式。
    """

    # ── 长期记忆读取 ──────────────────────────────────────────

    def get_long_term_memories(self, user_id: str) -> list[LongTermMemory]:
        """加载用户全部 active LTM，按 last_accessed_at/updated_at 倒序。"""
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, user_id, category, content, source_ids, experience_tag, extraction_count, "
            "last_accessed_at, status, created_at, updated_at "
            "FROM long_term_memories WHERE user_id = ? AND status = 'active' "
            "ORDER BY last_accessed_at DESC, updated_at DESC",
            (user_id,),
        ).fetchall()
        return [
            LongTermMemory(
                id=row["id"],
                user_id=row["user_id"],
                category=row["category"],
                content=row["content"],
                source_ids=_json_loads(row["source_ids"], default=[]),
                experience_tag=row["experience_tag"] if "experience_tag" in row.keys() else "",
                extraction_count=row["extraction_count"],
                last_accessed_at=row["last_accessed_at"],
                status=row["status"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def find_existing_ltm_id(self, user_id: str, category: str, content: str) -> int | None:
        """查找同 user/category/content 的 active LTM ID；不存在返回 None。"""
        conn = get_connection()
        row = conn.execute(
            "SELECT id FROM long_term_memories "
            "WHERE user_id = ? AND category = ? AND content = ? AND status = 'active' LIMIT 1",
            (user_id, category, content),
        ).fetchone()
        return row["id"] if row else None

    def get_ltm_for_decay(self, user_id: str | None) -> list[dict[str, Any]]:
        """加载 LTM 的衰减判定字段。"""
        conn = get_connection()
        if user_id:
            rows = conn.execute(
                "SELECT id, last_accessed_at, status FROM long_term_memories WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, last_accessed_at, status FROM long_term_memories"
            ).fetchall()
        return [dict(row) for row in rows]

    # ── 短期记忆读取 ──────────────────────────────────────────

    def get_recent_short_term_memories(self, user_id: str, limit: int) -> list[ShortTermMemory]:
        """加载用户最近 limit 条 STM（ORDER BY id DESC LIMIT ?）。"""
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, user_id, category, content, experience_tag, "
            "extraction_count, last_accessed_at, created_at "
            "FROM short_term_memories WHERE user_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [self._row_to_short_term(row) for row in rows]

    def get_all_short_term_memories(self, user_id: str) -> list[ShortTermMemory]:
        """加载用户全部 STM（供 build_full_context 的 query 评分路径）。"""
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, user_id, category, content, experience_tag, "
            "extraction_count, last_accessed_at, created_at "
            "FROM short_term_memories WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        return [self._row_to_short_term(row) for row in rows]

    def get_stm_candidates(self, user_id: str, min_extractions: int) -> list[dict[str, Any]]:
        """加载 extraction_count >= min_extractions 的 STM 行。"""
        conn = get_connection()
        rows = conn.execute(
            "SELECT stm.id, stm.user_id, stm.category, stm.content, "
            "stm.experience_tag, stm.extraction_count, stm.last_accessed_at "
            "FROM short_term_memories stm "
            "WHERE stm.user_id = ? AND stm.extraction_count >= ?",
            (user_id, min_extractions),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_stm_for_decay(self, user_id: str | None) -> list[dict[str, Any]]:
        """加载 STM 的衰减判定字段。"""
        conn = get_connection()
        if user_id:
            rows = conn.execute(
                "SELECT id, extraction_count, last_accessed_at FROM short_term_memories WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, extraction_count, last_accessed_at FROM short_term_memories"
            ).fetchall()
        return [dict(row) for row in rows]

    def list_user_ids_with_short_term_memories(self) -> list[str]:
        """列出所有有短期记忆的去重 user_id（排除空字符串）。"""
        conn = get_connection()
        rows = conn.execute(
            "SELECT DISTINCT user_id FROM short_term_memories WHERE user_id != ''"
        ).fetchall()
        return [row["user_id"] for row in rows]

    def find_short_term_duplicate(self, user_id: str, category: str, content: str) -> dict[str, Any] | None:
        """查找同 user/category/content 的 STM 行；不存在返回 None。"""
        conn = get_connection()
        row = conn.execute(
            "SELECT id, extraction_count FROM short_term_memories "
            "WHERE user_id = ? AND category = ? AND content = ? LIMIT 1",
            (user_id, category, content),
        ).fetchone()
        return dict(row) if row else None

    # ── 长期记忆写入 ──────────────────────────────────────────

    def touch_long_term_memories(self, ids: list[int], now: str) -> None:
        """批量更新 LTM 的 last_accessed_at。"""
        if not ids:
            return
        conn = get_connection()
        conn.execute(
            f"UPDATE long_term_memories SET last_accessed_at = ? WHERE id IN ({','.join('?' * len(ids))})",
            (now, *ids),
        )
        conn.commit()

    def update_ltm_status(self, ltm_id: int, status: str, now: str) -> None:
        """更新 LTM 状态与 updated_at。"""
        conn = get_connection()
        conn.execute(
            "UPDATE long_term_memories SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, ltm_id),
        )
        conn.commit()

    def merge_stm_into_existing_ltm(self, stm_id: int, ltm_id: int, now: str) -> None:
        """原子事务：递增已有 LTM 的 extraction_count/last_accessed_at/updated_at，并删除源 STM。"""
        conn = get_connection()
        conn.execute(
            "UPDATE long_term_memories SET extraction_count = extraction_count + 1, "
            "last_accessed_at = ?, updated_at = ? WHERE id = ?",
            (now, now, ltm_id),
        )
        conn.execute("DELETE FROM short_term_memories WHERE id = ?", (stm_id,))
        conn.commit()

    def promote_stm_to_ltm(
        self,
        *,
        user_id: str,
        category: str,
        content: str,
        source_ids: list[int],
        experience_tag: str,
        extraction_count: int,
        last_accessed_at: str,
        stm_id: int,
        now: str,
    ) -> None:
        """原子事务：将 STM 蒸馏为新 LTM 行，并删除源 STM。"""
        conn = get_connection()
        conn.execute(
            "INSERT INTO long_term_memories "
            "(user_id, category, content, source_ids, experience_tag, extraction_count, "
            "last_accessed_at, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)",
            (
                user_id,
                category,
                content,
                _json_dumps(source_ids),
                experience_tag,
                extraction_count,
                last_accessed_at or now,
                now,
                now,
            ),
        )
        conn.execute("DELETE FROM short_term_memories WHERE id = ?", (stm_id,))
        conn.commit()

    # ── 短期记忆写入 ──────────────────────────────────────────

    def touch_short_term_memories(self, ids: list[int], now: str) -> None:
        """批量更新 STM 的 last_accessed_at。"""
        if not ids:
            return
        conn = get_connection()
        conn.execute(
            f"UPDATE short_term_memories SET last_accessed_at = ? WHERE id IN ({','.join('?' * len(ids))})",
            (now, *ids),
        )
        conn.commit()

    def update_stm_source_conv(self, stm_id: int, conversation_id: int, now: str) -> None:
        """更新 STM 的 source_conv_id 与 last_accessed_at。"""
        conn = get_connection()
        conn.execute(
            "UPDATE short_term_memories SET source_conv_id = ?, last_accessed_at = ? WHERE id = ?",
            (conversation_id, now, stm_id),
        )
        conn.commit()

    def insert_short_term(
        self,
        *,
        user_id: str,
        category: str,
        content: str,
        conversation_id: int,
        experience_tag: str,
        now: str,
    ) -> int:
        """插入新 STM 行，返回 lastrowid。"""
        conn = get_connection()
        cursor = conn.execute(
            "INSERT INTO short_term_memories "
            "(user_id, category, content, source_conv_id, experience_tag, "
            "extraction_count, last_accessed_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, 0, ?, ?)",
            (user_id, category, content, conversation_id, experience_tag, now, now),
        )
        conn.commit()
        return cursor.lastrowid or 0

    def delete_short_term(self, stm_id: int) -> None:
        """按 ID 删除单条 STM。"""
        conn = get_connection()
        conn.execute("DELETE FROM short_term_memories WHERE id = ?", (stm_id,))
        conn.commit()

    # ── 会话与提取记录 ────────────────────────────────────────

    def save_conversation(self, session_id: str, user_id: str, summary: str, now: str) -> int:
        """插入 conversation 行，返回 lastrowid。summary 截断至 200 字。"""
        conn = get_connection()
        cursor = conn.execute(
            "INSERT INTO conversations (session_id, user_id, summary, created_at) VALUES (?, ?, ?, ?)",
            (session_id, user_id, summary[:200], now),
        )
        conn.commit()
        return cursor.lastrowid or 0

    def record_extraction(
        self,
        *,
        conversation_id: int,
        memory_type: str,
        memory_id: int,
        relevance: float,
        now: str,
    ) -> None:
        """原子事务：插入 memory_extractions 行，并递增对应记忆的 extraction_count。"""
        table = _MEMORY_TABLES.get(memory_type)
        if table is None:
            raise ValueError(f"Unknown memory_type: {memory_type!r}; expected 'short_term' or 'long_term'")
        conn = get_connection()
        conn.execute(
            "INSERT INTO memory_extractions (conversation_id, memory_type, memory_id, relevance, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (conversation_id, memory_type, memory_id, relevance, now),
        )
        conn.execute(
            f"UPDATE {table} SET extraction_count = extraction_count + 1, last_accessed_at = ? WHERE id = ?",
            (now, memory_id),
        )
        conn.commit()

    def get_distinct_conversation_ids_for_memory(self, memory_id: int) -> list[int]:
        """查询与某条 STM 关联的去重会话 ID 列表。"""
        conn = get_connection()
        rows = conn.execute(
            "SELECT DISTINCT c.id FROM memory_extractions me "
            "JOIN conversations c ON me.conversation_id = c.id "
            "WHERE me.memory_type = 'short_term' AND me.memory_id = ?",
            (memory_id,),
        ).fetchall()
        return [row["id"] for row in rows]

    # ── 辅助 ─────────────────────────────────────────────────

    @staticmethod
    def _row_to_short_term(row: Any) -> ShortTermMemory:
        """将数据库行映射为 ShortTermMemory 对象。"""
        return ShortTermMemory(
            id=row["id"],
            user_id=row["user_id"],
            category=row["category"],
            content=row["content"],
            experience_tag=row["experience_tag"],
            extraction_count=row["extraction_count"],
            last_accessed_at=row["last_accessed_at"],
            created_at=row["created_at"],
        )


__all__ = ["SqliteMemoryRepository"]
