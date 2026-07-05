from __future__ import annotations

from pydantic import BaseModel, Field


class ChatResponse(BaseModel):
    status: str = Field(default="completed", description="响应状态")
    reply: str = Field(description="回复内容")
