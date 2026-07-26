from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from domain.memory.ports import MemoryRepositoryPort, get_default_memory_repository
from domain.user.session.manager import Session

logger = logging.getLogger(__name__)


@dataclass
class ShortTermMemory:
    id: int
    user_id: str
    category: str
    content: str
    experience_tag: str = ""
    extraction_count: int = 0
    last_accessed_at: str = ""
    created_at: str = ""


@dataclass
class LongTermMemory:
    id: int
    user_id: str
    category: str
    content: str
    source_ids: list[int] = field(default_factory=list)
    experience_tag: str = ""
    extraction_count: int = 0
    last_accessed_at: str = ""
    status: str = "active"
    created_at: str = ""
    updated_at: str = ""


class DualLayerMemoryManager:
    """双层记忆管理器；通过 ``MemoryRepositoryPort`` 访问持久化层。

    P2.4：原直连 ``get_connection()`` 的 SQL 与 ``_json_loads`` 已下沉到
    ``infrastructure.persistence.repositories.memory.SqliteMemoryRepository``。
    本类只负责内存中的查询评分、分组渲染与业务逻辑编排。
    """

    def __init__(self, repository: MemoryRepositoryPort | None = None) -> None:
        self._repository = repository or get_default_memory_repository()

    def get_long_term_memories(self, user_id: str) -> list[LongTermMemory]:
        return self._repository.get_long_term_memories(user_id)

    def get_short_term_memories(
        self,
        user_id: str,
        *,
        query: str = "",
        limit: int | None = None,
    ) -> list[ShortTermMemory]:
        max_items = limit or 20

        if query.strip():
            terms = [t for t in query.strip().lower().split() if t]
            all_stms = self._repository.get_all_short_term_memories(user_id)
            scored: list[tuple[int, ShortTermMemory]] = []
            for stm in all_stms:
                hay = stm.content.lower()
                score = sum(1 for term in terms if term in hay)
                if score > 0:
                    scored.append((score, stm))
            scored.sort(key=lambda r: (r[0], r[1].created_at), reverse=True)
            return [stm for _, stm in scored[:max_items]]

        recent = self._repository.get_recent_short_term_memories(user_id, max_items)
        # 仓储按 id DESC 返回；reversed() 还原为窗口内时间正序，保持原有行为
        return list(reversed(recent))

    def build_full_context(self, user_id: str, *, query: str = "") -> str:
        parts: list[str] = []
        now = datetime.utcnow().isoformat()

        ltm_list = self.get_long_term_memories(user_id)
        if ltm_list:
            self._repository.touch_long_term_memories([m.id for m in ltm_list], now)

            category_labels = {"preference": "偏好", "fact": "事实", "experience": "经验"}
            grouped: dict[str, list[str]] = {}
            for mem in ltm_list:
                label = category_labels.get(mem.category, mem.category)
                text = mem.content
                if mem.category == "experience" and mem.experience_tag:
                    tag_label = "✓" if mem.experience_tag == "success" else "✗"
                    text = f"[{tag_label}] {text}"
                if mem.category == "fact":
                    text = f"[待确认] {text}"
                grouped.setdefault(label, []).append(text)

            ltm_lines: list[str] = []
            for cat_label, items in grouped.items():
                for item in items:
                    ltm_lines.append(f"  {cat_label}: {item}")
            parts.append("【用户长期记忆】\n" + "\n".join(ltm_lines))

        stm_list = self.get_short_term_memories(user_id, query=query, limit=10)
        if stm_list:
            self._repository.touch_short_term_memories([m.id for m in stm_list], now)

            category_labels = {"preference": "偏好", "fact": "事实", "experience": "经验"}
            stm_lines: list[str] = []
            for stm_mem in stm_list:
                label = category_labels.get(stm_mem.category, stm_mem.category)
                text = stm_mem.content
                if stm_mem.category == "experience" and stm_mem.experience_tag:
                    tag_label = "✓" if stm_mem.experience_tag == "success" else "✗"
                    text = f"[{tag_label}] {text}"
                if stm_mem.category == "fact":
                    text = f"[待确认] {text}"
                stm_lines.append(f"  {label}: {text}")
            parts.append("【近期记忆】\n" + "\n".join(stm_lines))

        return "\n\n".join(parts)

    def record_extraction(
        self,
        conversation_id: int,
        memory_type: str,
        memory_id: int,
        *,
        relevance: float = 1.0,
    ) -> None:
        now = datetime.utcnow().isoformat()
        self._repository.record_extraction(
            conversation_id=conversation_id,
            memory_type=memory_type,
            memory_id=memory_id,
            relevance=relevance,
            now=now,
        )

    def save_conversation(
        self,
        session_id: str,
        user_id: str,
        summary: str = "",
    ) -> int:
        now = datetime.utcnow().isoformat()
        return self._repository.save_conversation(session_id, user_id, summary, now)

    def delete_memory(self, *, user_id: str, memory_type: str, memory_id: int) -> bool:
        """删除单条记忆；校验所有权，不通过返回 False。

        P3.3b：将 ``api/v1/memory.py`` DELETE 路由的裸 SQL 下沉到仓储层。
        """
        return self._repository.delete_memory(
            user_id=user_id, memory_type=memory_type, memory_id=memory_id
        )


class SessionMemory:
    def refresh_summary(self, session: Session) -> None:
        turns = session.recent_messages(8)
        if not turns:
            session.summary = ""
            return
        session.summary = " | ".join(f"{t.role}:{t.content[:80]}" for t in turns[-4:])
