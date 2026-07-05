from __future__ import annotations

import logging

from fastapi import APIRouter, Request

router = APIRouter(tags=["debug"])

logger = logging.getLogger(__name__)


@router.get("/trace/{session_id}")
async def latest_trace(session_id: str, request: Request) -> dict:
    agent = request.app.state.agent
    logger.debug("API /debug/trace request: session_id=%s", session_id)
    return {"trace": agent.latest_trace(session_id)}


@router.get("/session/{session_id}")
async def session_snapshot(session_id: str, user_id: str | None = None, request: Request = None) -> dict:
    agent = request.app.state.agent
    logger.debug("API /debug/session request: session_id=%s user_id=%s", session_id, user_id)
    return {
        "session": agent.snapshot_session(session_id),
        "task": agent.snapshot_task(session_id, user_id=user_id),
    }


@router.get("/mcp")
async def mcp_snapshot(request: Request) -> dict:
    agent = request.app.state.agent
    logger.debug("API /debug/mcp request")
    return {"servers": agent.list_mcp_servers()}


@router.get("/mcp/select")
async def mcp_selection(query: str, limit: int = 4, request: Request = None) -> dict:
    agent = request.app.state.agent
    logger.debug("API /debug/mcp/select request: query=%s limit=%s", query, limit)
    return {"items": agent.select_mcp_tools(query, limit=limit)}


@router.get("/task/{session_id}")
async def task_snapshot(session_id: str, user_id: str | None = None, request: Request = None) -> dict:
    agent = request.app.state.agent
    logger.debug("API /debug/task request: session_id=%s user_id=%s", session_id, user_id)
    return {"task": agent.snapshot_task(session_id, user_id=user_id)}
