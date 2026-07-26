"""工具目录再导出垫片（P4.2）.

``ToolCatalog`` 已迁移至 ``domain/shared/tools/catalog.py``。本模块仅作
向后兼容垫片，保留 ``app.py`` 与测试中既有的
``from infrastructure.tools.catalog import ...`` 写法。

新代码应直接从 ``domain.shared.tools.catalog`` 导入。
"""

from __future__ import annotations

from domain.shared.tools.catalog import ToolCatalog  # noqa: F401  re-export for backward compatibility

__all__ = ["ToolCatalog"]
