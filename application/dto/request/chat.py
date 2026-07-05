from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(description="会话ID")
    user_id: str | None = Field(default=None, description="用户ID")
    message: str = Field(
        min_length=1,
        max_length=8000,
        description="用户消息",
    )
    agent_id: str | None = Field(default=None, description="智能体ID")
