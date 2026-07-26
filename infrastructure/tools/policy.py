"""工具执行策略再导出垫片（P4.2）.

``ToolPolicy`` / ``PolicyMode`` / ``PolicyDecision`` 已迁移至
``domain/shared/tools/policy.py``。本模块仅作向后兼容垫片，保留
``app.py`` 与测试中既有的 ``from infrastructure.tools.policy import ...`` 写法。

新代码应直接从 ``domain.shared.tools.policy`` 导入。
"""

from __future__ import annotations

from domain.shared.tools.policy import (  # noqa: F401  re-export for backward compatibility
    PolicyDecision,
    PolicyMode,
    ToolPolicy,
)

__all__ = ["PolicyDecision", "PolicyMode", "ToolPolicy"]
