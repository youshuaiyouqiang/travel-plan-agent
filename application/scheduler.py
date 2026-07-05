"""P1-3：记忆维护后台调度器。

每小时执行一次：
1. 逐用户蒸馏（确保用户间记忆隔离，避免 TypeError 与跨用户污染）
2. 全量衰减（run_decay 内部按 user_id 分组处理）

关键设计：
- `run_distillation(user_id: str)` 的参数是必填 str，不支持 None
- 蒸馏必须在独立线程中执行（via asyncio.to_thread），让 _compress_content
  内部的 asyncio.run() 能正常工作
- 使用 lifespan 上下文管理器注册，不使用废弃的 @app.on_event("startup")
"""

from __future__ import annotations

import asyncio
import logging

from config import settings
from domain.memory.memory_distiller import MemoryDistiller
from infrastructure.llm.openai import OpenAILLM
from infrastructure.persistence.database import get_connection

logger = logging.getLogger(__name__)

# 蒸馏循环间隔（秒）
_DISTILL_INTERVAL = 3600  # 1 小时


async def run_memory_maintenance() -> None:
    """后台任务：逐用户蒸馏 + 衰减。

    每小时跑一次。第一次启动延迟 60 秒，避免与 lifespan warmup 抢资源。
    """
    await asyncio.sleep(60)

    while True:
        try:
            # 每次循环都新建 distiller（LLM 配置可能在运行时被改）
            llm = OpenAILLM(
                api_key=settings.api_key,
                base_url=settings.base_url or "",
                model=settings.model,
            )
            distiller = MemoryDistiller(llm=llm)

            # 1. 枚举所有有短期记忆的用户，逐个蒸馏（确保隔离）
            conn = get_connection()
            user_rows = conn.execute("SELECT DISTINCT user_id FROM short_term_memories WHERE user_id != ''").fetchall()
            conn.close()

            total_distilled = 0
            for row in user_rows:
                uid = row["user_id"]
                try:
                    # 在独立线程中调用 sync run_distillation，
                    # 让 _compress_content 内的 asyncio.run() 正常工作
                    distilled = await asyncio.to_thread(distiller.run_distillation, uid)
                    if distilled > 0:
                        logger.info("Memory distilled: user=%s count=%d", uid, distilled)
                    total_distilled += distilled
                except Exception:
                    logger.warning("Distillation failed for user=%s", uid, exc_info=True)

            # 2. 全量衰减（run_decay 支持 user_id=None，内部按 user_id 分组）
            try:
                decayed = await asyncio.to_thread(distiller.run_decay, None)
                if decayed > 0:
                    logger.info("Memory decay: total=%d", decayed)
            except Exception:
                logger.warning("Memory decay failed", exc_info=True)

            logger.info(
                "Memory maintenance cycle done: users=%d distilled=%d",
                len(user_rows),
                total_distilled,
            )
        except Exception:
            logger.warning("Memory maintenance cycle failed", exc_info=True)

        await asyncio.sleep(_DISTILL_INTERVAL)
