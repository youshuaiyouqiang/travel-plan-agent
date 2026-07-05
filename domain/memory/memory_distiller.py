from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from config import settings
from infrastructure.llm.openai import OpenAILLM
from infrastructure.persistence.database import get_connection, _json_dumps, _json_loads

logger = logging.getLogger(__name__)

_DISTILL_SYSTEM_PROMPT = """\
你是一个记忆精炼器。将以下短期记忆压缩为更精炼的长期记忆。

规则：
1. 长期记忆每条不超过30字，只保留最核心的信息
2. 去除上下文依赖的表述，使其独立可理解
3. 合并同类记忆（如"喜欢吃辣"和"偏好川菜"合并为"偏好川菜"）
4. 保持原始分类不变（preference/fact/experience）
5. experience 类型保持 experience_tag 不变

输入格式：JSON数组
输出格式：JSON数组，每项包含 category, content, experience_tag
"""


class MemoryDistiller:
    def __init__(self, llm: OpenAILLM | None = None) -> None:
        self._llm = llm

    def run_distillation(self, user_id: str) -> int:
        candidates = self._find_candidates(user_id)
        if not candidates:
            return 0

        distilled_count = 0
        conn = get_connection()
        now = datetime.utcnow().isoformat()

        for stm in candidates:
            existing_ltm = conn.execute(
                "SELECT id FROM long_term_memories "
                "WHERE user_id = ? AND category = ? AND content = ? AND status = 'active' LIMIT 1",
                (user_id, stm["category"], stm["content"]),
            ).fetchone()

            if existing_ltm:
                conn.execute(
                    "UPDATE long_term_memories SET extraction_count = extraction_count + 1, "
                    "last_accessed_at = ?, updated_at = ? WHERE id = ?",
                    (now, now, existing_ltm["id"]),
                )
                conn.execute(
                    "DELETE FROM short_term_memories WHERE id = ?",
                    (stm["id"],),
                )
                distilled_count += 1
                continue

            source_ids = _json_loads(stm.get("source_ids", "[]"), default=[])
            if not source_ids:
                source_ids = [stm["id"]]

            content = stm["content"]
            if self._llm and len(content) > 30:
                content = self._compress_content(content, stm["category"])

            conn.execute(
                "INSERT INTO long_term_memories "
                "(user_id, category, content, source_ids, experience_tag, extraction_count, "
                "last_accessed_at, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)",
                (
                    user_id,
                    stm["category"],
                    content,
                    _json_dumps(source_ids),
                    stm.get("experience_tag", ""),
                    stm["extraction_count"],
                    stm["last_accessed_at"] or now,
                    now,
                    now,
                ),
            )
            conn.execute(
                "DELETE FROM short_term_memories WHERE id = ?",
                (stm["id"],),
            )
            distilled_count += 1
            logger.info(
                "Memory distilled: user=%s category=%s content=%s",
                user_id,
                stm["category"],
                content[:30],
            )

        conn.commit()
        return distilled_count

    def run_decay(self, user_id: str | None = None) -> int:
        conn = get_connection()
        now = datetime.utcnow()
        decayed = 0

        stale_days = getattr(settings, "memory_stale_days", 90)
        deprecated_days = stale_days + 30
        stm_expire_days = getattr(settings, "memory_stm_expire_days", 30)

        if user_id:
            user_filter = "WHERE user_id = ?"
            params: list[Any] = [user_id]
        else:
            user_filter = ""
            params = []

        rows = conn.execute(
            f"SELECT id, last_accessed_at, status FROM long_term_memories {user_filter}",
            params,
        ).fetchall()

        for row in rows:
            if not row["last_accessed_at"]:
                continue
            try:
                last = datetime.fromisoformat(row["last_accessed_at"])
            except (ValueError, TypeError):
                continue

            days_idle = (now - last).days

            if row["status"] == "active" and days_idle > stale_days:
                conn.execute(
                    "UPDATE long_term_memories SET status = 'stale', updated_at = ? WHERE id = ?",
                    (now.isoformat(), row["id"]),
                )
                decayed += 1
            elif row["status"] == "stale" and days_idle > deprecated_days:
                conn.execute(
                    "UPDATE long_term_memories SET status = 'deprecated', updated_at = ? WHERE id = ?",
                    (now.isoformat(), row["id"]),
                )
                decayed += 1

        stm_rows = conn.execute(
            f"SELECT id, extraction_count, last_accessed_at FROM short_term_memories {user_filter}",
            params,
        ).fetchall()

        for row in stm_rows:
            if not row["last_accessed_at"]:
                continue
            try:
                last = datetime.fromisoformat(row["last_accessed_at"])
            except (ValueError, TypeError):
                continue

            days_idle = (now - last).days
            if days_idle > stm_expire_days and row["extraction_count"] < 2:
                conn.execute("DELETE FROM short_term_memories WHERE id = ?", (row["id"],))
                decayed += 1

        conn.commit()
        if decayed > 0:
            logger.info("Memory decay: user=%s decayed=%d", user_id or "all", decayed)
        return decayed

    def _find_candidates(self, user_id: str) -> list[dict]:
        conn = get_connection()
        min_extractions = getattr(settings, "memory_distill_threshold", 3)
        min_conversations = getattr(settings, "memory_distill_min_convs", 2)

        rows = conn.execute(
            "SELECT stm.id, stm.user_id, stm.category, stm.content, "
            "stm.experience_tag, stm.extraction_count, stm.last_accessed_at "
            "FROM short_term_memories stm "
            "WHERE stm.user_id = ? AND stm.extraction_count >= ?",
            (user_id, min_extractions),
        ).fetchall()

        candidates = []
        for row in rows:
            conv_rows = conn.execute(
                "SELECT DISTINCT c.id FROM memory_extractions me "
                "JOIN conversations c ON me.conversation_id = c.id "
                "WHERE me.memory_type = 'short_term' AND me.memory_id = ?",
                (row["id"],),
            ).fetchall()
            distinct_conv_ids = set(r["id"] for r in conv_rows)

            if len(distinct_conv_ids) >= min_conversations:
                days_since_access = 9999
                if row["last_accessed_at"]:
                    try:
                        days_since_access = (datetime.utcnow() - datetime.fromisoformat(row["last_accessed_at"])).days
                    except (ValueError, TypeError):
                        pass

                if days_since_access <= 30:
                    candidates.append(dict(row))

        return candidates

    def _compress_content(self, content: str, category: str) -> str:
        """P1-3 修复：原实现用 loop.is_running() 短路，导致在 FastAPI 异步上下文中
        永远走 fallback content[:30]，LLM 压缩根本不会执行。

        新方案：用 asyncio.run() 在独立事件循环中调用 LLM。
        前提：调用方（_post_chat_memory_processing / scheduler）需通过 asyncio.to_thread()
        在独立线程中调用 run_distillation，从而避免 "asyncio.run() cannot be called
        from a running event loop" 错误。
        """
        if not self._llm:
            return content[:30]

        try:
            import asyncio

            # asyncio.run() 创建独立事件循环；调用方必须在独立线程中调用 run_distillation
            result = asyncio.run(
                self._llm.complete_json(
                    system=_DISTILL_SYSTEM_PROMPT,
                    user=json.dumps([{"category": category, "content": content}], ensure_ascii=False),
                )
            )
            if isinstance(result, list) and result:
                item = result[0]
                if isinstance(item, dict) and item.get("content"):
                    return str(item["content"])[:30]
        except RuntimeError:
            # 在已有事件循环的线程中被调用 — 回退到截断（保持向后兼容）
            logger.debug("Memory compression skipped: running within event loop")
        except Exception:
            logger.warning("Memory compression failed", exc_info=True)

        return content[:30]
