# infrastructure/mcp/servers/arxiv/ — 模块记忆

## 职责定位
arXiv 学术搜索 MCP 服务声明：论文检索、摘要获取、批量摘要、引用图谱（Semantic Scholar）。配合 `mcp/runtime.py` 内置 adapter 可实际执行，无需 API Key。

## 关键文件
- `SERVER_METADATA.json`：identifier `arxiv`，描述 arXiv 搜索 + 引用分析。
- `INSTRUCTIONS.md`：使用说明。
- `tools/`：四个工具声明（见其 memory.md）。

## 业务边界要点
- arXiv API 强制 3 秒请求间隔（全局锁 + asyncio.Lock）。
- `max_results` 上限 50；`paper_id` 自动去版本号 `vN`。
- 是学术 Agent 唯一允许的事实检索来源之一（学术边界：仅 arXiv/论文数据库）。
