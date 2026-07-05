from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Request

from application.dto.request.agent import CreateAgentRequest, UpdateAgentRequest
from application.exceptions import (
    ForbiddenException,
    NotFoundException,
    UnauthorizedException,
)

router = APIRouter(tags=["agents"])


@router.get("")
async def list_agents(request: Request) -> dict:
    """列出所有智能体（内置 + 自定义 + 公开）。"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()
    builtin = [asdict(c) for c in request.app.state.builtin_configs]
    custom = [asdict(c) for c in request.app.state.custom_repo.list_by_user(user_id)]
    public = [asdict(c) for c in request.app.state.custom_repo.list_public()]
    return {"builtin": builtin, "custom": custom, "public": public}


@router.post("/custom")
async def create_custom_agent(req: CreateAgentRequest, request: Request) -> dict:
    """创建自定义智能体。"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()
    config = request.app.state.custom_repo.create(user_id, **req.model_dump())
    return asdict(config)


@router.get("/custom/{agent_id}")
async def get_custom_agent(agent_id: str, request: Request) -> dict:
    """获取自定义智能体详情。"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()
    config = request.app.state.custom_repo.get(agent_id)
    if not config or (config.user_id != user_id and not config.is_public):
        raise NotFoundException("智能体", agent_id)
    return asdict(config)


@router.put("/custom/{agent_id}")
async def update_custom_agent(
    agent_id: str,
    req: UpdateAgentRequest,
    request: Request,
) -> dict:
    """更新自定义智能体。"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()
    repo = request.app.state.custom_repo
    config = repo.get(agent_id)
    if not config or config.user_id != user_id:
        raise ForbiddenException("无权修改")
    updated = repo.update(agent_id, **req.model_dump(exclude_unset=True))
    return asdict(updated)


@router.delete("/custom/{agent_id}")
async def delete_custom_agent(agent_id: str, request: Request) -> dict:
    """删除自定义智能体。"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()
    repo = request.app.state.custom_repo
    config = repo.get(agent_id)
    if not config or config.user_id != user_id:
        raise ForbiddenException("无权删除")
    repo.delete(agent_id)
    return {"status": "deleted"}


@router.post("/custom/{agent_id}/clone")
async def clone_custom_agent(agent_id: str, request: Request) -> dict:
    """从社区市场克隆智能体到自己的工作区。"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()
    repo = request.app.state.custom_repo
    source = repo.get(agent_id)
    if not source or (not source.is_public and source.user_id != user_id):
        raise NotFoundException("智能体", agent_id)
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
