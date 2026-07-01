from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from config import settings
from domain.user.session.manager import Session
from infrastructure.persistence.database import get_connection

logger = logging.getLogger(__name__)


@dataclass
class MemoryRecord:
    text: str
    source: str
    scope_id: str = "default"
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


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


class MemoryManager:
    def __init__(self) -> None:
        self._cache: dict[str, list[MemoryRecord]] = {}

    @staticmethod
    def _normalize_scope_id(scope_id: str | None) -> str:
        clean = str(scope_id or "").strip()
        return clean or "default"

    def remember(
        self,
        text: str,
        *,
        source: str = "conversation",
        scope_id: str | None = None,
    ) -> None:
        clean = text.strip()
        if not clean:
            return
        norm_scope = self._normalize_scope_id(scope_id)
        conn = get_connection()
        existing = conn.execute(
            "SELECT id FROM memories WHERE scope_id = ? AND text = ? LIMIT 1",
            (norm_scope, clean),
        ).fetchone()
        if existing:
            logger.debug("Memory skip duplicate: %s", clean[:80])
            return
        now = datetime.utcnow().isoformat()
        conn.execute(
            "INSERT INTO memories (scope_id, text, source, created_at) VALUES (?, ?, ?, ?)",
            (norm_scope, clean, source, now),
        )
        conn.commit()
        bucket = self._cache.setdefault(norm_scope, [])
        bucket.append(MemoryRecord(text=clean, source=source, scope_id=norm_scope, created_at=now))
        logger.info("Memory stored: source=%s scope_id=%s", source, norm_scope)

    def search(
        self,
        query: str,
        limit: int | None = None,
        *,
        scope_id: str | None = None,
    ) -> list[MemoryRecord]:
        norm_scope = self._normalize_scope_id(scope_id)
        max_items = limit or settings.max_memory_items
        clean = query.strip().lower()
        if not clean:
            return self._get_recent(norm_scope, max_items)
        terms = [token for token in clean.replace("\n", " ").split() if token]
        if not terms:
            return self._get_recent(norm_scope, max_items)
        conn = get_connection()
        rows = conn.execute(
            "SELECT text, source, scope_id, created_at FROM memories WHERE scope_id = ?",
            (norm_scope,),
        ).fetchall()
        scored: list[tuple[int, MemoryRecord]] = []
        for row in rows:
            hay = row["text"].lower()
            score = sum(1 for term in terms if term in hay)
            if score > 0:
                scored.append((score, MemoryRecord(
                    text=row["text"],
                    source=row["source"],
                    scope_id=row["scope_id"],
                    created_at=row["created_at"],
                )))
        scored.sort(key=lambda r: (r[0], r[1].created_at), reverse=True)
        return [item for _, item in scored[:max_items]]

    def build_context(self, query: str, *, scope_id: str | None = None) -> str:
        items = self.search(query, scope_id=scope_id)
        if not items:
            return ""
        logger.debug("Memory context built: matches=%s", len(items))
        return "\n".join(f"- {item.text}" for item in items)

    def list_recent(
        self,
        limit: int | None = None,
        *,
        scope_id: str | None = None,
    ) -> list[MemoryRecord]:
        max_items = limit or settings.max_memory_items
        norm_scope = self._normalize_scope_id(scope_id)
        return self._get_recent(norm_scope, max_items)

    def maybe_learn_from_message(self, message: str, *, scope_id: str | None = None) -> None:
        clean = message.strip()
        if not clean:
            return
        lowered = clean.lower()
        triggers = (
            "i like ", "i prefer ", "my name is ", "remember that ",
            "我叫", "我喜欢", "请记住", "记住",
        )
        if any(trigger in lowered for trigger in triggers) or any(
            marker in clean for marker in ("我叫", "我喜欢", "请记住", "记住")
        ):
            logger.debug("Memory learning trigger matched")
            self.remember(clean, source="user", scope_id=scope_id)

    def _get_recent(self, scope_id: str, limit: int) -> list[MemoryRecord]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT text, source, scope_id, created_at FROM memories WHERE scope_id = ? ORDER BY id DESC LIMIT ?",
            (scope_id, limit),
        ).fetchall()
        results = []
        for row in reversed(rows):
            results.append(MemoryRecord(
                text=row["text"],
                source=row["source"],
                scope_id=row["scope_id"],
                created_at=row["created_at"],
            ))
        return results


