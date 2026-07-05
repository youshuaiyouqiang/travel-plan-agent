from __future__ import annotations

import json as json_mod
import logging
import time
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from application.dto.request import ChatRequest
from application.dto.response import ChatResponse
from domain.shared.audit.logger import AuditLogger

logger = logging.getLogger(__name__)
_api_audit = AuditLogger()

router = APIRouter(tags=["chat"])


def _get_agent(request: Request):
    return request.app.state.agent


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request) -> ChatResponse:
    agent = _get_agent(request)
    auth_user_id = getattr(request.state, "user_id", None)
    effective_user_id = auth_user_id or req.user_id
    trace_id = uuid.uuid4().hex[:16]
    start_time = time.monotonic()
    logger.info("API /chat request: session_id=%s user_id=%s trace_id=%s", req.session_id, effective_user_id, trace_id)
    _api_audit.log_api_boundary(
        session_id=req.session_id,
        user_id=effective_user_id or "",
        trace_id=trace_id,
        direction="request",
        endpoint="/api/chat",
        method="POST",
        payload=req.message,
        agent_id=req.agent_id or "",
    )
    result = await agent.chat(
        session_id=req.session_id,
        user_id=effective_user_id,
        message=req.message,
        agent_id=req.agent_id,
        trace_id=trace_id,
    )
    duration_ms = int((time.monotonic() - start_time) * 1000)
    _api_audit.log_api_boundary(
        session_id=req.session_id,
        user_id=effective_user_id or "",
        trace_id=trace_id,
        direction="response",
        endpoint="/api/chat",
        method="POST",
        payload=result.get("reply", ""),
        duration_ms=duration_ms,
        agent_id=req.agent_id or "",
    )
    logger.info(
        "API /chat response: session_id=%s user_id=%s trace_id=%s duration_ms=%s",
        req.session_id,
        effective_user_id,
        trace_id,
        duration_ms,
    )
    return ChatResponse(status=result["status"], reply=result["reply"])


@router.post("/stream")
async def chat_stream(req: ChatRequest, request: Request) -> StreamingResponse:
    agent = _get_agent(request)
    auth_user_id = getattr(request.state, "user_id", None)
    effective_user_id = auth_user_id or req.user_id
    trace_id = uuid.uuid4().hex[:16]
    start_time = time.monotonic()
    logger.info(
        "API /chat/stream request: session_id=%s user_id=%s trace_id=%s", req.session_id, effective_user_id, trace_id
    )
    _api_audit.log_api_boundary(
        session_id=req.session_id,
        user_id=effective_user_id or "",
        trace_id=trace_id,
        direction="request",
        endpoint="/api/chat/stream",
        method="POST",
        payload=req.message,
        agent_id=req.agent_id or "",
    )
    full_reply = ""

    async def event_generator():
        nonlocal full_reply
        try:
            async for event in agent.chat_stream(
                session_id=req.session_id,
                user_id=effective_user_id,
                message=req.message,
                agent_id=req.agent_id,
                trace_id=trace_id,
            ):
                if event.get("type") == "chunk":
                    full_reply += event.get("data", "")
                yield f"data: {json_mod.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error("Stream error: trace_id=%s %s", trace_id, e, exc_info=True)
            error_event = json_mod.dumps({"type": "error", "data": str(e), "trace_id": trace_id}, ensure_ascii=False)
            yield f"data: {error_event}\n\n"

        duration_ms = int((time.monotonic() - start_time) * 1000)
        _api_audit.log_api_boundary(
            session_id=req.session_id,
            user_id=effective_user_id or "",
            trace_id=trace_id,
            direction="response",
            endpoint="/api/chat/stream",
            method="POST",
            payload=full_reply,
            duration_ms=duration_ms,
            agent_id=req.agent_id or "",
        )
        logger.info(
            "API /chat/stream done: session_id=%s trace_id=%s duration_ms=%s", req.session_id, trace_id, duration_ms
        )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
