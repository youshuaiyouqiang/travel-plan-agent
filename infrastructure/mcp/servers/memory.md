# infrastructure/mcp/servers/ — 模块记忆

## 职责定位
MCP 服务的目录式声明仓库：每个子目录一个 server，含 `SERVER_METADATA.json`（元数据）、`INSTRUCTIONS.md`（使用说明）、`tools/*.json`（工具参数声明）。由 `mcp/catalog.py` 扫描加载。

## 子目录
- `arxiv/`：arXiv 论文搜索 + Semantic Scholar 引用分析（有内置 adapter，可执行）。
- `web-search/`：DuckDuckGo 免 Key 网页/新闻搜索（有内置 adapter，可执行）。
- `chrome-devtools/`：浏览器自动化（仅声明，无 adapter）。
- `tencent-docs/`：腾讯文档读写（仅声明，无 adapter）。
- `wecom-doc/`：企业微信待办/消息（仅声明，无 adapter）。

## 关键文件
- `README.md`：目录结构约定与加载优先级（项目本地 > Cursor 项目级 > Cursor 全局）。

## 业务边界要点
- 新增 server 只需添加目录与 JSON 声明；要可执行还需在 `mcp/runtime.py` 的 `build_default_adapters` 登记 adapter。
