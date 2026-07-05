from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Request

from application.exceptions import NotFoundException, UnauthorizedException

router = APIRouter(tags=["skills"])


@router.get("")
async def list_skills(request: Request) -> dict:
    """列出所有技能。"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()
    sp = request.app.state.skill_provider
    return {"skills": [asdict(s) for s in sp.list_skills()]}


@router.get("/{skill_name}")
async def get_skill_detail(skill_name: str, request: Request) -> dict:
    """获取技能详情。"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()
    sp = request.app.state.skill_provider
    skill = sp.get_skill(skill_name)
    if not skill:
        raise NotFoundException("Skill", skill_name)
    return asdict(skill)
