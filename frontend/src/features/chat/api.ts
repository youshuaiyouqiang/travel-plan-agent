/**
 * Task 3 chat 领域 API 客户端 — 与 ``/api/v1/chat/*``、``/api/v1/sessions/*`` 端点交互。
 *
 * 设计要点（来源：plans/2026-07-17-academic-frontend-quality.md Task 3）：
 * - 不接受/不发送客户端 ``user_id``：用户身份只能从服务端认证上下文（cookie/Bearer）取得
 * - 请求体仅包含 ``session_id`` 与 ``message``；其他业务字段（如 ``agent_id``）由后端基于会话模式决定
 * - 使用 ``features/auth/client.ts`` 共享 cookie + CSRF 流程，不再向 localStorage 持久化 token
 * - SSE 事件按 ``StreamEvent`` 判别联合解析（chunk/route/error/done/tool_status/need_input/actions/control_returned/status）；
 *   解析失败或事件 data 形态不符合契约的行被忽略
 */
import { AuthClient } from '../auth/client'
import type { StreamActionsEvent, StreamEvent } from './types'

const API_BASE = '/api/v1'

// 每次调用都构造 AuthClient，使其引用当前 ``globalThis.fetch``；
// 测试可在 ``beforeEach`` 中替换 fetch 后再调用本模块函数。
function authClient(): AuthClient {
  return new AuthClient()
}

function jsonHeaders(): HeadersInit {
  return { 'Content-Type': 'application/json' }
}

// ==================== 会话管理 ====================

export type SessionMode = 'yunhe_default' | 'agent_locked' | 'news_analysis_locked'

export interface SessionInfo {
  session_id: string
  title: string
  created_at: string
  updated_at: string
  message_count: number
}

export interface SessionCreateResult {
  session_id: string
  user_id: string
  mode: SessionMode
  locked_agent_id: string | null
  news_id: string | null
}

export async function listSessions(): Promise<SessionInfo[]> {
  const res = await authClient().request(`${API_BASE}/sessions`)
  if (!res.ok) {
    throw new Error('获取会话列表失败')
  }
  const data = await res.json()
  return data.sessions || []
}

export async function createSession(
  options?: { mode?: SessionMode; locked_agent_id?: string },
): Promise<SessionCreateResult> {
  const body =
    options && (options.mode || options.locked_agent_id)
      ? {
          mode: options.mode ?? 'yunhe_default',
          ...(options.locked_agent_id ? { locked_agent_id: options.locked_agent_id } : {}),
        }
      : undefined
  const res = await authClient().request(`${API_BASE}/sessions`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    throw new Error('创建会话失败')
  }
  const payload = await res.json()
  // 后端统一响应：{ code, message, data }
  return payload?.data ?? payload
}

