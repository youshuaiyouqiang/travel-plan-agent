from __future__ import annotations

import asyncio
import json as json_mod
import os
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
import logging
from app import build_orchestrator

from config import settings
from domain.shared.runtime.logging import init_from_settings
from core.auth import UserStore
from core.token import generate_token, verify_token
from core.trending import get_trending_travel, refresh_pool
from core.audit.logger import AuditLogger

init_from_settings()
logger = logging.getLogger(__name__)
_api_audit = AuditLogger()

_BACKGROUND_TASK: asyncio.Task | None = None
_POOL_REFRESH_INTERVAL = 1800


async def _periodic_refresh_pool() -> None:
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _BACKGROUND_TASK
    logger.info("Server starting: warming up trending pool")
    try:
        count = await refresh_pool()
        logger.info("Trending pool warmup done: %d items", count)
    except Exception as e:
        logger.warning("Trending pool warmup failed: %s", e)
    _BACKGROUND_TASK = asyncio.create_task(_periodic_refresh_pool())
    yield
    if _BACKGROUND_TASK:
        _BACKGROUND_TASK.cancel()
        try:
            await _BACKGROUND_TASK
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Claw API", lifespan=lifespan)
_container = build_orchestrator()
agent = _container.orchestrator
app.state.skill_provider = _container.skill_provider
app.state.builtin_configs = _container.builtin_configs
app.state.custom_repo = _container.custom_repo
user_store = UserStore()

_PUBLIC_PATHS = {"/api/auth/register", "/api/auth/login", "/api/trending", "/health", "/metrics", "/api/shared"}

_rate_limiter = None


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)
    path = request.url.path
    if path.startswith("/debug") or path in _PUBLIC_PATHS or path.startswith("/api/auth") or path.startswith("/api/shared"):
        return await call_next(request)
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip() if auth_header.startswith("Bearer ") else ""
    if not token:
        token = request.query_params.get("token", "")
    if token:
        user_id = verify_token(token)
        if user_id:
            request.state.user_id = user_id
            return await call_next(request)
    return JSONResponse(status_code=401, content={"detail": "未登录或登录已过期"})


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path == "/api/chat" and _rate_limiter:
        client_id = request.client.host if request.client else "unknown"
        if not _rate_limiter.is_allowed(client_id):
            return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})
    return await call_next(request)


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    user_id: str
    username: str
    token: str


@app.post("/api/auth/register", response_model=AuthResponse)
async def register(req: RegisterRequest) -> AuthResponse:
    if len(req.username) < 2 or len(req.username) > 32:
        return JSONResponse(status_code=400, content={"detail": "用户名长度需在2-32之间"})
    if len(req.password) < 6:
        return JSONResponse(status_code=400, content={"detail": "密码长度不能少于6位"})
    try:
        user = user_store.create(req.username, req.password)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"detail": str(e)})
    token = generate_token(user.user_id)
    logger.info("User registered: user_id=%s username=%s", user.user_id, user.username)
    return AuthResponse(user_id=user.user_id, username=user.username, token=token)


@app.post("/api/auth/login", response_model=AuthResponse)
async def login(req: LoginRequest) -> AuthResponse:
    user = user_store.authenticate(req.username, req.password)
    if not user:
        return JSONResponse(status_code=401, content={"detail": "用户名或密码错误"})
    token = generate_token(user.user_id)
    logger.info("User logged in: user_id=%s username=%s", user.user_id, user.username)
    return AuthResponse(user_id=user.user_id, username=user.username, token=token)


class ChatRequest(BaseModel):
    session_id: str
    user_id: str | None = None
    message: str = Field(..., min_length=1, max_length=8000)
    agent_id: str | None = None  # 指定使用哪个智能体


