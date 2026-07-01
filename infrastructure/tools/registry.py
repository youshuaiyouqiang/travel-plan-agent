from __future__ import annotations

from tools.base import Tool

class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        return self._tools[name]

    def has(self, name: str) -> bool:
        return name in self._tools

    def list_names(
        self,
        hints: list[str] | None = None,
        *,
        exclude_categories: list[str] | None = None,
    ) -> list[str]:
        excluded = set(exclude_categories or [])
        if not hints:
            return sorted(
                name for name, tool in self._tools.items() if tool.category not in excluded
            )
        allowed = {
            name
            for name, tool in self._tools.items()
            if (tool.category in hints or name in hints) and tool.category not in excluded
        }
        fallback = [
            name for name, tool in self._tools.items() if tool.category not in excluded
        ]
        return sorted(allowed or fallback)