export async function updateSessionMode(
  sessionId: string,
  mode: SessionMode,
  lockedAgentId?: string,
): Promise<SessionCreateResult> {
  const body: Record<string, unknown> = { mode }
  if (lockedAgentId) body.locked_agent_id = lockedAgentId
  const res = await authClient().request(`${API_BASE}/sessions/${sessionId}/mode`, {
    method: 'PATCH',
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    throw new Error('更新会话模式失败')
  }
  const payload = await res.json()
  return payload?.data ?? payload
}

export async function deleteSession(sessionId: string): Promise<void> {
  const res = await authClient().request(`${API_BASE}/sessions/${sessionId}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    throw new Error('删除会话失败')
  }
}

export interface SessionMessage {
  id: number
  session_id: string
  role: string
  content: string
  agent_id?: string
  created_at: string
  [key: string]: unknown
}

export async function getSessionMessages(sessionId: string): Promise<SessionMessage[]> {
  const res = await authClient().request(`${API_BASE}/sessions/${sessionId}/messages`)
  if (!res.ok) {
    throw new Error('获取消息失败')
  }
  const data = await res.json()
  return data.messages || []
}

// ==================== 流式对话 ====================


/** ``sendMessageStream`` 输入；不包含 ``user_id`` 等身份字段。 */
export interface ChatStreamInput {
  session_id: string
  message: string
}

/** 兼容字段名（前端旧代码可能传入）：仅取 ``session_id`` 与 ``message``。 */
export interface ChatStreamLegacyInput {
  session_id: string
  message: string
  /** 显式忽略：用户身份只能来自服务端。 */
  user_id?: unknown
  /** 显式忽略：委派由后端会话模式决定。 */
  agent_id?: unknown
}

/**
 * 发起流式对话请求。
 *
 * 调用方仅提供 ``session_id`` 与 ``message``；其他身份字段一律忽略，
 * 由后端从认证上下文与 ``SessionService`` 中解析。
 */
export async function* sendMessageStream(
  input: ChatStreamInput | ChatStreamLegacyInput,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  // 严格只发送 session_id 与 message；忽略任何 caller 传入的 user_id / agent_id
  const body = JSON.stringify({
    session_id: input.session_id,
    message: input.message,
  })

  const res = await authClient().request(`${API_BASE}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
    signal,
  })

  if (!res.ok) {
    if (res.status === 401) {
      throw new Error('AUTH_EXPIRED')
    }
    if (res.status === 429) {
      throw new Error('请求过于频繁，请稍后再试')
    }
    throw new Error(`请求失败 (${res.status})`)
  }

  const reader = res.body?.getReader()
  if (!reader) {
    throw new Error('无法读取流式响应')
  }

  const decoder = new TextDecoder()
  let buffer = ''

  // 解析判别联合中声明的所有事件类型；data 字段为强类型，禁止 any
  function tryParse(line: string): StreamEvent | null {
    const trimmed = line.trim()
    if (!trimmed || !trimmed.startsWith('data: ')) return null
    const jsonStr = trimmed.slice(6)
    try {
      const raw = JSON.parse(jsonStr) as { type?: unknown; data?: unknown }
      switch (raw.type) {
        case 'chunk':
          if (typeof raw.data === 'string') {
            return { type: 'chunk', data: raw.data }
          }
          return null
        case 'route':
          if (
            raw.data &&
            typeof raw.data === 'object' &&
            'agent_id' in raw.data &&
            'delegated' in raw.data
          ) {
            const d = raw.data as { agent_id: string | null; delegated: boolean }
            return {
              type: 'route',
              data: {
                agent_id: d.agent_id,
                delegated: Boolean(d.delegated),
              },
            }
          }
          return null
        case 'error': {
          if (raw.data && typeof raw.data === 'object') {
            const d = raw.data as { code?: string; message?: string }
            return {
              type: 'error',
              data: {
                code: typeof d.code === 'string' ? d.code : 'UNKNOWN',
                message: typeof d.message === 'string' ? d.message : '未知错误',
              },
            }
          }
          // 兼容后端旧格式：error.data 为字符串
          if (typeof raw.data === 'string') {
            return { type: 'error', data: { code: 'UNKNOWN', message: raw.data } }
          }
          return null
        }
        case 'done':
          if (raw.data && typeof raw.data === 'object') {
            const d = raw.data as {
              handled_by?: string
              next_controller?: string
            }
            const nextController = d.next_controller === 'locked_agent' ? 'locked_agent' : 'yunhe'
            return {
              type: 'done',
              data: {
                handled_by: typeof d.handled_by === 'string' ? d.handled_by : '',
                next_controller: nextController,
              },
            }
          }
          // 兼容后端旧格式：done.data 为字符串（如 "completed" / "need_input" / "escalated"）
          if (typeof raw.data === 'string') {
            return {
              type: 'done',
              data: { handled_by: raw.data, next_controller: 'yunhe' },
            }
          }
          return null
        case 'tool_status':
          if (typeof raw.data === 'string') {
            return { type: 'tool_status', data: raw.data }
          }
          return null
        case 'need_input': {
          const d = raw.data
          if (typeof d === 'string' || Array.isArray(d)) {
            return { type: 'need_input', data: d }
          }
          if (d && typeof d === 'object' && typeof (d as { question?: unknown }).question === 'string') {
            return { type: 'need_input', data: d as { question: string; field?: string } }
          }
          return null
        }
        case 'actions':
          if (Array.isArray(raw.data)) {
            return { type: 'actions', data: raw.data as StreamActionsEvent['data'] }
          }
          return null
        case 'control_returned':
          if (typeof raw.data === 'string') {
            return { type: 'control_returned', data: raw.data }
          }
          return null
        case 'status':
          if (typeof raw.data === 'string') {
            return { type: 'status', data: raw.data }
          }
          return null
        default:
          return null
      }
    } catch {
      return null
    }
  }

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      const event = tryParse(line)
      if (event) yield event
    }
  }

  // 处理剩余 buffer
  if (buffer.trim()) {
    const event = tryParse(buffer)
    if (event) yield event
  }
}