class ChatResponse(BaseModel):
    status: str = "completed"
    reply: str


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request) -> ChatResponse:
    auth_user_id = getattr(request.state, "user_id", None)
    effective_user_id = auth_user_id or req.user_id
    trace_id = uuid.uuid4().hex[:16]
    start_time = time.monotonic()
    logger.info("API /chat request: session_id=%s user_id=%s trace_id=%s", req.session_id, effective_user_id, trace_id)
    _api_audit.log_api_boundary(
        session_id=req.session_id, user_id=effective_user_id or "", trace_id=trace_id,
        direction="request", endpoint="/api/chat", method="POST",
        payload=req.message, agent_id=req.agent_id or "",
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
        session_id=req.session_id, user_id=effective_user_id or "", trace_id=trace_id,
        direction="response", endpoint="/api/chat", method="POST",
        payload=result.get("reply", ""), duration_ms=duration_ms, agent_id=req.agent_id or "",
    )
    logger.info("API /chat response: session_id=%s user_id=%s trace_id=%s duration_ms=%s", req.session_id, effective_user_id, trace_id, duration_ms)
    return ChatResponse(status=result["status"], reply=result["reply"])


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest, request: Request) -> StreamingResponse:
    auth_user_id = getattr(request.state, "user_id", None)
    effective_user_id = auth_user_id or req.user_id
    trace_id = uuid.uuid4().hex[:16]
    start_time = time.monotonic()
    logger.info("API /chat/stream request: session_id=%s user_id=%s trace_id=%s", req.session_id, effective_user_id, trace_id)
    _api_audit.log_api_boundary(
        session_id=req.session_id, user_id=effective_user_id or "", trace_id=trace_id,
        direction="request", endpoint="/api/chat/stream", method="POST",
        payload=req.message, agent_id=req.agent_id or "",
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
            session_id=req.session_id, user_id=effective_user_id or "", trace_id=trace_id,
            direction="response", endpoint="/api/chat/stream", method="POST",
            payload=full_reply, duration_ms=duration_ms, agent_id=req.agent_id or "",
        )
        logger.info("API /chat/stream done: session_id=%s trace_id=%s duration_ms=%s", req.session_id, trace_id, duration_ms)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/sessions")
async def list_sessions(request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    sessions = agent.list_user_sessions(user_id)
    return {"sessions": sessions}


class CreateAgentRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    description: str = Field("", max_length=500)
    icon: str = Field("🤖", max_length=16)
    system_prompt: str = Field(..., min_length=1, max_length=8000)
    skills: list[str] = Field(default_factory=list, max_length=20)
    welcome_message: str = Field("", max_length=500)
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    is_public: bool = False


class UpdateAgentRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=64)
    description: str | None = Field(None, max_length=500)
    icon: str | None = Field(None, max_length=16)
    system_prompt: str | None = Field(None, min_length=1, max_length=8000)
    skills: list[str] | None = Field(None, max_length=20)
    welcome_message: str | None = Field(None, max_length=500)
    temperature: float | None = Field(None, ge=0.0, le=2.0)
    is_public: bool | None = None


@app.get("/api/skills")
async def list_skills(request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "未登录")
    sp = request.app.state.skill_provider
    return {"skills": [asdict(s) for s in sp.list_skills()]}


@app.get("/api/agents")
async def list_agents(request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "未登录")
    builtin = [asdict(c) for c in request.app.state.builtin_configs]
    custom = [asdict(c) for c in request.app.state.custom_repo.list_by_user(user_id)]
    public = [asdict(c) for c in request.app.state.custom_repo.list_public()]
    return {"builtin": builtin, "custom": custom, "public": public}


@app.post("/api/agents/custom")
async def create_custom_agent(req: CreateAgentRequest, request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "未登录")
    # TODO: 商用应加速率限制（如每用户每天最多创建 N 个）
    config = request.app.state.custom_repo.create(user_id, **req.model_dump())
    return asdict(config)


@app.get("/api/agents/custom/{agent_id}")
async def get_custom_agent(agent_id: str, request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "未登录")
    config = request.app.state.custom_repo.get(agent_id)
    if not config or (config.user_id != user_id and not config.is_public):
        raise HTTPException(404, "智能体不存在")
    return asdict(config)


@app.put("/api/agents/custom/{agent_id}")
async def update_custom_agent(agent_id: str, req: UpdateAgentRequest, request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "未登录")
    repo = request.app.state.custom_repo
    config = repo.get(agent_id)
    if not config or config.user_id != user_id:
        raise HTTPException(403, "无权修改")
    updated = repo.update(agent_id, **req.model_dump(exclude_unset=True))
    return asdict(updated)


