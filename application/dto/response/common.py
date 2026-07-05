from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ApiResponse(BaseModel):
    code: int = Field(default=0, description="状态码")
    message: str = Field(default="success", description="响应消息")
    data: Any = Field(default=None, description="响应数据")


class ErrorResponse(BaseModel):
    code: int = Field(description="错误码")
    message: str = Field(description="错误消息")
    details: dict | None = Field(default=None, description="错误详情")
    trace_id: str | None = Field(default=None, description="追踪ID")
