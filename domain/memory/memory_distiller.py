from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from config import settings
from domain.memory.ports import MemoryRepositoryPort, get_default_memory_repository
from domain.shared.llm.ports import LLMPort

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
    def __init__(
        self,
        llm: LLMPort | None = None,
        repository: MemoryRepositoryPort | None = None,
    ) -> None:
        self._llm = llm
        self._repository = repository or get_default_memory_repository()

    def run_distillation(self, user_id: str) -> int:
        candidates = self._find_candidates(user_id)
        if not candidates:
            return 0

        distilled_count = 0
        now = datetime.utcnow().isoformat()

        for stm in candidates:
            existing_ltm_id = self._repository.find_existing_ltm_id(
                user_id, stm["category"], stm["content"]
            )

            if existing_ltm_id is not None:
                # 路径 A：同内容 LTM 已存在，递增 extraction_count 并删除源 STM（原子事务）
                self._repository.merge_stm_into_existing_ltm(stm["id"], existing_ltm_id, now)
                distilled_count += 1
                continue

            # 路径 B：新建 LTM 并删除源 STM（原子事务）
            source_ids = _parse_source_ids(stm.get("source_ids", "[]"))
            if not source_ids:
                source_ids = [stm["id"]]

            content = stm["content"]
            if self._llm and len(content) > 30:
                content = self._compress_content(content, stm["category"])

            self._repository.promote_stm_to_ltm(
                user_id=user_id,
                category=stm["category"],
                content=content,
                source_ids=source_ids,
                experience_tag=stm.get("experience_tag", ""),
                extraction_count=stm["extraction_count"],
                last_accessed_at=stm["last_accessed_at"] or now,
                stm_id=stm["id"],
                now=now,
            )
            distilled_count += 1
            logger.info(
                "Memory distilled: user=%s category=%s content=%s",
                user_id,
                stm["category"],
                content[:30],
            )

        return distilled_count

    def run_decay(self, user_id: str | None = None) -> int:
        now = datetime.utcnow()
        decayed = 0

        stale_days = getattr(settings, "memory_stale_days", 90)
        deprecated_days = stale_days + 30
        stm_expire_days = getattr(settings, "memory_stm_expire_days", 30)

        # ── LTM 衰减：active → stale → deprecated ──
        for row in self._repository.get_ltm_for_decay(user_id):
            if not row["last_accessed_at"]:
                continue
            try:
                last = datetime.fromisoformat(row["last_accessed_at"])
            except (ValueError, TypeError):
                continue

            days_idle = (now - last).days

            if row["status"] == "active" and days_idle > stale_days:
                self._repository.update_ltm_status(row["id"], "stale", now.isoformat())
                decayed += 1
            elif row["status"] == "stale" and days_idle > deprecated_days:
                self._repository.update_ltm_status(row["id"], "deprecated", now.isoformat())
                decayed += 1

        # ── STM 衰减：过期且低引用删除 ──
        for row in self._repository.get_stm_for_decay(user_id):
            if not row["last_accessed_at"]:
                continue
            try:
                last = datetime.fromisoformat(row["last_accessed_at"])
            except (ValueError, TypeError):
                continue

            days_idle = (now - last).days
            if days_idle > stm_expire_days and row["extraction_count"] < 2:
                self._repository.delete_short_term(row["id"])
                decayed += 1

        if decayed > 0:
            logger.info("Memory decay: user=%s decayed=%d", user_id or "all", decayed)
        return decayed

    def _find_candidates(self, user_id: str) -> list[dict[str, Any]]:
        min_extractions = getattr(settings, "memory_distill_threshold", 3)
        min_conversations = getattr(settings, "memory_distill_min_convs", 2)

        candidates: list[dict[str, Any]] = []
        for row in self._repository.get_stm_candidates(user_id, min_extractions):
            distinct_conv_ids = self._repository.get_distinct_conversation_ids_for_memory(row["id"])

            if len(distinct_conv_ids) >= min_conversations:
                days_since_access = 9999
                if row["last_accessed_at"]:
                    try:
                        days_since_access = (
                            datetime.utcnow() - datetime.fromisoformat(row["last_accessed_at"])
                        ).days
                    except (ValueError, TypeError):
                        pass

                if days_since_access <= 30:
                    candidates.append(row)

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


def _parse_source_ids(raw: str) -> list[int]:
    """解析 source_ids JSON 字符串为 int 列表；失败返回空列表。

    替代原 ``infrastructure.persistence.database._json_loads``，保持相同容错语义。
    """
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [int(x) for x in parsed]
    except (ValueError, TypeError):
        pass
    return []
