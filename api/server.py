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
from domain.user.auth.auth import UserStore
from domain.user.auth.token import generate_token, verify_token
from application.trending.manager import get_trending_travel, refresh_pool
from domain.shared.audit.logger import AuditLogger
from domain.feedback.repository import FeedbackRepository

init_from_settings()
logger = logging.getLogger(__name__)
_api_audit = AuditLogger()

_BACKGROUND_TASK: asyncio.Task | None = None
_MEMORY_TASK: asyncio.Task | None = None
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


async def _periodic_memory_maintenance() -> None:
    """P1-3：记忆维护后台任务（蒸馏 + 衰减）。"""
    from application.scheduler import run_memory_maintenance
    await run_memory_maintenance()


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
    # P1-3：启动记忆维护后台任务（蒸馏 + 衰减，每小时一次）
    _MEMORY_TASK = asyncio.create_task(_periodic_memory_maintenance())
    yield
    if _BACKGROUND_TASK:
        _BACKGROUND_TASK.cancel()
        try:
            await _BACKGROUND_TASK
        except asyncio.CancelledError:
            pass
    if _MEMORY_TASK:
        _MEMORY_TASK.cancel()
        try:
            await _MEMORY_TASK
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Claw API", lifespan=lifespan)
# P2-18：时序耦合说明 — build_orchestrator() 在模块加载时同步执行，
# 若失败则 server 无法启动。理想做法是移入 lifespan 并用 request.app.state 取用，
# 但当前 agent/user_store 为模块级变量被多个路由直接引用，重构风险较高，暂保留。
_container = build_orchestrator()
agent = _container.orchestrator
app.state.skill_provider = _container.skill_provider
app.state.builtin_configs = _container.builtin_configs
app.state.custom_repo = _container.custom_repo
app.state.mcp_runtime = _container.mcp_runtime
app.state.mcp_catalog = _container.mcp_catalog
user_store = UserStore()

_PUBLIC_PATHS = {"/api/auth/register", "/api/auth/login", "/api/trending", "/health", "/metrics", "/api/shared"}
# P0-6：/api/album/ 跳过全局 auth_middleware（<img> 标签无法携带 Authorization header），
# 端点内部自行校验 query token。其它端点一律拒绝 query token，仅接受 Authorization header。
_PUBLIC_PREFIXES = ("/api/album/",)

# Phase 5: 轻量全局限流（进程内字典计数器，按 user_id + IP）。
# 注意：本限流为单进程实现，多 worker 部署（如 gunicorn -w 4）下各进程独立计数，
# 实际阈值会放大 N 倍；分布式场景应改用 Redis（参考 P1-9 方案 B）。
_rate_counters: dict[str, dict[str, float]] = {}  # key -> {"count": N, "window_start": timestamp}
_RATE_WINDOW = 60       # 时间窗口（秒）
_RATE_MAX_REQUESTS = settings.rate_limit_rpm  # 每窗口最大请求数（读 settings，默认 60）
_RATE_CLEANUP_INTERVAL = 300  # 清理间隔（秒）
_last_rate_cleanup = 0.0


def _make_rate_key(user_id: str, ip: str, path: str) -> str:
    """构造限流键：按用户 + IP + API 前缀聚合。"""
    # 聚合路径前缀：/api/chat/* → chat, /api/agents/* → agents
    prefix = path.split("/api/")[-1].split("/")[0] if "/api/" in path else path.strip("/")
    return f"{user_id}:{ip}:{prefix}"


def _cleanup_rate_counters(now: float) -> None:
    """清理过期的限流计数器。"""
    global _last_rate_cleanup
    if now - _last_rate_cleanup < _RATE_CLEANUP_INTERVAL:
        return
    _last_rate_cleanup = now
    expired_keys = [
        k for k, v in _rate_counters.items()
        if now - v.get("window_start", 0) > _RATE_WINDOW * 2
    ]
    for k in expired_keys:
        del _rate_counters[k]


