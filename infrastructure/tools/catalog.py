from __future__ import annotations

from .base import ToolSpec


class ToolCatalog:
    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._specs[spec.name] = spec

    def get(self, name: str) -> ToolSpec:
        return self._specs[name]

    def list_specs(self, categories: list[str] | None = None) -> list[ToolSpec]:
        if not categories:
            return sorted(self._specs.values(), key=lambda item: item.name)
        allowed = [
            spec
            for spec in self._specs.values()
            if spec.category in categories or spec.name in categories
        ]
        target = allowed or list(self._specs.values())
        return sorted(target, key=lambda item: item.name)