# infrastructure/mcp/servers/arxiv/tools/ — 模块记忆

## 职责定位
arXiv MCP 服务的工具参数声明（JSON Schema），由 `mcp/catalog.py` 扫描并生成 `mcp__arxiv__*` 代理工具。

## 文件
- `search_papers.json`：关键词 + 分类 + 时间范围搜索论文。
- `get_abstract.json`：获取单篇论文摘要。
- `batch_abstracts.json`：批量获取摘要（单次最多 50 篇）。
- `citation_graph.json`：引用关系图谱（Semantic Scholar）。

## 业务边界要点
- 仅为声明文件；实际执行逻辑在 `mcp/runtime.py` 的内置 adapter。
