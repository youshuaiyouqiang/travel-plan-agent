"""Claw7 API 服务器入口。

本文件仅负责：
1. 创建 FastAPI 应用实例
2. 注册生命周期钩子
3. 挂载中间件和全局异常处理器
4. 挂载 API v1 路由

所有路由逻辑已拆分至 ``api/v1/`` 目录。
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.v1 import router as v1_router
from api.middleware.auth import auth_middleware, rate_limit_middleware
from api.middleware.error_handler import claw_exception_handler, unhandled_exception_handler
from application.exceptions.base import ClawException
from application.trending.manager import refresh_pool
from app import build_orchestrator
from config import settings
from domain.shared.runtime.logging import init_from_settings

init_from_settings()
logger = logging.getLogger(__name__)

_BACKGROUND_TASK: asyncio.Task | None = None
_MEMORY_TASK: asyncio.Task | None = None
_POOL_REFRESH_INTERVAL = 1800


# ── 后台任务 ──────────────────────────────────────────────


async def _periodic_refresh_pool() -> None:
    """定期刷新热搜池。"""
    while True:
        try:
            await asyncio.sleep(_POOL_REFRESH_INTERVAL)
            logger.info("Periodic trending pool refresh starting")
            count = await refresh_pool()
            logger.info("Periodic trending pool refresh done: %d items", count)
        except asyncio.CancelledError:
            logger.info("Periodic trending pool refresh cancelled")
            break
        except Exception as e:
            logger.error("Periodic trending pool refresh error: %s", e)


async def _periodic_memory_maintenance() -> None:
    """记忆维护后台任务（蒸馏 + 衰减）。"""
    from application.scheduler import run_memory_maintenance
    await run_memory_maintenance()


# ── 生命周期 ──────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _BACKGROUND_TASK, _MEMORY_TASK
    logger.info("Server starting: warming up trending pool")
    try:
        count = await refresh_pool()
        logger.info("Trending pool warmup done: %d items", count)
    except Exception as e:
        logger.warning("Trending pool warmup failed: %s", e)
    _BACKGROUND_TASK = asyncio.create_task(_periodic_refresh_pool())
    _MEMORY_TASK = asyncio.create_task(_periodic_memory_maintenance())
    yield
    for task in (_BACKGROUND_TASK, _MEMORY_TASK):
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


# ── 应用创建 ──────────────────────────────────────────────


app = FastAPI(title="Claw7 API", version="1.0.0", lifespan=lifespan, redirect_slashes=False)

# 初始化编排器，存储到 app.state 供路由使用
_container = build_orchestrator()
app.state.agent = _container.orchestrator
app.state.skill_provider = _container.skill_provider
app.state.builtin_configs = _container.builtin_configs
app.state.custom_repo = _container.custom_repo
app.state.mcp_runtime = _container.mcp_runtime
app.state.mcp_catalog = _container.mcp_catalog

# ── CORS ──────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins if hasattr(settings, "cors_origins") else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 中间件 ────────────────────────────────────────────────

app.middleware("http")(auth_middleware)
app.middleware("http")(rate_limit_middleware)

# ── 全局异常处理器 ─────────────────────────────────────────

app.add_exception_handler(ClawException, claw_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# ── 路由挂载 ──────────────────────────────────────────────

# 新版 API（/api/v1/...）
app.include_router(v1_router, prefix="/api/v1")

# 向后兼容：旧路由前缀 /api/... 直接复用 v1 路由
# 前端当前请求 /api/auth/register 等，此挂载保证无缝迁移
app.include_router(v1_router, prefix="/api")