def _check_rate(user_id: str, ip: str, path: str) -> bool:
    """检查请求频率。返回 True 表示允许，False 表示超限。"""
    now = time.monotonic()
    _cleanup_rate_counters(now)
    key = _make_rate_key(user_id, ip, path)
    counter = _rate_counters.get(key)
    if counter is None or now - counter.get("window_start", 0) > _RATE_WINDOW:
        _rate_counters[key] = {"count": 1, "window_start": now}
        return True
    counter["count"] += 1
    return counter["count"] <= _RATE_MAX_REQUESTS


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)
    path = request.url.path
    # P0-6：/api/album/ 走端点内部校验（<img> 标签限制），其它公共路径直接放行
    if path.startswith("/debug") or path in _PUBLIC_PATHS or path.startswith("/api/auth") or path.startswith("/api/shared"):
        return await call_next(request)
    if any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES):
        return await call_next(request)
    # P0-6：仅接受 Authorization header，不再从 query 参数取 token（避免泄露到 access log/浏览器历史）
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip() if auth_header.startswith("Bearer ") else ""
    if token:
        user_id = verify_token(token)
        if user_id:
            request.state.user_id = user_id
            # Phase 5: 全局限流检查
            client_ip = request.client.host if request.client else "unknown"
            if not _check_rate(user_id, client_ip, path):
                return JSONResponse(status_code=429, content={"detail": "请求过于频繁，请稍后再试"})
            return await call_next(request)
    return JSONResponse(status_code=401, content={"detail": "未登录或登录已过期"})


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """兼容旧限流器（如果配置了 _rate_limiter）。"""
    pass
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
    mcp_servers: list[str] = Field(default_factory=list, max_length=20)
    welcome_message: str = Field("", max_length=500)
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    is_public: bool = False


class UpdateAgentRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=64)
    description: str | None = Field(None, max_length=500)
    icon: str | None = Field(None, max_length=16)
    system_prompt: str | None = Field(None, min_length=1, max_length=8000)
    skills: list[str] | None = Field(None, max_length=20)
    mcp_servers: list[str] | None = Field(None, max_length=20)
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


@app.get("/api/skills/{skill_name}")
async def get_skill_detail(skill_name: str, request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "未登录")
    sp = request.app.state.skill_provider
    skill = sp.get_skill(skill_name)
    if not skill:
        raise HTTPException(404, "Skill 不存在")
    return asdict(skill)


@app.get("/api/mcp/servers")
async def list_mcp_servers(request: Request) -> dict:
    """列出所有 MCP server（含 tools 和 adapter_available 状态）。"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "未登录")
    catalog = request.app.state.mcp_catalog
    runtime = request.app.state.mcp_runtime
    servers = []
    for server in catalog.list_servers():
        tools = []
        for tool in server.tools:
            proxy_name = tool.proxy_name
            tools.append({
                "name": tool.name,
                "description": tool.description,
                "proxy_name": proxy_name,
                "input_schema": tool.input_schema,
                "adapter_available": runtime.adapter_available(proxy_name) if runtime else False,
            })
        servers.append({
            "identifier": server.identifier,
            "name": server.name,
            "description": server.description,
            "instructions": server.instructions,
            "tools": tools,
        })
    return {"servers": servers}


@app.get("/api/mcp/servers/{server_id}")
async def get_mcp_server_detail(server_id: str, request: Request) -> dict:
    """获取单个 MCP server 详情。"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "未登录")
    catalog = request.app.state.mcp_catalog
    runtime = request.app.state.mcp_runtime
    for server in catalog.list_servers():
        if server.identifier == server_id:
            tools = []
            for tool in server.tools:
                proxy_name = tool.proxy_name
                tools.append({
                    "name": tool.name,
                    "description": tool.description,
                    "proxy_name": proxy_name,
                    "input_schema": tool.input_schema,
                    "adapter_available": runtime.adapter_available(proxy_name) if runtime else False,
                })
            return {
                "identifier": server.identifier,
                "name": server.name,
                "description": server.description,
                "instructions": server.instructions,
                "tools": tools,
            }
    raise HTTPException(404, "MCP Server 不存在")


@app.get("/api/mcp/servers/{server_id}/tools")
async def get_mcp_server_tools(server_id: str, request: Request) -> dict:
    """获取某 MCP server 的工具列表。"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "未登录")
    catalog = request.app.state.mcp_catalog
    runtime = request.app.state.mcp_runtime
    for server in catalog.list_servers():
        if server.identifier == server_id:
            tools = []
            for tool in server.tools:
                proxy_name = tool.proxy_name
                tools.append({
                    "name": tool.name,
                    "description": tool.description,
                    "proxy_name": proxy_name,
                    "input_schema": tool.input_schema,
                    "adapter_available": runtime.adapter_available(proxy_name) if runtime else False,
                })
            return {"server_id": server_id, "tools": tools}
    raise HTTPException(404, "MCP Server 不存在")


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


# ===== Phase 5: 智能体市场（克隆） =====

@app.post("/api/agents/custom/{agent_id}/clone")
async def clone_custom_agent(agent_id: str, request: Request) -> dict:
    """从社区市场克隆智能体到自己的工作区。"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "未登录")
    repo = request.app.state.custom_repo
    source = repo.get(agent_id)
    if not source or (not source.is_public and source.user_id != user_id):
        raise HTTPException(404, "智能体不存在或不可克隆")
    # 克隆：复制配置 + 标记为 cloned
    cloned = repo.create(
        user_id,
        name=f"{source.name} (克隆)",
        description=source.description,
        icon=source.icon,
        system_prompt=source.system_prompt,
        skills=source.skills,
        mcp_servers=source.mcp_servers,
        welcome_message=source.welcome_message,
        temperature=source.temperature,
        is_public=False,
        status="draft",
    )
    return asdict(cloned)


