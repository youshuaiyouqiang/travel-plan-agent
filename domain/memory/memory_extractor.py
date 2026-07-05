from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime

from infrastructure.llm.openai import OpenAILLM
from infrastructure.persistence.database import get_connection

logger = logging.getLogger(__name__)

_EXTRACT_SYSTEM_PROMPT = """\
你是一个记忆提取器。从用户与助手的对话中，提取值得长期记住的用户信息。

提取规则：
1. 积极提取，宁可多提不要遗漏
2. 每条记忆不超过50字，只保留核心信息
3. 分类为以下三种：
   - preference: 用户偏好（饮食偏好、出行方式、住宿偏好、节奏偏好、消费水平、景点类型偏好等）
   - fact: 用户事实信息（姓名、住址、职业、家庭成员、常去城市、出行人数、预算等）
   - experience: 用户经验（成功或失败的决策经历、踩坑经历、对景点/餐厅的评价等）
4. experience 类型的记忆必须标注 experience_tag：
   - success: 正面经验，值得复用
   - failure: 负面经验，需要避免
5. 以下信息也必须提取：
   - 用户提到的出行人数（如"两个人"、"带老人"→ fact）
   - 用户提到的预算范围（如"3000左右"、"不要太贵"→ fact）
   - 用户对景点类型的偏好（如"喜欢自然风光"、"不想去人多的地方"→ preference）
   - 用户对行程节奏的偏好（如"不要太赶"、"想轻松一点"→ preference）
   - 用户对住宿/交通的偏好（如"住市中心"、"不想自驾"→ preference）
   - 用户对之前旅行的评价（如"上次去XX觉得人太多"→ experience, failure）
6. 不要提取临时性信息（如"今天天气怎么样"这类问答）
7. 不要提取助手说的内容，只提取用户透露的信息

输出严格的JSON数组格式：
[{"category":"preference","content":"喜欢自然风光","experience_tag":""}]
[{"category":"fact","content":"两人出行预算5000","experience_tag":""}]
[{"category":"experience","content":"上次去三亚蜈支洲岛人太多","experience_tag":"failure"}]

如无记忆可提取，输出：[]
"""


@dataclass
class ExtractedMemory:
    category: str
    content: str
    experience_tag: str = ""


class MemoryExtractor:
    def __init__(self, llm: OpenAILLM) -> None:
        self._llm = llm

    async def extract(
        self,
        turns: list[dict[str, str]],
        *,
        user_id: str,
        session_id: str,
    ) -> list[ExtractedMemory]:
        if not turns:
            return []

        conversation_text = self._format_turns(turns)
        if len(conversation_text.strip()) < 10:
            return []

        try:
            result = await self._llm.complete_json(
                system=_EXTRACT_SYSTEM_PROMPT,
                user=conversation_text,
            )
        except Exception:
            logger.warning("Memory extraction LLM call failed", exc_info=True)
            return []

        if not isinstance(result, list):
            if isinstance(result, dict) and "memories" in result:
                result = result["memories"]
            else:
                return []

        extracted: list[ExtractedMemory] = []
        for item in result:
            if not isinstance(item, dict):
                continue
            category = str(item.get("category", "")).strip().lower()
            if category not in ("preference", "fact", "experience"):
                category = "fact"
            content = str(item.get("content", "")).strip()[:50]
            if not content:
                continue
            experience_tag = ""
            if category == "experience":
                experience_tag = str(item.get("experience_tag", "")).strip().lower()
                if experience_tag not in ("success", "failure"):
                    experience_tag = ""
            extracted.append(
                ExtractedMemory(
                    category=category,
                    content=content,
                    experience_tag=experience_tag,
                )
            )

        logger.info(
            "Memory extraction: session=%s user=%s extracted=%d",
            session_id,
            user_id,
            len(extracted),
        )
        return extracted

    def save_extracted(
        self,
        memories: list[ExtractedMemory],
        *,
        user_id: str,
        conversation_id: int,
    ) -> list[int]:
        if not memories:
            return []

        conn = get_connection()
        saved_ids: list[int] = []
        now = datetime.utcnow().isoformat()

        for mem in memories:
            existing = conn.execute(
                "SELECT id, extraction_count FROM short_term_memories "
                "WHERE user_id = ? AND category = ? AND content = ? LIMIT 1",
                (user_id, mem.category, mem.content),
            ).fetchone()

            if existing:
                conn.execute(
                    "UPDATE short_term_memories SET source_conv_id = ?, last_accessed_at = ? WHERE id = ?",
                    (conversation_id, now, existing["id"]),
                )
                saved_ids.append(existing["id"])
                logger.debug("Memory skip duplicate: %s", mem.content[:40])
            else:
                cursor = conn.execute(
                    "INSERT INTO short_term_memories "
                    "(user_id, category, content, source_conv_id, experience_tag, "
                    "extraction_count, last_accessed_at, created_at) "
                    "VALUES (?, ?, ?, ?, ?, 0, ?, ?)",
                    (user_id, mem.category, mem.content, conversation_id, mem.experience_tag, now, now),
                )
                saved_ids.append(cursor.lastrowid)

        conn.commit()
        return saved_ids

    def _format_turns(self, turns: list[dict[str, str]]) -> str:
        lines: list[str] = []
        for turn in turns[-20:]:
            role = turn.get("role", "")
            content = turn.get("content", "")
            if role and content:
                label = "用户" if role == "user" else "助手"
                lines.append(f"{label}: {content}")
        return "\n".join(lines)
