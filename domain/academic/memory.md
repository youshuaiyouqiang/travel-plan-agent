# domain/academic/ — 模块记忆

## 职责定位
学术 Agent 领域层：定义论文检索端口（依赖倒置）与会话级临时研究上下文。是本项目分层最干净的子域，可作为新代码范本。

## 关键文件
- `context.py`：`Paper` 实体（仅元数据，不含全文）与 `ResearchContext`（单会话某研究主题的临时上下文，含 `segment_id`，草稿文本只存 `draft_text` 字段不长期化）。
- `ports.py`：`PaperSearchPort`（Protocol）——仅暴露 arXiv/论文库检索能力，由基础设施层实现并注入。
- `__init__.py`：导出 `Paper`、`ResearchContext`、`PaperSearchPort`。

## 业务边界要点
- `draft_text` 严禁写入长期存储或审计日志正文；审计只用 `to_audit_summary()` 摘要。
- 切换研究主题必须丢弃前一段的论文与草稿（独立 `segment_id`，防跨主题污染）。
- 事实检索只允许 arXiv/论文数据库；通用网页搜索由工具层 `ToolPolicy` 拦截，本端口不暴露。
