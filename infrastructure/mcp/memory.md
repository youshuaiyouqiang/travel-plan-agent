# infrastructure/mcp/ — 模块记忆

## 职责定位
MCP（Model Context Protocol）子系统：目录驱动的声明式工具注册 + 代理运行时。扫描 `servers/*/` 的元数据生成工具目录，把 MCP 工具以 `mcp__{server}__{tool}` 统一命名暴露给工具总线。

## 关键文件
- `catalog.py`：`MCPCatalog` 扫描器 + `MCPServerInfo`/`MCPToolInfo`/`MCPToolRef`——目录扫描、`proxy_name` 生成、基于关键词 hint 的工具推荐评分 `select_tool_refs`、`build_prompt_block` 生成提示块。
- `runtime.py`：`MCPProxyRuntime` + `build_default_adapters()` + `build_mcp_proxy_tools()`——内置 web-search（DuckDuckGo）与 arxiv（arXiv API + 3 秒限流）adapter；无 adapter 的工具返回 `adapter_available=False` 友好提示；把 MCP tool 包装为统一 `ToolSpec`/`ToolHandler`。
- `__init__.py`：包占位。

## 业务边界要点
- 工具名带 `mcp__<server>__<tool>` 前缀，避免与内置工具冲突。
- 只有 runtime 登记了 adapter 的 (server, tool) 才有实际执行能力；chrome-devtools/tencent-docs/wecom-doc 仅有目录声明。
- web-search/arxiv 的实际抓取内置在 `runtime.py`，非独立进程。
