from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CreateAgentRequest(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=64,
        description="智能体名称",
    )
    description: str = Field(
        default="",
        max_length=500,
        description="智能体描述",
    )
    icon: str = Field(
        default="🤖",
        max_length=16,
        description="智能体图标",
    )
    system_prompt: str = Field(
        min_length=1,
        max_length=8000,
        description="系统提示词",
    )
    skills: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="技能列表",
    )
    mcp_servers: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="MCP服务器列表",
    )
    welcome_message: str = Field(
        default="",
        max_length=500,
        description="欢迎消息",
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="温度参数",
    )
    is_public: bool = Field(default=False, description="是否公开")


class UpdateAgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=64, description="智能体名称")
    description: str | None = Field(default=None, max_length=500, description="智能体描述")
    icon: str | None = Field(default=None, max_length=16, description="智能体图标")
    system_prompt: str | None = Field(default=None, min_length=1, max_length=8000, description="系统提示词")
    skills: list[str] | None = Field(default=None, max_length=20, description="技能列表")
    mcp_servers: list[str] | None = Field(default=None, max_length=20, description="MCP服务器列表")
    welcome_message: str | None = Field(default=None, max_length=500, description="欢迎消息")
    temperature: float | None = Field(default=None, ge=0.0, le=2.0, description="温度参数")
    is_public: bool | None = Field(default=None, description="是否公开")
