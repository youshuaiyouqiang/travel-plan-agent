"""API v1 路由聚合。

所有子模块路由在此汇总，由 server.py 通过 ``app.include_router(v1_router, prefix="/api/v1")`` 挂载。
同时保留旧路由前缀的 301 重定向，确保前端不中断。
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from api.v1.auth import router as auth_router
from api.v1.chat import router as chat_router
from api.v1.session import router as session_router
from api.v1.session import confirm_router as session_confirm_router
from api.v1.agent import router as agent_router
from api.v1.skill import router as skill_router
from api.v1.mcp import router as mcp_router
from api.v1.itinerary import router as itinerary_router
from api.v1.album import router as album_router
from api.v1.album import album_serve_router
from api.v1.memory import router as memory_router
from api.v1.news import router as news_router
from api.v1.geocode import router as geocode_router
from api.v1.share import router as share_router
from api.v1.debug import router as debug_router
from api.v1.health import router as health_router
from api.v1.feedback import router as feedback_router

router = APIRouter()

# ── 按资源挂载子路由 ──
router.include_router(auth_router, prefix="/auth", tags=["认证"])
router.include_router(chat_router, prefix="/chat", tags=["对话"])
router.include_router(session_router, prefix="/sessions", tags=["会话"])
router.include_router(session_confirm_router, prefix="/session", tags=["方案确认"])
router.include_router(agent_router, prefix="/agents", tags=["智能体"])
router.include_router(skill_router, prefix="/skills", tags=["技能"])
router.include_router(mcp_router, prefix="/mcp/servers", tags=["MCP"])
router.include_router(itinerary_router, prefix="/itineraries", tags=["行程"])
router.include_router(album_router, prefix="/itineraries", tags=["相册"])
router.include_router(album_serve_router, prefix="/album", tags=["相册文件"])
router.include_router(memory_router, prefix="/memories", tags=["记忆"])
router.include_router(news_router, tags=["热搜/新闻"])
router.include_router(geocode_router, prefix="/geocode", tags=["地理编码"])
router.include_router(share_router, prefix="/shared", tags=["分享"])
router.include_router(debug_router, prefix="/debug", tags=["调试"])
router.include_router(health_router, tags=["健康检查"])
router.include_router(feedback_router, prefix="/feedback", tags=["反馈"])


# ── 旧路由 → /api/v1/ 的 301 重定向 ──
# 前端当前请求 /api/auth/register 等旧路径，此映射保证兼容性。
_LEGACY_REDIRECTS: dict[str, str] = {
    "/api/auth/register": "/api/v1/auth/register",
    "/api/auth/login": "/api/v1/auth/login",
    "/api/chat": "/api/v1/chat",
    "/api/chat/stream": "/api/v1/chat/stream",
    "/api/sessions": "/api/v1/sessions",
    "/api/skills": "/api/v1/skills",
    "/api/agents": "/api/v1/agents",
    "/api/memories": "/api/v1/memories",
    "/api/trending": "/api/v1/trending",
    "/api/feedback": "/api/v1/feedback",
    "/api/itineraries": "/api/v1/itineraries",
    "/api/news/favorites": "/api/v1/news/favorites",
    "/api/mcp/servers": "/api/v1/mcp/servers",
    "/api/geocode": "/api/v1/geocode",
    "/health": "/api/v1/health",
    "/metrics": "/api/v1/metrics",
}

# 需要前缀匹配的旧路由
_LEGACY_PREFIX_REDIRECTS: list[tuple[str, str]] = [
    ("/api/session/", "/api/v1/session/"),
    ("/api/sessions/", "/api/v1/sessions/"),
    ("/api/agents/", "/api/v1/agents/"),
    ("/api/skills/", "/api/v1/skills/"),
    ("/api/mcp/servers/", "/api/v1/mcp/servers/"),
    ("/api/itineraries/", "/api/v1/itineraries/"),
    ("/api/memories/", "/api/v1/memories/"),
    ("/api/news/favorites/", "/api/v1/news/favorites/"),
    ("/api/shared/", "/api/v1/shared/"),
    ("/api/geocode/", "/api/v1/geocode/"),
    ("/api/album/", "/api/v1/album/"),
    ("/debug/", "/api/v1/debug/"),
]


def create_legacy_redirect_router() -> APIRouter:
    """为旧路由创建 301 重定向路由器。"""
    redirect_router = APIRouter()

    @redirect_router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    async def legacy_redirect(request: Request, path: str):
        full_path = f"/{path}" if path else str(request.url.path)
        # 精确匹配
        if full_path in _LEGACY_REDIRECTS:
            return RedirectResponse(
                url=_LEGACY_REDIRECTS[full_path],
                status_code=301,
            )
        # 前缀匹配
        for old_prefix, new_prefix in _LEGACY_PREFIX_REDIRECTS:
            if full_path.startswith(old_prefix):
                new_path = new_prefix + full_path[len(old_prefix):]
                return RedirectResponse(url=new_path, status_code=301)
        # 无匹配，继续正常路由
        return None

    return redirect_router