# ===== Phase 4: 对话质量反馈 =====

class FeedbackRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    rating: str = Field("bad", pattern="^(good|bad)$")
    issue_type: str = Field("other", pattern="^(inaccurate|tool_error|delegation_error|other)$")
    comment: str = Field("", max_length=1000)
    agent_id: str = Field("")
    message_snippet: str = Field("", max_length=500)


@app.post("/api/feedback")
async def submit_feedback(req: FeedbackRequest, request: Request) -> dict:
    """提交对话质量反馈（👍/👎）。"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "未登录")
    repo = FeedbackRepository()
    feedback_id = repo.record(
        session_id=req.session_id,
        user_id=user_id,
        rating=req.rating,
        issue_type=req.issue_type,
        comment=req.comment,
        agent_id=req.agent_id,
        message_snippet=req.message_snippet,
    )
    return {"status": "ok", "id": feedback_id}


# ===== 会话管理 =====

@app.post("/api/sessions")
async def create_session(request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    session_id = os.urandom(8).hex()
    # P1-10：通过 SessionRepository 持久化会话（同时写 sessions + tasks 行）
    from infrastructure.persistence.session_repository import SessionRepository
    SessionRepository.create(session_id, user_id)
    return {"session_id": session_id, "user_id": user_id}


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str, request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    agent.delete_session(session_id, user_id=user_id)
    return {"detail": "已删除"}


# ===== ★ 多方案确认/撤销 API =====

@app.post("/api/session/{session_id}/confirm-plan")
async def confirm_plan(session_id: str, request: Request) -> dict:
    """确认方案 —— 并发安全设计（幂等 + 409 冲突）"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    body = await request.json()
    plan_type = str(body.get("plan_type", "")).strip()
    itinerary_id = str(body.get("itinerary_id", "")).strip()
    if plan_type not in ("sightseeing", "budget"):
        return JSONResponse(status_code=400, content={"error": "plan_type 必须为 sightseeing 或 budget"})

    from infrastructure.persistence.database import get_connection
    from datetime import datetime
    conn = get_connection()
    try:
        # 查询当前确认状态
        row = conn.execute(
            "SELECT confirmed_plan FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            return JSONResponse(status_code=404, content={"error": "session not found"})

        current = row["confirmed_plan"]
        # 幂等：已确认同一个方案
        if current == plan_type:
            return {"message": "already confirmed", "plan_type": plan_type, "itinerary_id": itinerary_id}

        # 冲突：已确认不同方案
        if current is not None and current != "":
            return JSONResponse(status_code=409, content={
                "error": "已确认其他方案，如需更换请先撤销",
                "current_confirmed": current,
                "hint": "调用 POST /api/session/{session_id}/revoke-confirm 撤销后重新选择",
            })

        # 更新确认状态
        now = datetime.now().isoformat()
        conn.execute(
            "UPDATE sessions SET confirmed_plan = ?, confirmed_at = ? WHERE session_id = ?",
            (plan_type, now, session_id),
        )
        # 同步更新 itinerary 的确认状态
        if itinerary_id:
            conn.execute(
                "UPDATE itineraries SET confirmed_plan = ?, confirmed_at = ? WHERE id = ?",
                (plan_type, now, itinerary_id),
            )
        conn.commit()
        return {"confirmed_plan": plan_type, "itinerary_id": itinerary_id, "confirmed_at": now}
    except Exception as e:
        conn.rollback()
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/session/{session_id}/revoke-confirm")
async def revoke_confirm(session_id: str, request: Request) -> dict:
    """撤销确认 —— 恢复所有按钮为可点击态"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    body = await request.json()
    itinerary_id = str(body.get("itinerary_id", "")).strip()

    from infrastructure.persistence.database import get_connection
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT confirmed_plan FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if not row or not row["confirmed_plan"]:
            return JSONResponse(status_code=404, content={"error": "无确认记录可撤销"})

        conn.execute(
            "UPDATE sessions SET confirmed_plan = NULL, confirmed_at = NULL WHERE session_id = ?",
            (session_id,),
        )
        if itinerary_id:
            conn.execute(
                "UPDATE itineraries SET confirmed_plan = NULL, confirmed_at = NULL WHERE id = ?",
                (itinerary_id,),
            )
        conn.commit()
        return {"message": "确认已撤销，可重新选择方案"}
    except Exception as e:
        conn.rollback()
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/session/{session_id}/confirm-status")
async def get_confirm_status(session_id: str) -> dict:
    """查询会话的方案确认状态"""
    from infrastructure.persistence.database import get_connection
    conn = get_connection()
    row = conn.execute(
        "SELECT confirmed_plan, confirmed_at FROM sessions WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if not row:
        return JSONResponse(status_code=404, content={"error": "session not found"})

    # 查找关联的 itinerary_id
    itinerary_row = conn.execute(
        "SELECT id FROM itineraries WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
        (session_id,),
    ).fetchone()

    result: dict = {
        "confirmed_plan": row["confirmed_plan"] if row["confirmed_plan"] else None,
        "confirmed_at": row["confirmed_at"] if row["confirmed_at"] else None,
    }
    if itinerary_row:
        result["itinerary_id"] = itinerary_row["id"]
    return result


@app.get("/api/memories")
async def get_memories(request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    from domain.memory.manager import DualLayerMemoryManager
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
    from infrastructure.persistence.database import get_connection
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
        from infrastructure.persistence.health import check_health
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


# ===== 新闻热搜收藏 =====

class NewsFavoriteRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    summary: str = Field("", max_length=500)
    content: str = Field("", max_length=5000)
    url: str = Field("", max_length=1000)
    source: str = Field("", max_length=32)
    tag: str = Field("", max_length=32)


@app.get("/api/news/favorites")
async def list_news_favorites(request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    from infrastructure.persistence.database import get_connection
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, title, summary, content, url, source, tag, created_at "
        "FROM news_favorites WHERE user_id = ? ORDER BY id DESC",
        (user_id,),
    ).fetchall()
    favorites = [{
        "id": r["id"], "title": r["title"], "summary": r["summary"],
        "content": r["content"], "url": r["url"], "source": r["source"], "tag": r["tag"],
        "created_at": r["created_at"],
    } for r in rows]
    return {"favorites": favorites}


@app.post("/api/news/favorites")
async def add_news_favorite(req: NewsFavoriteRequest, request: Request) -> dict:
    """收藏一条新闻，同时写入 short_term_memories 让智能体能检索到。"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    from infrastructure.persistence.database import get_connection
    from datetime import datetime
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO news_favorites (user_id, title, summary, content, url, source, tag, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, req.title, req.summary, req.content, req.url, req.source, req.tag, now),
        )
        # 同步写入 short_term_memories，让 agent 在对话中能引用用户关注的新闻
        memory_content = f"用户收藏的新闻：{req.title}。{req.content or req.summary}"
        conn.execute(
            "INSERT INTO short_term_memories (user_id, category, content, experience_tag, created_at) "
            "VALUES (?, 'news', ?, ?, ?)",
            (user_id, memory_content, req.tag or "news"),
        )
        conn.commit()
    except Exception as e:
        # UNIQUE 约束冲突 = 已收藏，幂等返回成功
        if "UNIQUE" in str(e) or "unique" in str(e):
            return {"status": "already_favorited", "title": req.title}
        logger.error("Add news favorite failed: %s", e)
        return JSONResponse(status_code=500, content={"detail": "收藏失败"})
    return {"status": "ok", "title": req.title}


