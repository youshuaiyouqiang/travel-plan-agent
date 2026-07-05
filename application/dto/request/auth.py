from __future__ import annotations

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str = Field(
        min_length=2,
        max_length=32,
        description="用户名",
    )
    password: str = Field(
        min_length=6,
        max_length=128,
        description="密码",
    )


class LoginRequest(BaseModel):
    username: str = Field(description="用户名")
    password: str = Field(description="密码")
