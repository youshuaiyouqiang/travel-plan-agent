/**
 * Task 3 academic 领域 API 客户端 — 学术研究上下文的类型契约。
 *
 * 设计要点（来源：plans/2026-07-17-academic-frontend-quality.md Task 1 + Task 3）：
 * - 学术服务 ``AcademicService`` 仅在后端运行；前端不直接调用论文检索/草稿接口
 * - 论文与草稿只存在于当前会话的 ``ResearchContext``，不进入长期记忆或审计正文
 * - 这里只导出与后端 ``Paper`` / ``ResearchContext`` 对齐的 TS 类型，供 UI 与 chat 流事件协同
 * - ``ResearchContextSummary`` 与 ``ResearchContext.to_audit_summary()`` 字段保持一致，不含 ``draft_text``
 */

/** 论文实体（与 ``domain.academic.context.Paper`` 对齐）— 仅元数据，不含全文。 */
export interface Paper {
  id: string
  title: string
  abstract: string
  authors: string[]
  url: string
  published_at: string
}

/**
 * 研究段摘要 — 与后端 ``ResearchContext.to_audit_summary()`` 对齐。
 *
 * 注意：前端永远不应接收或渲染 ``draft_text`` 正文；该字段只存在于后端内存中。
 */
export interface ResearchContextSummary {
  segment_id: string
  session_id: string
  topic: string
  paper_count: number
  has_draft: boolean
}
