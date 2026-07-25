# infrastructure/mcp/servers/web-search/tools/ — 模块记忆

## 职责定位
Web 搜索 MCP 服务的工具参数声明（JSON Schema）。

## 文件
- `web_search.json`：通用网页搜索。
- `news_search.json`：新闻搜索。

## 业务边界要点
- 实际执行在 `mcp/runtime.py` 内置 adapter（DuckDuckGo）。
- 新闻检索结果只用元数据/摘录，不抓取全文。
