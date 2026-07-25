# frontend/src/features/academic/ — 模块记忆

## 职责定位
学术智能体的前端类型契约层（当前无运行时 API 调用）。

## 关键文件
- `api.ts`：仅导出与后端对齐的类型——`Paper`（论文元数据，不含全文）与 `ResearchContextSummary`（研究段摘要，不含 draft_text 正文）。

## 业务边界要点
- 前端永不接收/渲染论文草稿正文（`draft_text`）；草稿只存在后端会话级 ResearchContext。
