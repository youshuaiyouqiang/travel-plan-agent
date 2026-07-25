from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.v1 import router as v1_router
from api.middleware.auth import auth_middleware, rate_limit_middleware
from api.middleware.error_handler import yunhe_exception_handler, unhandled_exception_handler
from application.authz import AuthorizationService
from application.exceptions.base import YunheException
from application.session.service import SessionService
from application.trending.manager import refresh_pool
from app import build_orchestrator
from config import settings
from domain.shared.runtime.logging import init_from_settings

"""Yunhe API 服务器入口。

本文件仅负责：
1. 创建 FastAPI 应用实例
2. 注册生命周期钩子
3. 挂载中间件和全局异常处理器
4. 挂载 API v1 路由

所有路由逻辑已拆分至 ``api/v1/`` 目录。
"""

init_from_settings()
logger = logging.getLogger(__name__)

_BACKGROUND_TASK: asyncio.Task | None = None
_MEMORY_TASK: asyncio.Task | None = None
_HOTSPOT_REFRESH_TASK: asyncio.Task | None = None
_HOTSPOT_CLEANUP_TASK: asyncio.Task | None = None
_POOL_REFRESH_INTERVAL = 1800


# ── 启动期管理员解析 ────────────────────────────────────────


def resolve_admin_user_id() -> str | None:
    """启动期解析 ``YUNHE_ADMIN_USERNAME`` → ``admin_user_id``。

    P1-2 行为：
    - 生产环境（``settings.environment == "production"``）下，
      ``YUNHE_ADMIN_USERNAME`` 为空或对应用户不存在时必须 fail-fast
      抛 ``RuntimeError``，禁止静默降级到无管理员状态。
    - 开发环境允许缺失/找不到，仅记录 warning，返回 None。

    Returns:
        解析成功时返回 ``user_id``；开发环境未配置或找不到时返回 None。

    Raises:
        RuntimeError: 生产环境下管理员未配置或用户不存在。
    """
    from domain.user.auth.auth import UserStore

    username = settings.admin_username
    is_production = settings.environment == "production"

    if not username:
        if is_production:
            raise RuntimeError(
                "YUNHE_ADMIN_USERNAME is not configured; production deployments "
                "must define a system administrator before startup."
            )
        logger.info("YUNHE_ADMIN_USERNAME not configured; admin API disabled (development mode)")
        return None

    user = UserStore().get_by_username(username)
    if user is None:
        if is_production:
            raise RuntimeError(
                f"YUNHE_ADMIN_USERNAME={username!r} does not match any existing user; "
                "production deployments must reference a valid administrator account."
            )
        logger.warning(
            "YUNHE_ADMIN_USERNAME=%s 不存在对应用户；管理员 API 将不可用（开发模式降级）",
            username,
        )
        return None

    logger.info("Admin resolved: username=%s user_id=%s", username, user.user_id)
    return user.user_id


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


app = FastAPI(title="Yunhe API", version="1.0.0", lifespan=lifespan, redirect_slashes=False)

# 初始化编排器，存储到 app.state 供路由使用
_container = build_orchestrator()
app.state.agent = _container.orchestrator
app.state.skill_provider = _container.skill_provider
app.state.builtin_configs = _container.builtin_configs
app.state.custom_repo = _container.custom_repo
app.state.mcp_runtime = _container.mcp_runtime
app.state.mcp_catalog = _container.mcp_catalog
# Task 1: 会话模式应用服务。可锁定的 Agent 来自内置配置（排除调度员 yunhe）。
# news Agent 由新闻研判流程内部锁定（news_analysis_locked），不进入用户可选白名单。
_lockable_agent_ids = {
    c.id for c in _container.builtin_configs if c.id not in {"yunhe", "news"}
}
app.state.session_service = SessionService(available_agent_ids=_lockable_agent_ids)
# Task 2: 集中式对象级授权服务；复用同一 SessionService 保证会话所有权判定一致。
app.state.authz_service = AuthorizationService(session_service=app.state.session_service)
# Task 2: 注入生产用 HotspotService；路由通过 request.app.state.hotspot_service 取用。
# 测试通过覆盖此属性注入替身；未配置时 GET /hotspots 返回空列表。
from application.news.hotspot_service import get_default_service as _get_default_hotspot_service

app.state.hotspot_service = _get_default_hotspot_service()
# 新闻研判分析服务：调用 ``analyze`` 把证据按来源状态分类为 verified / conflicted
# / unverified_leads。当前生产默认使用空证据提供者（未接入真实证据通道），
# 后续可替换为 LLM 抽取或检索器实现。chat 端点在 news_analysis_locked 会话下
# 自动调用本服务取证并注入到 user message，让新闻 Agent 基于已注入上下文
# 直接产出研判（不再要求用户补充证据）。
from application.news.analysis_service import NewsAnalysisService
from application.news.empty_evidence_provider import EmptyEvidenceProvider
from application.news.source_service import SourceService

app.state.news_analysis_service = NewsAnalysisService(
    sources=SourceService(), evidence_provider=EmptyEvidenceProvider()
)
# 新闻来源治理：启动期解析 YUNHE_ADMIN_USERNAME → admin_user_id。
# P1-2: 生产环境（environment == "production"）下，YUNHE_ADMIN_USERNAME 缺失
# 或找不到对应用户时必须 fail-fast，禁止静默降级。
app.state.admin_user_id = resolve_admin_user_id()

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

# Starlette 期望异常处理器签名为 (Request, Exception)；此处 yunhe_exception_handler
# 接受更窄的 YunheException，运行时仅注册到 YunheException 路由上，
# 类型不匹配是 Starlette 类型契约的已知限制。
app.add_exception_handler(YunheException, yunhe_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(Exception, unhandled_exception_handler)

# ── 路由挂载 ──────────────────────────────────────────────

# 新版 API（/api/v1/...）
app.include_router(v1_router, prefix="/api/v1")

# 向后兼容：旧路由前缀 /api/... 直接复用 v1 路由
# 前端当前请求 /api/auth/register 等，此挂载保证无缝迁移
app.include_router(v1_router, prefix="/api")
