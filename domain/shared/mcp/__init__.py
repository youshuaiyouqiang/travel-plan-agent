"""MCP 端口与供应商无关的目录/运行时抽象。

P4.3 引入：``MCPCatalogPort`` / ``MCPProxyRuntimePort`` 抽象 MCP 工具发现
与执行能力，使 domain 层不再直接依赖 ``infrastructure.mcp.*``。具体 MCP
服务器扫描（读盘）和适配器实现（HTTP/搜索/论文检索）仍留在
``infrastructure/mcp/``。

端口设计遵循 ``docs/superpowers/plans/2026-07-25-architecture-cleanup.md``
§4.P4：端口不得暴露 ``build_specs()`` / ``build_handlers()`` 等装配细节；
组合根负责装配工具，domain 只消费目录查询和运行时探测能力。
"""
