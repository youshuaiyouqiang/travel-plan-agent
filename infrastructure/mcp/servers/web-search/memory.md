# infrastructure/mcp/servers/web-search/ — 模块记忆

## 职责定位
基于 DuckDuckGo 的免 Key 网页/新闻搜索 MCP 服务声明。有内置 adapter（`mcp/runtime.py` 的 `_run_web_search`），可实际执行。

## 关键文件
- `INSTRUCTIONS.md`：详述 `web_search` 与 `news_search` 两工具参数。
- `tools/`：两个工具声明（见其 memory.md）。

## 业务边界要点
- 与内置 `web_search` 工具共享引擎但定位不同：内置为 Agent 日常搜索主路径，本服务面向多节点/外部 MCP 客户端。
- 学术 Agent 被工具策略禁止使用任何网页搜索（学术边界：仅 arXiv/论文数据库）。
