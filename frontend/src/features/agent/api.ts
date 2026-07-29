/**
 * 智能体中心前端 API 客户端。
 *
 * P5.3 从 ``utils/api.ts`` 迁入：fetchAgents / createCustomAgent /
 * updateCustomAgent / deleteCustomAgent / cloneCustomAgent 及 AgentInfo 类型。
 * 所有请求统一走 ``features/auth/client.ts`` 的 cookie + CSRF 流程。
 *
 * 错误处理：``!res.ok`` 时抛 :class:`ApiError`，携带真实 HTTP ``status`` 便于
 * 组件层精确决策（401 → logout、500 → 重试提示等）。旧实现抛固定字符串、
 * 不带 status，会让 ``msg.includes('401')`` 永远不命中，401 无法触发 logout。
 */
import { AuthClient } from '../auth/client'
import { ApiError } from '../auth/errors'

const API_BASE = '/api/v1'

function authClient(): AuthClient {
  return new AuthClient()
}

function jsonHeaders(): HeadersInit {
  return { 'Content-Type': 'application/json' }
}

async function readErrorBody(res: Response): Promise<string> {
  return res.text().catch(() => '')
}

/** 智能体信息（字段与后端 AgentConfig 完全对齐）。 */
export interface AgentInfo {
  id: string
  name: string
  description: string
  icon: string
  source: 'builtin' | 'custom'
  skills?: string[]
  mcp_servers?: string[]
  is_public?: boolean
  status?: string
  created_at?: string
  system_prompt?: string
  welcome_message?: string
  temperature?: number
  user_id?: string
}

export async function fetchAgents(): Promise<{
  builtin: AgentInfo[]
  custom: AgentInfo[]
  public: AgentInfo[]
}> {
  const url = `${API_BASE}/agents`
  const res = await authClient().request(url)
  if (!res.ok) {
    throw new ApiError(res.status, url, await readErrorBody(res), '获取智能体列表失败')
  }
  return res.json()
}

export async function createCustomAgent(data: Partial<AgentInfo>): Promise<AgentInfo> {
  const url = `${API_BASE}/agents/custom`
  const res = await authClient().request(url, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const body = await readErrorBody(res)
    throw new ApiError(res.status, url, body, '创建智能体失败')
  }
  return res.json()
}

export async function updateCustomAgent(agentId: string, data: Partial<AgentInfo>): Promise<AgentInfo> {
  const url = `${API_BASE}/agents/custom/${agentId}`
  const res = await authClient().request(url, {
    method: 'PUT',
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const body = await readErrorBody(res)
    throw new ApiError(res.status, url, body, '更新智能体失败')
  }
  return res.json()
}

export async function deleteCustomAgent(agentId: string): Promise<void> {
  const url = `${API_BASE}/agents/custom/${agentId}`
  const res = await authClient().request(url, {
    method: 'DELETE',
  })
  if (!res.ok) {
    const body = await readErrorBody(res)
    throw new ApiError(res.status, url, body, '删除智能体失败')
  }
}

export async function cloneCustomAgent(agentId: string): Promise<AgentInfo> {
  const url = `${API_BASE}/agents/custom/${agentId}/clone`
  const res = await authClient().request(url, {
    method: 'POST',
  })
  if (!res.ok) {
    const body = await readErrorBody(res)
    throw new ApiError(res.status, url, body, '克隆智能体失败')
  }
  return res.json()
}
