from __future__ import annotations
from dataclasses import dataclass
from typing import Any,Awaitable,Callable

ToolHandler = Callable[[dict[str,Any]],Awaitable[dict[str,Any]]]


@dataclass
class ToolSpec:
    name: str
    description: str
    category: str
    parameters: dict[str, Any] | None = None

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


