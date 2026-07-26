"""工具执行器再导出垫片（P4.2）.

``ToolExecutor`` 已迁移至 ``domain/shared/tools/executor.py``。本模块仅作
向后兼容垫片，保留 ``app.py``、``domain/travel/services/context_preparer.py``
历史引用与测试中既有的 ``from infrastructure.tools.executor import ...`` 写法。

新代码应直接从 ``domain.shared.tools.executor`` 导入。
"""

from __future__ import annotations

from domain.shared.tools.executor import ToolExecutor  # noqa: F401  re-export for backward compatibility

__all__ = ["ToolExecutor"]
