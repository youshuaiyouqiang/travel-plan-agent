from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass
class ToolSpec:
    name: str
    description: str  # 完整描述（Level 2）
    category: str
    parameters: dict[str, Any] | None = None

    # === 渐进式披露字段（Phase 1） ===
    short_description: str = ""  # 一句话摘要（Level 0），默认取 description 前 50 字
    disclosure_keywords: list[str] = field(default_factory=list)  # 关键词匹配，用于自动推荐
    confirm_required: bool = False  # 是否需要用户确认（高风险工具）
    tier: str = "standard"  # "core"（始终披露）| "standard"（按需披露）| "advanced"（需确认后披露）
    skill_binding: str = ""  # 该工具属于哪个 skill（用于 skill → tool 映射）
    mcp_source: str = ""  # 该工具来自哪个 MCP server

    def to_summary(self) -> str:
        """Level 0 摘要：name + short_description"""
        return f"- {self.name}: {self.short_description or self.description[:50]}"

    def to_openai_schema(self) -> dict:
        """Level 2 完整 schema：传给 LLM 的 native tool 定义"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters or {"type": "object", "properties": {}},
            },
        }


@dataclass
class Tool:
    spec: ToolSpec
    handler: ToolHandler

    @property
    def name(self) -> str:
        return self.spec.name

    @property
    def description(self) -> str:
        return self.spec.description

    @property
    def category(self) -> str:
        return self.spec.category


def bind_tool(spec: ToolSpec, handler: ToolHandler) -> Tool:
    return Tool(spec=spec, handler=handler)
