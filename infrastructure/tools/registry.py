from __future__ import annotations

from collections.abc import Iterator
from infrastructure.tools.base import Tool, ToolSpec


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
            return sorted(name for name, tool in self._tools.items() if tool.category not in excluded)
        allowed = {
            name
            for name, tool in self._tools.items()
            if (tool.category in hints or name in hints) and tool.category not in excluded
        }
        fallback = [name for name, tool in self._tools.items() if tool.category not in excluded]
        return sorted(allowed or fallback)

    # ===== P1-16：公共 API 替代外部对 _tools 的私有访问 =====

    def get_all_specs(self) -> list[ToolSpec]:
        """返回所有工具的 spec 列表（只读视图）。"""
        return [tool.spec for tool in self._tools.values()]

    def iter_tools(self) -> Iterator[Tool]:
        """迭代所有工具。"""
        return iter(self._tools.values())
