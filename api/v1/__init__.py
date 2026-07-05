from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from api.v1.auth import router as auth_router
from api.v1.agent import router as agent_router
from api.v1.album import album_serve_router
from api.v1.album import router as album_router
from api.v1.chat import router as chat_router
from api.v1.debug import router as debug_router
from api.v1.feedback import router as feedback_router
from api.v1.geocode import router as geocode_router
from api.v1.health import router as health_router
from api.v1.itinerary import router as itinerary_router
from api.v1.mcp import router as mcp_router
from api.v1.memory import router as memory_router
from api.v1.news import router as news_router
from api.v1.session import confirm_router as session_confirm_router
from api.v1.session import router as session_router
from api.v1.share import router as share_router
from api.v1.skill import router as skill_router

"""API v1 路由聚合。

所有子模块路由在此汇总，由 server.py 通过 ``app.include_router(v1_router, prefix="/api/v1")`` 挂载。
同时保留旧路由前缀的 301 重定向，确保前端不中断。
"""

router = APIRouter()


# ── 旧路由重定向（向后兼容）────────────────────────────────

_LEGACY_REDIRECTS = {
    "/api/auth/login": "/api/v1/auth/login",
    "/api/auth/register": "/api/v1/auth/register",
    "/api/auth/logout": "/api/v1/auth/logout",
    "/api/auth/me": "/api/v1/auth/me",
    "/api/sessions": "/api/v1/sessions",
    "/api/sessions/": "/api/v1/sessions",
}

_LEGACY_PREFIX_REDIRECTS = {
    "/api/agents": "/api/v1/agents",
    "/api/skills": "/api/v1/skills",
    "/api/mcp": "/api/v1/mcp",
    "/api/itineraries": "/api/v1/itineraries",
    "/api/album": "/api/v1/album",
    "/api/memory": "/api/v1/memory",
    "/api/news": "/api/v1/news",
    "/api/share": "/api/v1/share",
}


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def legacy_redirect(request: Request, path: str):
    full_path = f"/{path}"
    if full_path in _LEGACY_REDIRECTS:
        return RedirectResponse(url=_LEGACY_REDIRECTS[full_path], status_code=301)
    for prefix, target in _LEGACY_PREFIX_REDIRECTS.items():
        if full_path.startswith(prefix):
            return RedirectResponse(url=full_path.replace(prefix, target, 1), status_code=301)
    return RedirectResponse(url=f"/api/v1/{path}", status_code=301)


# ── 路由挂载 ──────────────────────────────────────────────

router.include_router(auth_router, prefix="/auth")
router.include_router(chat_router, prefix="/chat")
router.include_router(session_router, prefix="/sessions")
router.include_router(session_confirm_router, prefix="/session")
router.include_router(agent_router, prefix="/agents")
router.include_router(skill_router, prefix="/skills")
router.include_router(mcp_router, prefix="/mcp")
router.include_router(itinerary_router, prefix="/itineraries")
router.include_router(album_router, prefix="/itineraries")
router.include_router(album_serve_router, prefix="/album")
router.include_router(memory_router, prefix="/memory")
router.include_router(news_router, prefix="/news")
router.include_router(geocode_router, prefix="/geocode")
router.include_router(share_router, prefix="/share")
router.include_router(debug_router, prefix="/debug")
router.include_router(health_router, prefix="/health")
router.include_router(feedback_router, prefix="/feedback")
