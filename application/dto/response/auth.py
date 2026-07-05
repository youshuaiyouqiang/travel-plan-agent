from __future__ import annotations

from pydantic import BaseModel, Field


class AuthResponse(BaseModel):
    user_id: str = Field(description="用户ID")
    username: str = Field(description="用户名")
    token: str = Field(description="认证令牌")
