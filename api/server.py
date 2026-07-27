from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.v1 import router as v1_router
from api.middleware.auth import auth_middleware, rate_limit_middleware
from api.middleware.error_handler import yunhe_exception_handler, unhandled_exception_handler
from application.exceptions.base import YunheException
from application.trending.manager import refresh_pool
from app import AppContainer, build_orchestrator, resolve_admin_user_id
from config import settings

"""Yunhe API 服务器入口。

本文件仅负责：
1. 创建 FastAPI 应用实例（``create_api`` 工厂，接收容器）
2. 注册生命周期钩子
3. 挂载中间件和全局异常处理器
4. 挂载 API v1 路由

所有路由逻辑已拆分至 ``api/v1/`` 目录。
"""

# P3.2：``init_from_settings`` 已在 ``build_orchestrator()`` 内部调用，
# 不再在模块级重复初始化，消除 import-time 副作用。
logger = logging.getLogger(__name__)

_BACKGROUND_TASK: asyncio.Task | None = None
_MEMORY_TASK: asyncio.Task | None = None
_HOTSPOT_REFRESH_TASK: asyncio.Task | None = None
_HOTSPOT_CLEANUP_TASK: asyncio.Task | None = None
_POOL_REFRESH_INTERVAL = 1800

# P3.1：``resolve_admin_user_id`` 已迁移到 ``app.py`` 组合根，此处保留
# re-export 供 ``tests/integration/test_admin_failfast.py`` 等历史导入兼容。
__all__ = ["resolve_admin_user_id", "app", "create_api"]


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


async def _periodic_hotspot_refresh() -> None:
    """热点池增量刷新后台任务（每 15 分钟）。"""
    from application.scheduler import run_hotspot_refresh

    await run_hotspot_refresh()


async def _periodic_hotspot_cleanup() -> None:
    """热点池清理/重聚类后台任务（每 6 小时，占位）。"""
    from application.scheduler import run_hotspot_cleanup

    await run_hotspot_cleanup()


# ── 生命周期 ──────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _BACKGROUND_TASK, _MEMORY_TASK, _HOTSPOT_REFRESH_TASK, _HOTSPOT_CLEANUP_TASK
    logger.info("Server starting: warming up trending pool")
    try:
        count = await refresh_pool()
        logger.info("Trending pool warmup done: %d items", count)
    except Exception as e:
        logger.warning("Trending pool warmup failed: %s", e)
    # Task 1（新闻治理）：启动期 idempotent 注册内置白名单。
    # 不抛异常：与 hotspot warmup 行为一致；管理员可手动 POST /admin/news/sources/register-builtin 补救。
    try:
        from application.news.source_service import (
            BUILTIN_WHITELIST,
            SourceService,
        )

        service = SourceService()
        for domain, name, tier in BUILTIN_WHITELIST:
            service.register_builtin_whitelist(domain=domain, name=name, tier=tier)
        logger.info("Built-in whitelist seeded: %d sources", len(BUILTIN_WHITELIST))
    except Exception as e:
        logger.warning("Built-in whitelist seed failed: %s", e)
    _BACKGROUND_TASK = asyncio.create_task(_periodic_refresh_pool())
    _MEMORY_TASK = asyncio.create_task(_periodic_memory_maintenance())
    _HOTSPOT_REFRESH_TASK = asyncio.create_task(_periodic_hotspot_refresh())
    _HOTSPOT_CLEANUP_TASK = asyncio.create_task(_periodic_hotspot_cleanup())
    yield
    for task in (
        _BACKGROUND_TASK,
        _MEMORY_TASK,
        _HOTSPOT_REFRESH_TASK,
        _HOTSPOT_CLEANUP_TASK,
    ):
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


# ── 应用创建 ──────────────────────────────────────────────


def create_api(container: AppContainer) -> FastAPI:
    """创建 FastAPI 应用并把容器字段绑定到 ``app.state`` 供路由读取。

    P3.2：app 创建逻辑工厂化，测试可注入替身容器；模块级 ``app`` 保留
    供 uvicorn 与历史 ``from api.server import app`` 导入兼容。
    """
    app = FastAPI(title="Yunhe API", version="1.0.0", lifespan=lifespan, redirect_slashes=False)

    # 组合根已在 ``build_orchestrator()`` 中构造全部应用服务；
    # 此处只做 ``app.state`` 绑定，不构造任何服务。
    app.state.container = container
    app.state.agent = container.orchestrator
    app.state.skill_provider = container.skill_provider
    app.state.builtin_configs = container.builtin_configs
    app.state.custom_repo = container.custom_repo
    app.state.mcp_runtime = container.mcp_runtime
    app.state.mcp_catalog = container.mcp_catalog
    app.state.session_service = container.session_service
    app.state.authz_service = container.authz_service
    app.state.hotspot_service = container.hotspot_service
    app.state.news_analysis_service = container.news_analysis_service
    app.state.admin_user_id = container.admin_user_id
    # P7：限流器从组合根注入；中间件不再直接 import infrastructure
    app.state.rate_limiter = container.rate_limiter
    # P7：健康检查从组合根注入；路由不再直接 import infrastructure
    app.state.health_checker = container.health_checker

    # ── CORS ──────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins if hasattr(settings, "cors_origins") else ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── 中间件 ────────────────────────────────────────────
    app.middleware("http")(auth_middleware)
    app.middleware("http")(rate_limit_middleware)

    # ── 全局异常处理器 ─────────────────────────────────────
    # Starlette 期望异常处理器签名为 (Request, Exception)；此处 yunhe_exception_handler
    # 接受更窄的 YunheException，运行时仅注册到 YunheException 路由上，
    # 类型不匹配是 Starlette 类型契约的已知限制。
    app.add_exception_handler(YunheException, yunhe_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # ── 路由挂载 ──────────────────────────────────────────
    # 新版 API（/api/v1/...）
    app.include_router(v1_router, prefix="/api/v1")
    # 向后兼容：旧路由前缀 /api/... 直接复用 v1 路由
    # 前端当前请求 /api/auth/register 等，此挂载保证无缝迁移
    app.include_router(v1_router, prefix="/api")

    return app


# 模块级默认实例：组合根组装容器后创建应用，供 uvicorn 与历史导入兼容。
app = create_api(build_orchestrator())
