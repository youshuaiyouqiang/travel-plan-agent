"""工具模型再导出垫片（P4.2）.

纯内存工具模型已迁移至 ``domain/shared/tools/base.py``。本模块仅作
向后兼容垫片，保留 ``app.py``、``infrastructure/tools/adapters/`` 与
测试中既有的 ``from infrastructure.tools.base import ...`` 写法。

新代码应直接从 ``domain.shared.tools.base`` 导入。
"""

from __future__ import annotations

from domain.shared.tools.base import (  # noqa: F401  re-export for backward compatibility
    Tool,
    ToolHandler,
    ToolSpec,
    bind_tool,
)

__all__ = ["Tool", "ToolHandler", "ToolSpec", "bind_tool"]
