from __future__ import annotations

from fastapi import APIRouter

from api.v1.agent import router as agent_router
from api.v1.auth import router as auth_router
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
server.py 同时将 v1_router 挂载在 /api 前缀下实现向后兼容，无需额外重定向。
"""

router = APIRouter()


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
router.include_router(memory_router, prefix="/memories")
router.include_router(news_router, prefix="/news")
router.include_router(geocode_router, prefix="/geocode")
router.include_router(share_router, prefix="/share")
router.include_router(debug_router, prefix="/debug")
router.include_router(health_router, prefix="/health")
router.include_router(feedback_router, prefix="/feedback")
