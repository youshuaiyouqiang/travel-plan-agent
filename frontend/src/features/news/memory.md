# frontend/src/features/news/ — 模块记忆

## 职责定位
新闻域前端 API：热点获取、研判会话创建、来源审核（管理员）与证据类型契约。

## 关键文件
- `api.ts`：`getHotspots`（只读缓存）、`createAnalysisSession`（创建 news 锁定会话，锁定 Agent 固定为 "news"）、`listNewsSources` / `reviewNewsSource` / `listNewsSourceAudits`（管理员，403 → `FORBIDDEN`）；类型含 `HotspotItem` / `EvidenceCard` / `UnverifiedLead` / `NewsSource` / `SourceStatus`。

## 业务边界要点
- `HotspotItem` 只含标题/来源/URL/摘要/时间——不接收、不传递新闻全文。
- `locked_agent_id` 不接受客户端传入，由后端固定。
- 管理员授权边界由后端 403 强制。