@app.delete("/api/agents/custom/{agent_id}")
async def delete_custom_agent(agent_id: str, request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "未登录")
    repo = request.app.state.custom_repo
    config = repo.get(agent_id)
    if not config or config.user_id != user_id:
        raise HTTPException(403, "无权删除")
    repo.delete(agent_id)
    return {"status": "deleted"}


@app.post("/api/sessions")
async def create_session(request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    session_id = os.urandom(8).hex()
    return {"session_id": session_id, "user_id": user_id}


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str, request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    agent.delete_session(session_id, user_id=user_id)
    return {"detail": "已删除"}


@app.get("/api/memories")
async def get_memories(request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    from core.memory import DualLayerMemoryManager
    mgr = DualLayerMemoryManager()
    ltm_list = mgr.get_long_term_memories(user_id)
    stm_list = mgr.get_short_term_memories(user_id, limit=20)
    category_labels = {"preference": "偏好", "fact": "事实", "experience": "经验"}
    long_term = []
    for m in ltm_list:
        item = {
            "id": m.id,
            "category": m.category,
            "category_label": category_labels.get(m.category, m.category),
            "content": m.content,
            "experience_tag": m.experience_tag,
            "extraction_count": m.extraction_count,
            "last_accessed_at": m.last_accessed_at,
            "created_at": m.created_at,
        }
        long_term.append(item)
    short_term = []
    for m in stm_list:
        item = {
            "id": m.id,
            "category": m.category,
            "category_label": category_labels.get(m.category, m.category),
            "content": m.content,
            "experience_tag": m.experience_tag,
            "extraction_count": m.extraction_count,
            "last_accessed_at": m.last_accessed_at,
            "created_at": m.created_at,
        }
        short_term.append(item)
    return {
        "long_term": long_term,
        "short_term": short_term,
        "summary": {
            "total_ltm": len(long_term),
            "total_stm": len(short_term),
            "preferences": len([m for m in long_term + short_term if m["category"] == "preference"]),
            "facts": len([m for m in long_term + short_term if m["category"] == "fact"]),
            "experiences": len([m for m in long_term + short_term if m["category"] == "experience"]),
        },
    }


@app.delete("/api/memories/{memory_type}/{memory_id}")
async def delete_memory(memory_type: str, memory_id: int, request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    if memory_type not in ("short_term", "long_term"):
        return JSONResponse(status_code=400, content={"detail": "无效的记忆类型"})
    from infra.db import get_connection
    conn = get_connection()
    table = "short_term_memories" if memory_type == "short_term" else "long_term_memories"
    row = conn.execute(f"SELECT id FROM {table} WHERE id = ? AND user_id = ?", (memory_id, user_id)).fetchone()
    if not row:
        return JSONResponse(status_code=404, content={"detail": "记忆不存在"})
    conn.execute(f"DELETE FROM {table} WHERE id = ?", (memory_id,))
    conn.commit()
    return {"detail": "已删除"}


@app.get("/api/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    snapshot = agent.snapshot_session(session_id)
    if not snapshot:
        return {"messages": []}
    return {"messages": snapshot.get("turns", [])}


@app.get("/debug/trace/{session_id}")
async def latest_trace(session_id: str) -> dict:
    logger.debug("API /debug/trace request: session_id=%s", session_id)
    return {"trace": agent.latest_trace(session_id)}


@app.get("/debug/session/{session_id}")
async def session_snapshot(session_id: str, user_id: str | None = None) -> dict:
    logger.debug("API /debug/session request: session_id=%s user_id=%s", session_id, user_id)
    return {"session": agent.snapshot_session(session_id), "task": agent.snapshot_task(session_id, user_id=user_id)}


@app.get("/debug/memory")
async def memory_snapshot(
    query: str = "",
    limit: int = 10,
    session_id: str = "default",
    user_id: str | None = None,
) -> dict:
    effective_user_id = user_id or session_id
    logger.debug(
        "API /debug/memory request: query=%s limit=%s session_id=%s user_id=%s",
        query,
        limit,
        session_id,
        effective_user_id,
    )
    if query.strip():
        return {"items": agent.search_memory(query, limit=limit, user_id=effective_user_id)}
    return {"items": agent.list_recent_memory(limit=limit, user_id=effective_user_id)}


@app.get("/debug/mcp")
async def mcp_snapshot() -> dict:
    logger.debug("API /debug/mcp request")
    return {"servers": agent.list_mcp_servers()}


@app.get("/debug/mcp/select")
async def mcp_selection(query: str, limit: int = 4) -> dict:
    logger.debug("API /debug/mcp/select request: query=%s limit=%s", query, limit)
    return {"items": agent.select_mcp_tools(query, limit=limit)}


@app.get("/debug/task/{session_id}")
async def task_snapshot(session_id: str, user_id: str | None = None) -> dict:
    logger.debug("API /debug/task request: session_id=%s user_id=%s", session_id, user_id)
    return {"task": agent.snapshot_task(session_id, user_id=user_id)}


@app.get("/health")
async def health() -> dict:
    try:
        from infra.health import check_health
        status = check_health()
        return {"status": status.status, "details": status.details}
    except Exception as exc:
        return {"status": "degraded", "details": {"error": str(exc)}}


@app.get("/metrics")
async def metrics():
    if settings.metrics_enabled:
        try:
            from prometheus_client import generate_latest
            return Response(content=generate_latest(), media_type="text/plain")
        except ImportError:
            return {"detail": "prometheus_client not installed"}
    return {"detail": "metrics disabled"}


@app.get("/api/trending")
async def trending(refresh: bool = False) -> dict:
    items = await get_trending_travel(refresh=refresh)
    return {"items": items}


from core.itinerary.repository import ItineraryRepository

_itinerary_repo = ItineraryRepository()


def _user_owns_itinerary(user_id: str, itin) -> bool:
    if itin.user_id and itin.user_id == user_id:
        return True
    if itin.session_id:
        from infra.db import get_connection
        conn = get_connection()
        row = conn.execute(
            "SELECT 1 FROM tasks WHERE user_id = ? AND session_id = ? LIMIT 1",
            (user_id, itin.session_id),
        ).fetchone()
        if row:
            return True
    if itin.user_id:
        from core.auth import UserStore
        us = UserStore()
        existing = us.get_by_id(itin.user_id)
        if not existing:
            return True
    return False


@app.post("/api/itineraries")
async def create_itinerary(request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    body = await request.json()
    title = str(body.get("title", "")).strip()
    destination = str(body.get("destination", "")).strip()
    start_date = str(body.get("start_date", "")).strip()
    end_date = str(body.get("end_date", "")).strip()
    if not title or not destination:
        return JSONResponse(status_code=400, content={"detail": "标题和目的地不能为空"})
    session_id = str(body.get("session_id", ""))
    budget = str(body.get("budget", ""))
    raw_content = str(body.get("raw_content", ""))
    status = str(body.get("status", "planning"))
    days_data = body.get("days", [])
    if days_data:
        from core.itinerary.schema import Itinerary as Itin, DayPlan, Activity
        itin = Itin(
            user_id=user_id,
            session_id=session_id,
            title=title,
            destination=destination,
            start_date=start_date,
            end_date=end_date,
            budget=budget,
            raw_content=raw_content,
            status=status,
        )
        for di, day_data in enumerate(days_data):
            day = DayPlan(
                day_index=di,
                date=str(day_data.get("date", "")),
                title=str(day_data.get("title", "")),
                summary=str(day_data.get("summary", "")),
            )
            for ai, act_data in enumerate(day_data.get("activities", [])):
                act = Activity(
                    activity_index=ai,
                    time_slot=str(act_data.get("time_slot", "")),
                    title=str(act_data.get("title", "")),
                    location=str(act_data.get("location", "")),
                    description=str(act_data.get("description", "")),
                    image_url=str(act_data.get("image_url", "")),
                    cost=float(act_data.get("cost", 0)),
                    tips=str(act_data.get("tips", "")),
                )
                day.activities.append(act)
            itin.days.append(day)
        result = _itinerary_repo.save_full_itinerary(itin)
    else:
        result = _itinerary_repo.create_itinerary(
            user_id=user_id,
            title=title,
            destination=destination,
            start_date=start_date,
            end_date=end_date,
            session_id=session_id,
            budget=budget,
            raw_content=raw_content,
            status=status,
        )
    return result.to_dict()


@app.get("/api/itineraries")
async def list_itineraries(request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    items = _itinerary_repo.list_itineraries(user_id)
    seen_ids = {i.id for i in items}
    from infra.db import get_connection
    conn = get_connection()
    session_rows = conn.execute(
        "SELECT DISTINCT session_id FROM tasks WHERE user_id = ? AND session_id != ''",
        (user_id,),
    ).fetchall()
    for row in session_rows:
        sid = row["session_id"]
        if not sid:
            continue
        session_itins = conn.execute(
            "SELECT * FROM itineraries WHERE session_id = ? ORDER BY updated_at DESC",
            (sid,),
        ).fetchall()
        for r in session_itins:
            from core.itinerary.schema import Itinerary
            itin = Itinerary.from_row(dict(r))
            if itin.id not in seen_ids:
                items.append(itin)
                seen_ids.add(itin.id)
    return {"itineraries": [i.to_list_dict() for i in items]}


@app.post("/api/itineraries/compare")
async def compare_itineraries(request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    body = await request.json()
    ids = body.get("ids", [])
    if len(ids) < 2:
        return JSONResponse(status_code=400, content={"detail": "至少需要2个行程进行对比"})
    if len(ids) > 4:
        return JSONResponse(status_code=400, content={"detail": "最多支持4个行程对比"})
    results = []
    for itin_id in ids:
        itin = _itinerary_repo.get_itinerary(str(itin_id))
        if not itin or not _user_owns_itinerary(user_id, itin):
            continue
        total_budget = sum(a.cost for d in itin.days for a in d.activities)
        total_actual = sum(a.actual_cost for d in itin.days for a in d.activities)
        results.append({
            "id": itin.id,
            "title": itin.title,
            "destination": itin.destination,
            "start_date": itin.start_date,
            "end_date": itin.end_date,
            "budget_text": itin.budget,
            "budget_total": total_budget,
            "actual_total": total_actual,
            "days_count": len(itin.days),
            "activities_count": sum(len(d.activities) for d in itin.days),
            "days": [
                {
                    "day_index": d.day_index,
                    "date": d.date,
                    "title": d.title,
                    "summary": d.summary,
                    "budget": sum(a.cost for a in d.activities),
                    "actual": sum(a.actual_cost for a in d.activities),
                    "activities": [
                        {
                            "time_slot": a.time_slot,
                            "title": a.title,
                            "location": a.location,
                            "cost": a.cost,
                            "actual_cost": a.actual_cost,
                        }
                        for a in d.activities
                    ],
                }
                for d in itin.days
            ],
        })
    if len(results) < 2:
        return JSONResponse(status_code=400, content={"detail": "有效行程不足2个"})
    return {"itineraries": results}


@app.get("/api/itineraries/{itinerary_id}")
async def get_itinerary(itinerary_id: str, request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    itin = _itinerary_repo.get_itinerary(itinerary_id)
    if not itin:
        return JSONResponse(status_code=404, content={"detail": "行程不存在"})
    return itin.to_dict()


@app.put("/api/itineraries/{itinerary_id}")
async def update_itinerary(itinerary_id: str, request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    itin = _itinerary_repo.get_itinerary(itinerary_id)
    if not itin or not _user_owns_itinerary(user_id, itin):
        return JSONResponse(status_code=404, content={"detail": "行程不存在"})
    body = await request.json()
    _itinerary_repo.update_itinerary(itinerary_id, **body)
    updated = _itinerary_repo.get_itinerary(itinerary_id)
    return updated.to_dict()


@app.delete("/api/itineraries/{itinerary_id}")
async def delete_itinerary(itinerary_id: str, request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    itin = _itinerary_repo.get_itinerary(itinerary_id)
    if not itin or not _user_owns_itinerary(user_id, itin):
        return JSONResponse(status_code=404, content={"detail": "行程不存在"})
    _itinerary_repo.delete_itinerary(itinerary_id)
    return {"detail": "已删除"}


@app.patch("/api/itineraries/{itinerary_id}/activities/{activity_id}/checkin")
async def checkin_activity(itinerary_id: str, activity_id: int, request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    itin = _itinerary_repo.get_itinerary(itinerary_id)
    if not itin or not _user_owns_itinerary(user_id, itin):
        return JSONResponse(status_code=404, content={"detail": "行程不存在"})
    activity = _itinerary_repo.get_activity(activity_id)
    if not activity:
        return JSONResponse(status_code=404, content={"detail": "活动不存在"})
    body = await request.json()
    checked_in = body.get("checked_in", True)
    if checked_in:
        _itinerary_repo.check_in_activity(activity_id)
    else:
        _itinerary_repo.uncheck_activity(activity_id)
    updated = _itinerary_repo.get_activity(activity_id)
    return updated.to_dict()


@app.delete("/api/itineraries/{itinerary_id}/activities/{activity_id}")
async def delete_activity(itinerary_id: str, activity_id: int, request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    itin = _itinerary_repo.get_itinerary(itinerary_id)
    if not itin or not _user_owns_itinerary(user_id, itin):
        return JSONResponse(status_code=404, content={"detail": "行程不存在"})
    _itinerary_repo.delete_activity(activity_id)
    return {"detail": "已删除"}


@app.patch("/api/itineraries/{itinerary_id}/activities/{activity_id}/cost")
async def update_activity_cost(itinerary_id: str, activity_id: int, request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    itin = _itinerary_repo.get_itinerary(itinerary_id)
    if not itin or not _user_owns_itinerary(user_id, itin):
        return JSONResponse(status_code=404, content={"detail": "行程不存在"})
    body = await request.json()
    actual_cost = float(body.get("actual_cost", 0))
    _itinerary_repo.update_actual_cost(activity_id, actual_cost)
    updated = _itinerary_repo.get_activity(activity_id)
    return updated.to_dict()


@app.get("/api/itineraries/{itinerary_id}/expense-summary")
async def expense_summary(itinerary_id: str, request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    itin = _itinerary_repo.get_itinerary(itinerary_id)
    if not itin or not _user_owns_itinerary(user_id, itin):
        return JSONResponse(status_code=404, content={"detail": "行程不存在"})
    total_budget = 0.0
    total_actual = 0.0
    day_summaries = []
    for day in itin.days:
        day_budget = sum(a.cost for a in day.activities)
        day_actual = sum(a.actual_cost for a in day.activities)
        total_budget += day_budget
        total_actual += day_actual
        day_summaries.append({
            "day_index": day.day_index,
            "date": day.date,
            "title": day.title,
            "budget": day_budget,
            "actual": day_actual,
            "activities": [
                {
                    "id": a.id,
                    "title": a.title,
                    "budget": a.cost,
                    "actual": a.actual_cost,
                    "checked_in": a.checked_in,
                }
                for a in day.activities
            ],
        })
    budget_str = itin.budget or ""
    budget_num = 0.0
    for seg in budget_str.replace("约", "").replace("元", "").replace("/人", "").replace(",", "").split():
        try:
            budget_num = float(seg)
            break
        except ValueError:
            continue
    return {
        "itinerary_id": itinerary_id,
        "title": itin.title,
        "budget_text": itin.budget,
        "budget_total": budget_num or total_budget,
        "actual_total": total_actual,
        "remaining": (budget_num or total_budget) - total_actual,
        "days": day_summaries,
    }


@app.post("/api/itineraries/{itinerary_id}/share")
async def create_share_link(itinerary_id: str, request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    itin = _itinerary_repo.get_itinerary(itinerary_id)
    if not itin or not _user_owns_itinerary(user_id, itin):
        return JSONResponse(status_code=404, content={"detail": "行程不存在"})
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    expires_at = str(body.get("expires_at", "")) if body else ""
    token = _itinerary_repo.create_share_link(itinerary_id, user_id, expires_at)
    return {"token": token, "itinerary_id": itinerary_id}


@app.get("/api/itineraries/{itinerary_id}/shares")
async def list_share_links(itinerary_id: str, request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    links = _itinerary_repo.list_share_links(itinerary_id)
    return {"shares": links}


@app.delete("/api/itineraries/{itinerary_id}/shares/{token}")
async def delete_share_link(itinerary_id: str, token: str, request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    _itinerary_repo.delete_share_link(token)
    return {"detail": "已删除"}


@app.post("/api/geocode")
async def batch_geocode(request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    body = await request.json()
    addresses = body.get("addresses", [])
    if not addresses or not isinstance(addresses, list):
        return JSONResponse(status_code=400, content={"detail": "addresses 列表不能为空"})
    if len(addresses) > 20:
        return JSONResponse(status_code=400, content={"detail": "单次最多20 个地址"})
    import urllib.request
    import urllib.parse
    import json as _json
    amap_key = os.environ.get("AMAP_WEBSERVICE_KEY", "")
    if not amap_key:
        return JSONResponse(status_code=503, content={"detail": "高德地图服务未配置"})
    results = []
    for addr in addresses:
        addr = str(addr).strip()
        if not addr:
            results.append({"address": addr, "lng": None, "lat": None, "formatted": ""})
            continue
        try:
            qs = urllib.parse.urlencode({"address": addr, "key": amap_key})
            url = f"https://restapi.amap.com/v3/geocode/geo?{qs}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = _json.loads(resp.read().decode())
            geocodes = data.get("geocodes", [])
            if geocodes:
                loc = geocodes[0].get("location", "")
                parts = loc.split(",") if loc else []
                results.append({
                    "address": addr,
                    "lng": float(parts[0]) if len(parts) == 2 else None,
                    "lat": float(parts[1]) if len(parts) == 2 else None,
                    "formatted": geocodes[0].get("formatted_address", ""),
                })
            else:
                results.append({"address": addr, "lng": None, "lat": None, "formatted": ""})
        except Exception as e:
            logger.warning("Geocode failed for '%s': %s", addr, e)
            results.append({"address": addr, "lng": None, "lat": None, "formatted": ""})
    return {"results": results}


def _nominatim_lookup(query: str) -> dict | None:
    """同步调用 Nominatim —— 必须在线程池中执行，避免阻塞事件循环。"""
    import urllib.request
    import urllib.parse
    import json as _json
    try:
        qs = urllib.parse.urlencode({
            "q": query,
            "format": "json",
            "limit": "1",
            "accept-language": "zh",
        })
        url = f"https://nominatim.openstreetmap.org/search?{qs}"
        req = urllib.request.Request(url, headers={"User-Agent": "ClawTravelApp/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read().decode())
        if data and len(data) > 0:
            lat = float(data[0].get("lat", 0))
            lon = float(data[0].get("lon", 0))
            if lat != 0 and lon != 0:
                return {
                    "lng": lon,
                    "lat": lat,
                    "formatted": data[0].get("display_name", ""),
                }
    except Exception as e:
        logger.warning("Nominatim geocode failed for '%s': %s", query, e)
    return None


@app.post("/api/geocode/intl")
async def intl_geocode(request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    body = await request.json()
    address = str(body.get("address", "")).strip()
    city = str(body.get("city", "")).strip()
    if not address:
        return JSONResponse(status_code=400, content={"detail": "address 不能为空"})
    from api.intl_coords import lookup_intl_coords
    coords = lookup_intl_coords(address, city or None)
    if coords:
        return {"address": address, "lng": coords[0], "lat": coords[1], "formatted": address}
    query = f"{city} {address}" if city and address not in city else address
    # 用线程池执行同步阻塞的 Nominatim 调用，避免卡死事件循环
    # （此前直接在 async 路由里调 urllib.urlopen 会阻塞整个事件循环，
    #  导致并发的其他请求如打卡 PATCH 长时间无响应）
    result = await asyncio.to_thread(_nominatim_lookup, query)
    if result:
        return {"address": address, **result}
    return {"address": address, "lng": None, "lat": None, "formatted": ""}


@app.get("/api/shared/{token}")
async def get_shared_itinerary(token: str) -> dict:
    link = _itinerary_repo.get_share_link(token)
    if not link:
        return JSONResponse(status_code=404, content={"detail": "分享链接不存在"})
    itin = _itinerary_repo.get_itinerary(link["itinerary_id"])
    if not itin:
        return JSONResponse(status_code=404, content={"detail": "行程不存在"})
    return {
        "itinerary": itin.to_dict(),
        "share_info": {
            "view_count": link["view_count"],
            "created_at": link["created_at"],
        },
    }


# ==================== 相册管理 ====================
from core.album.service import AlbumService
from fastapi import UploadFile, File, Form
from fastapi.responses import FileResponse as FastAPIFileResponse

_album_service = AlbumService()


@app.post("/api/itineraries/{itinerary_id}/photos")
async def upload_photos(
    itinerary_id: str,
    request: Request,
    files: list[UploadFile] = File(...),
    description: str = Form(""),
    day_index: int = Form(0),
):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})

    itin = _itinerary_repo.get_itinerary(itinerary_id)
    if not itin or not _user_owns_itinerary(user_id, itin):
        return JSONResponse(status_code=400, content={"detail": "行程不存在"})

    photos = []
    for f in files:
        file_bytes = await f.read()
        try:
            photo = await _album_service.upload(
                itinerary_id=itinerary_id,
                user_id=user_id,
                file_name=f.filename or "",
                file_bytes=file_bytes,
                mime_type=f.content_type or "image/jpeg",
                description=description,
                day_index=day_index,
            )
            photos.append(photo.to_dict())
        except ValueError as e:
            return JSONResponse(status_code=400, content={"detail": str(e)})
    return {"photos": photos}


@app.get("/api/itineraries/{itinerary_id}/photos")
async def list_photos(itinerary_id: str, request: Request, day_index: int = 0, tag: str = ""):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})

    if tag:
        photos = _album_service.list_photos_by_tag(itinerary_id, tag)
    elif day_index > 0:
        photos = _album_service.list_photos(itinerary_id, day_index)
    else:
        photos = _album_service.list_photos(itinerary_id)

    tags = _album_service.get_all_tags(itinerary_id)
    cover = _album_service.repo.get_cover(itinerary_id)

    return {
        "itinerary_id": itinerary_id,
        "photos": [p.to_dict() for p in photos],
        "total": len(photos),
        "tags": tags,
        "cover": cover.to_dict() if cover else None,
    }


@app.delete("/api/itineraries/{itinerary_id}/photos/{photo_id}")
async def delete_photo(itinerary_id: str, photo_id: int, request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    try:
        _album_service.delete(photo_id, user_id)
    except ValueError:
        return JSONResponse(status_code=404, content={"detail": "照片不存在"})
    except PermissionError:
        return JSONResponse(status_code=403, content={"detail": "无权删除此照片"})
    return {"detail": "已删除"}


@app.patch("/api/itineraries/{itinerary_id}/photos/{photo_id}")
async def update_photo(itinerary_id: str, photo_id: int, request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    body = await request.json()
    _album_service.update_photo(
        photo_id,
        description=body.get("description"),
        day_index=body.get("day_index"),
        tags=body.get("tags"),
    )
    photo = _album_service.repo.get_photo(photo_id)
    return photo.to_dict() if photo else JSONResponse(status_code=404, content={"detail": "照片不存在"})


@app.post("/api/itineraries/{itinerary_id}/photos/{photo_id}/cover")
async def set_cover(itinerary_id: str, photo_id: int, request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    try:
        photo = _album_service.set_cover(itinerary_id, photo_id)
        return photo.to_dict()
    except ValueError as e:
        return JSONResponse(status_code=400, content={"detail": str(e)})


@app.get("/api/itineraries/{itinerary_id}/photos/map")
async def get_photo_locations(itinerary_id: str, request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    photos = _album_service.get_photos_with_location(itinerary_id)
    return {
        "itinerary_id": itinerary_id,
        "markers": [
            {
                "photo_id": p.id,
                "latitude": p.latitude,
                "longitude": p.longitude,
                "description": p.ai_description or p.description or p.file_name,
                "day_index": p.day_index,
                "thumbnail_path": p.thumbnail_path,
            }
            for p in photos
        ],
    }


@app.post("/api/itineraries/{itinerary_id}/travelogue")
async def generate_travelogue(itinerary_id: str, request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    try:
        content = await _album_service.generate_travelogue(itinerary_id)
        return {"itinerary_id": itinerary_id, "content": content}
    except ValueError as e:
        return JSONResponse(status_code=400, content={"detail": str(e)})


@app.get("/api/album/{file_path:path}")
async def serve_album_image(file_path: str, request: Request):
    # <img> 标签无法携带 Authorization header，支持 query param token
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        token = request.query_params.get("token", "")
        if token:
            try:
                payload = verify_token(token)
                user_id = payload.get("user_id")
            except Exception:
                pass
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    full_path = settings.data_dir / "album" / file_path
    if not full_path.exists():
        return JSONResponse(status_code=404, content={"detail": "文件不存在"})
    return FastAPIFileResponse(str(full_path))
