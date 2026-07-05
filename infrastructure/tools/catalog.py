from __future__ import annotations

from .base import ToolSpec


class ToolCatalog:
    """P2-13：工具规格只读视图（与 ToolRegistry 的 spec 部分重叠）。

    保留供测试和外部查询使用；生产路径请优先使用 ToolRegistry
    （其同时持有 spec + handler）。
    """

    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._specs[spec.name] = spec

    def get(self, name: str) -> ToolSpec:
        return self._specs[name]

    def list_specs(self, categories: list[str] | None = None) -> list[ToolSpec]:
        if not categories:
            return sorted(self._specs.values(), key=lambda item: item.name)
        allowed = [spec for spec in self._specs.values() if spec.category in categories or spec.name in categories]
        target = allowed or list(self._specs.values())
        return sorted(target, key=lambda item: item.name)
