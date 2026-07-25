/**
 * Task 3 chat 领域类型 — 收紧 SSE 事件判别联合，避免 ``any``。
 *
 * 设计要点：
 * - 计划（plans/2026-07-17-academic-frontend-quality.md Task 3）声明的核心四类事件：
 *   ``chunk`` / ``route`` / ``error`` / ``done``，data 字段为强类型
 * - 后端 ``orchestrator.py`` / ``dynamic_agent.py`` / ``travel/agent.py`` 仍会发出
 *   ``tool_status`` / ``need_input`` / ``actions`` / ``control_returned`` / ``status`` 事件；
 *   为避免静默丢失既有 UX（思考步骤、追问、操作卡片、控制器归还），本联合一并纳入这些事件
 *   并收紧 data 形状，禁止 ``any``
 * - ``route`` 事件携带 ``{ agent_id, delegated }``，可同时表达委派与控制归还
 *   （``delegated=false`` 且 ``agent_id=null`` 即等价于旧 ``control_returned``）
 */

import type { EvidenceCard } from '../news/api'

/** 流式回复中的文本增量；前端按顺序拼接即可。 */
export interface StreamChunkEvent {
  type: 'chunk'
  data: string
}

/** 委派事件：当前轮委派给专业 Agent，或交还云合。 */
export interface StreamRouteEvent {
  type: 'route'
  data: {
    /** 被委派的 Agent ID；交还云合时为 ``null``。 */
    agent_id: string | null
    /** 是否发生了实际委派。 */
    delegated: boolean
  }
}

/** 错误事件：携带错误码与可展示文案。 */
export interface StreamErrorEvent {
  type: 'error'
  data: {
    code: string
    message: string
  }
}

/** 完成事件：当前轮处理完成，控制器按调度规则归还。 */
export interface StreamDoneEvent {
  type: 'done'
  data: {
    /** 实际处理本轮的 Agent ID；后端旧格式可能传 ``"need_input"`` 等字符串。 */
    handled_by: string
    /** 下一轮控制器：默认归还云合，或继续锁定 Agent。 */
    next_controller: 'yunhe' | 'locked_agent'
  }
}

/** 工具调用思考步骤：data 为可展示的状态文本。 */
export interface StreamToolStatusEvent {
  type: 'tool_status'
  data: string
}

/**
 * 动态 Agent 追问事件。
 *
 * 后端可能发出多种 data 形态：
 * - ``string``：已构造好的问题文案
 * - ``string[]``：缺失字段列表（如 ``["destination", "date"]``）
 * - ``{ question: string; field?: string }``：文档示例形态
 */
export interface StreamNeedInputEvent {
  type: 'need_input'
  data: string | string[] | { question: string; field?: string }
}

/** Agent 操作建议卡片；与 ``AgentAction`` 结构保持一致，``type`` 当前固定为 ``"navigate"``。 */
export interface StreamActionsEvent {
  type: 'actions'
  data: Array<{
    type: 'navigate'
    label: string
    path: string
    agent: string
    description: string
  }>
}

/** 控制器归还事件（旧格式）：data 为接管的 Agent ID（如 ``"yunhe"``）。 */
export interface StreamControlReturnedEvent {
  type: 'control_returned'
  data: string
}

/** 通用状态事件：thinking 状态文本，前端通常仅用于调试展示。 */
export interface StreamStatusEvent {
  type: 'status'
  data: string
}

/**
 * 结构化 evidence 卡片事件。
 *
 * 由后端 ``/api/v1/chat/stream`` 在 ``news_analysis_locked`` 会话且
 * :class:`NewsAnalysisService` 已注入时主动推送；data 为
 * :interface:`EvidenceCard` 数组（含 ``source_id``，可跳转到来源人工审核页）。
 *
 * 业务红线：
 * - 卡片为空数组也表示"无证据"而非事件丢失；前端组件应据此统一渲染占位。
 * - 仅在新闻研判会话推送，其他模式不会触发该事件。
 */
export interface StreamEvidenceEvent {
  type: 'evidence'
  data: EvidenceCard[]
}

/** SSE 事件判别联合 — 涵盖后端当前所有事件类型，data 字段均为强类型。 */
export type StreamEvent =
  | StreamChunkEvent
  | StreamRouteEvent
  | StreamErrorEvent
  | StreamDoneEvent
  | StreamToolStatusEvent
  | StreamNeedInputEvent
  | StreamActionsEvent
  | StreamControlReturnedEvent
  | StreamStatusEvent
  | StreamEvidenceEvent
