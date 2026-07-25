# application/academic/ — 模块记忆

## 职责定位
学术研究上下文应用层：管理每个会话的临时研究上下文（Research Context），强制论文草稿只存会话、不长期化。

## 关键文件
- `service.py`：`AcademicService`——按会话管理最新研究段（start/switch/get/add/search 论文）；切换研究主题时丢弃旧段（新 `segment_id`），后续检索不携带旧主题的论文与结论。
- `__init__.py`：导出 `AcademicService`。

## 业务边界要点
- 论文草稿（`draft_text`）仅保留在内存中的当前 `ResearchContext`，不提供持久化、长期记忆或审计正文接口。
- 审计只允许使用 `to_audit_summary()` 摘要，禁止把草稿正文写入日志/审计。
- 事实检索只允许 arXiv/论文数据库（端口由 domain/academic/ports.py 定义，基础设施注入）。
