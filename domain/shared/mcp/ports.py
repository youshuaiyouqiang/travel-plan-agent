"""MCP 目录与运行时端口定义。

P4.3 引入：``MCPCatalogPort`` 抽象 MCP 工具发现与查询能力，
``MCPProxyRuntimePort`` 抽象运行时适配器探测能力。domain 层只依赖端口，
不导入 ``infrastructure.mcp.*`` 的具体实现。

设计约束（plan §4.P4）：
- 端口不得暴露 ``build_specs()`` / ``build_handlers()`` 等装配细节；
  装配由组合根负责。
- 端口方法只覆盖 domain 已消费的能力：目录查询（select/list/get/build_prompt）
  与运行时探测（adapter_available）。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from domain.shared.mcp.types import MCPServerInfo, MCPToolRef


@runtime_checkable
class MCPCatalogPort(Protocol):
    """MCP 工具目录端口 — 只读查询能力。

    实现方（``infrastructure.mcp.catalog.MCPCatalog``）负责从磁盘扫描
    server metadata 并填充内存状态；domain 只消费查询结果。
    """

    def list_servers(self) -> list[MCPServerInfo]:
        """返回所有已发现的 MCP 服务器信息。"""
        ...

    def list_tool_refs(self) -> list[MCPToolRef]:
        """返回所有 MCP 工具的扁平引用列表。"""
        ...

    def get_tool_ref(self, proxy_name: str) -> MCPToolRef | None:
        """按代理工具名查找工具引用；未找到返回 None。"""
        ...

    def select_tool_refs(self, query: str, limit: int = 4) -> list[MCPToolRef]:
        """根据用户消息打分选择 top-N 相关 MCP 工具引用。"""
        ...

    def build_prompt_block(
        self,
        *,
        query: str = "",
        limit: int = 4,
        tool_refs: list[MCPToolRef] | None = None,
    ) -> str:
        """构建注入 system prompt 的 MCP 工具说明块。"""
        ...


@runtime_checkable
class MCPProxyRuntimePort(Protocol):
    """MCP 运行时端口 — 适配器可用性探测。

    实现方（``infrastructure.mcp.runtime.MCPProxyRuntime``）持有具体 HTTP/
    搜索/论文检索适配器；domain 只探测是否可用，不直接调用适配器。
    工具实际调用由 ``ToolExecutor`` 经由注册的 handler 完成。
    """

    def adapter_available(self, proxy_name: str) -> bool:
        """检查指定代理工具是否有运行时适配器可用。"""
        ...


class NullMCPCatalog:
    """``MCPCatalogPort`` 的空实现 — 返回空结果，不发现任何 MCP 工具。

    Null Object 模式：当组合根未注入具体目录时（例如测试或无 MCP 配置的
    部署），domain 使用本实例作为安全默认值，避免在 domain 中实例化
    ``infrastructure.mcp.catalog.MCPCatalog`` 造成跨层依赖。
    """

    def list_servers(self) -> list[MCPServerInfo]:
        return []

    def list_tool_refs(self) -> list[MCPToolRef]:
        return []

    def get_tool_ref(self, proxy_name: str) -> MCPToolRef | None:
        return None

    def select_tool_refs(self, query: str, limit: int = 4) -> list[MCPToolRef]:
        return []

    def build_prompt_block(
        self,
        *,
        query: str = "",
        limit: int = 4,
        tool_refs: list[MCPToolRef] | None = None,
    ) -> str:
        return ""