class DualLayerMemoryManager:
    def __init__(self) -> None:
        self._legacy = MemoryManager()

    def get_long_term_memories(self, user_id: str) -> list[LongTermMemory]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, user_id, category, content, source_ids, experience_tag, extraction_count, "
            "last_accessed_at, status, created_at, updated_at "
            "FROM long_term_memories WHERE user_id = ? AND status = 'active' "
            "ORDER BY last_accessed_at DESC, updated_at DESC",
            (user_id,),
        ).fetchall()
        from infra.db import _json_loads
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

    def get_short_term_memories(
        self,
        user_id: str,
        *,
        query: str = "",
        limit: int | None = None,
    ) -> list[ShortTermMemory]:
        max_items = limit or 20
        conn = get_connection()

        if query.strip():
            terms = [t for t in query.strip().lower().split() if t]
            rows = conn.execute(
                "SELECT id, user_id, category, content, experience_tag, "
                "extraction_count, last_accessed_at, created_at "
                "FROM short_term_memories WHERE user_id = ?",
                (user_id,),
            ).fetchall()
            scored: list[tuple[int, dict]] = []
            for row in rows:
                hay = row["content"].lower()
                score = sum(1 for term in terms if term in hay)
                if score > 0:
                    scored.append((score, dict(row)))
            scored.sort(key=lambda r: (r[0], r[1].get("created_at", "")), reverse=True)
            top = [item for _, item in scored[:max_items]]
        else:
            rows = conn.execute(
                "SELECT id, user_id, category, content, experience_tag, "
                "extraction_count, last_accessed_at, created_at "
                "FROM short_term_memories WHERE user_id = ? "
                "ORDER BY id DESC LIMIT ?",
                (user_id, max_items),
            ).fetchall()
            top = [dict(row) for row in reversed(rows)]

        return [
            ShortTermMemory(
                id=r["id"],
                user_id=r["user_id"],
                category=r["category"],
                content=r["content"],
                experience_tag=r["experience_tag"],
                extraction_count=r["extraction_count"],
                last_accessed_at=r["last_accessed_at"],
                created_at=r["created_at"],
            )
            for r in top
        ]

    def build_full_context(self, user_id: str, *, query: str = "") -> str:
        parts: list[str] = []
        now = datetime.utcnow().isoformat()

        ltm_list = self.get_long_term_memories(user_id)
        if ltm_list:
            conn = get_connection()
            ltm_ids = [m.id for m in ltm_list]
            conn.execute(
                f"UPDATE long_term_memories SET last_accessed_at = ? WHERE id IN ({','.join('?' * len(ltm_ids))})",
                (now, *ltm_ids),
            )
            conn.commit()

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
            conn = get_connection()
            stm_ids = [m.id for m in stm_list]
            conn.execute(
                f"UPDATE short_term_memories SET last_accessed_at = ? WHERE id IN ({','.join('?' * len(stm_ids))})",
                (now, *stm_ids),
            )
            conn.commit()

            category_labels = {"preference": "偏好", "fact": "事实", "experience": "经验"}
            stm_lines: list[str] = []
            for mem in stm_list:
                label = category_labels.get(mem.category, mem.category)
                text = mem.content
                if mem.category == "experience" and mem.experience_tag:
                    tag_label = "✓" if mem.experience_tag == "success" else "✗"
                    text = f"[{tag_label}] {text}"
                if mem.category == "fact":
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
        conn = get_connection()
        now = datetime.utcnow().isoformat()
        conn.execute(
            "INSERT INTO memory_extractions (conversation_id, memory_type, memory_id, relevance, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (conversation_id, memory_type, memory_id, relevance, now),
        )

        table = "short_term_memories" if memory_type == "short_term" else "long_term_memories"
        conn.execute(
            f"UPDATE {table} SET extraction_count = extraction_count + 1, last_accessed_at = ? WHERE id = ?",
            (now, memory_id),
        )
        conn.commit()

    def save_conversation(
        self,
        session_id: str,
        user_id: str,
        summary: str = "",
    ) -> int:
        conn = get_connection()
        now = datetime.utcnow().isoformat()
        cursor = conn.execute(
            "INSERT INTO conversations (session_id, user_id, summary, created_at) VALUES (?, ?, ?, ?)",
            (session_id, user_id, summary[:200], now),
        )
        conn.commit()
        return cursor.lastrowid

    def remember(self, text: str, *, source: str = "conversation", scope_id: str | None = None) -> None:
        self._legacy.remember(text, source=source, scope_id=scope_id)

    def search(self, query: str, limit: int | None = None, *, scope_id: str | None = None) -> list[MemoryRecord]:
        return self._legacy.search(query, limit=limit, scope_id=scope_id)

    def build_context(self, query: str, *, scope_id: str | None = None) -> str:
        return self._legacy.build_context(query, scope_id=scope_id)

    def list_recent(self, limit: int | None = None, *, scope_id: str | None = None) -> list[MemoryRecord]:
        return self._legacy.list_recent(limit=limit, scope_id=scope_id)

    def maybe_learn_from_message(self, message: str, *, scope_id: str | None = None) -> None:
        self._legacy.maybe_learn_from_message(message, scope_id=scope_id)


class SessionMemory:
    def refresh_summary(self, session: Session) -> None:
        turns = session.recent_messages(8)
        if not turns:
            session.summary = ""
            return
        session.summary = " | ".join(f"{t.role}:{t.content[:80]}" for t in turns[-4:])
