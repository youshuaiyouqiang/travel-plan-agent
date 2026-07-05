from __future__ import annotations

import asyncio
import logging
from typing import Any

from domain.memory.manager import DualLayerMemoryManager
from domain.memory.memory_extractor import MemoryExtractor
from domain.memory.memory_distiller import MemoryDistiller

logger = logging.getLogger(__name__)


class MemoryProcessor:
    def __init__(
        self,
        *,
        dual_memory: DualLayerMemoryManager,
        memory_extractor: MemoryExtractor,
        memory_distiller: MemoryDistiller,
    ) -> None:
        self._dual_memory = dual_memory
        self._memory_extractor = memory_extractor
        self._memory_distiller = memory_distiller

    async def process(
        self,
        session: Any,
        session_id: str,
        memory_scope: str,
        user_id: str | None,
    ) -> None:
        from config import settings as cfg
        if not cfg.memory_extraction_enabled:
            return
        if not user_id:
            return

        try:
            conv_id = self._dual_memory.save_conversation(
                session_id=session_id,
                user_id=user_id,
                summary=session.summary[:200] if session.summary else "",
            )

            turns_data = [{"role": t.role, "content": t.content} for t in session.turns]
            extracted = await self._memory_extractor.extract(
                turns_data,
                user_id=user_id,
                session_id=session_id,
            )

            if extracted:
                saved_ids = self._memory_extractor.save_extracted(
                    extracted,
                    user_id=user_id,
                    conversation_id=conv_id,
                )
                for mid in saved_ids:
                    self._dual_memory.record_extraction(
                        conversation_id=conv_id,
                        memory_type="short_term",
                        memory_id=mid,
                    )

            ltm_list = self._dual_memory.get_long_term_memories(user_id)
            for ltm in ltm_list:
                self._dual_memory.record_extraction(
                    conversation_id=conv_id,
                    memory_type="long_term",
                    memory_id=ltm.id,
                    relevance=0.5,
                )

            # P1-3：在独立线程中调用 sync distiller 方法，避免阻塞事件循环，
            # 同时让 _compress_content 内部的 asyncio.run() 能正常工作（线程内无运行中的 loop）
            distilled = await asyncio.to_thread(
                self._memory_distiller.run_distillation, user_id
            )
            if distilled > 0:
                logger.info("Memory distilled: user=%s count=%d", user_id, distilled)

            await asyncio.to_thread(self._memory_distiller.run_decay, user_id)

        except Exception:
            logger.warning("Post-chat memory processing failed", exc_info=True)