@app.delete("/api/news/favorites/{favorite_id}")
async def delete_news_favorite(favorite_id: int, request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    from infrastructure.persistence.database import get_connection
    conn = get_connection()
    conn.execute("DELETE FROM news_favorites WHERE id = ? AND user_id = ?", (favorite_id, user_id))
    conn.commit()
    return {"detail": "已取消收藏"}


from domain.travel.itinerary.repository import ItineraryRepository

_itinerary_repo = ItineraryRepository()


def _user_owns_itinerary(user_id: str, itin) -> bool:
    if itin.user_id and itin.user_id == user_id:
        return True
    if itin.session_id:
        from infrastructure.persistence.database import get_connection
        conn = get_connection()
        row = conn.execute(
            "SELECT 1 FROM tasks WHERE user_id = ? AND session_id = ? LIMIT 1",
            (user_id, itin.session_id),
        ).fetchone()
        if row:
            return True
    if itin.user_id:
        from domain.user.auth.auth import UserStore
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
        from domain.travel.itinerary.schema import Itinerary as Itin, DayPlan, Activity
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
    from infrastructure.persistence.database import get_connection
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
            from domain.travel.itinerary.schema import Itinerary
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
from domain.travel.album.service import AlbumService
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
    # P0-6：<img> 标签无法携带 Authorization header，本端点在 _PUBLIC_PREFIXES 中跳过全局中间件，
    # 此处自行校验 query token。建议未来引入一次性 token 或短时效 token（见 FIX_DEV_GUIDE P0-6）。
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        token = request.query_params.get("token", "")
        if token:
            user_id = verify_token(token)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    full_path = settings.data_dir / "album" / file_path
    if not full_path.exists():
        return JSONResponse(status_code=404, content={"detail": "文件不存在"})
    return FastAPIFileResponse(str(full_path))
