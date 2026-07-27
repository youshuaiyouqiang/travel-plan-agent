"""P1-3：记忆维护与热点池后台调度器。

记忆维护（每小时）：
1. 逐用户蒸馏（确保用户间记忆隔离，避免 TypeError 与跨用户污染）
2. 全量衰减（run_decay 内部按 user_id 分组处理）

热点刷新（每 15 分钟）：
- 调用 ``HotspotService.refresh`` 仅抓取 ``enabled`` 来源。
- 不抓取新闻全文；只更新元数据缓存。

热点清理（每 6 小时）：
- 当前为占位实现：仅记录日志。
- 后续若引入聚类/衰减策略，在此扩展，不破坏现有抓取流程。

关键设计：
- `run_distillation(user_id: str)` 的参数是必填 str，不支持 None
- 蒸馏必须在独立线程中执行（via asyncio.to_thread），让 _compress_content
  内部的 asyncio.run() 能正常工作
- 使用 lifespan 上下文管理器注册，不使用废弃的 @app.on_event("startup")
"""

from __future__ import annotations

import asyncio
import logging

from domain.memory.memory_distiller import MemoryDistiller
from domain.memory.ports import get_default_memory_repository
from domain.shared.llm.ports import get_default_llm

logger = logging.getLogger(__name__)

# 蒸馏循环间隔（秒）
_DISTILL_INTERVAL = 3600  # 1 小时

# 热点刷新间隔（秒）— Task 2：每 15 分钟增量刷新一次
_HOTSPOT_REFRESH_INTERVAL = 900  # 15 分钟

# 热点清理/重聚类间隔（秒）— Task 2：每 6 小时执行一次
_HOTSPOT_CLEANUP_INTERVAL = 6 * 3600  # 6 小时


async def run_memory_maintenance() -> None:
    """后台任务：逐用户蒸馏 + 衰减。

    每小时跑一次。第一次启动延迟 60 秒，避免与 lifespan warmup 抢资源。
    """
    await asyncio.sleep(60)

    while True:
        try:
            # P4.1：通过组合根注册的默认 LLM 端口构造 distiller，
            # 不再直接 ``OpenAILLM(...)`` 实例化（消除 application → infrastructure 依赖）。
            llm = get_default_llm()
            if llm is None:
                logger.warning("No default LLM configured; skip memory maintenance cycle")
                await asyncio.sleep(_DISTILL_INTERVAL)
                continue
            distiller = MemoryDistiller(llm=llm)

            # 1. 枚举所有有短期记忆的用户，逐个蒸馏（确保隔离）
            # P2.6：通过 MemoryRepositoryPort 枚举用户，不再直接查询数据库
            memory_repo = get_default_memory_repository()
            user_ids = memory_repo.list_user_ids_with_short_term_memories()

            total_distilled = 0
            for uid in user_ids:
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
                len(user_ids),
                total_distilled,
            )
        except Exception:
            logger.warning("Memory maintenance cycle failed", exc_info=True)

        await asyncio.sleep(_DISTILL_INTERVAL)


async def run_hotspot_refresh() -> None:
    """后台任务：每 15 分钟刷新热点池。

    - 仅抓取 ``enabled`` 来源；非 enabled 由 ``SourceService`` 过滤。
    - 不抓取新闻全文；只更新元数据缓存。
    - 首次启动延迟 30 秒，避免与 lifespan warmup 抢资源。
    """
    await asyncio.sleep(30)
    while True:
        try:
            from application.news.hotspot_service import get_default_service

            service = get_default_service()
            result = await service.refresh()
            logger.info(
                "Hotspot refresh cycle done: count=%d sources=%d",
                result.count,
                len(result.sources_used),
            )
        except Exception:
            logger.warning("Hotspot refresh cycle failed", exc_info=True)

        await asyncio.sleep(_HOTSPOT_REFRESH_INTERVAL)


async def run_hotspot_cleanup() -> None:
    """后台任务：每 6 小时执行一次热点清理/重聚类。

    当前为占位实现：仅记录日志。后续若引入聚类/衰减策略，在此扩展，
    不破坏现有抓取流程。首次启动延迟 5 分钟，避免与 warmup 抢资源。
    """
    await asyncio.sleep(300)
    while True:
        try:
            # 占位：当前热点池由 refresh 全量替换，无需额外清理。
            # 未来若引入聚类/衰减/过期清理，在此扩展。
            logger.info("Hotspot cleanup cycle: no-op (placeholder)")
        except Exception:
            logger.warning("Hotspot cleanup cycle failed", exc_info=True)

        await asyncio.sleep(_HOTSPOT_CLEANUP_INTERVAL)
