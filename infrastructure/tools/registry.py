"""工具注册表再导出垫片（P4.2）.

``ToolRegistry`` 已迁移至 ``domain/shared/tools/registry.py``。本模块仅作
向后兼容垫片，保留 ``app.py``、``infrastructure/tools/adapters/`` 与
测试中既有的 ``from infrastructure.tools.registry import ...`` 写法。

新代码应直接从 ``domain.shared.tools.registry`` 导入。
"""

from __future__ import annotations

from domain.shared.tools.registry import ToolRegistry  # noqa: F401  re-export for backward compatibility

__all__ = ["ToolRegistry"]
