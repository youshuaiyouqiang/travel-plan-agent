/**
 * 智能体中心前端 API 客户端。
 *
 * P5.3 从 ``utils/api.ts`` 迁入：fetchAgents / createCustomAgent /
 * updateCustomAgent / deleteCustomAgent / cloneCustomAgent 及 AgentInfo 类型。
 * 所有请求统一走 ``features/auth/client.ts`` 的 cookie + CSRF 流程。
 */
import { AuthClient } from '../auth/client'

const API_BASE = '/api'

function authClient(): AuthClient {
  return new AuthClient()
}

function jsonHeaders(): HeadersInit {
  return { 'Content-Type': 'application/json' }
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
  const res = await authClient().request(`${API_BASE}/agents`)
  if (!res.ok) throw new Error('获取智能体列表失败')
  return res.json()
}

export async function createCustomAgent(data: Partial<AgentInfo>): Promise<AgentInfo> {
  const res = await authClient().request(`${API_BASE}/agents/custom`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || '创建智能体失败')
  }
  return res.json()
}

export async function updateCustomAgent(agentId: string, data: Partial<AgentInfo>): Promise<AgentInfo> {
  const res = await authClient().request(`${API_BASE}/agents/custom/${agentId}`, {
    method: 'PUT',
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || '更新智能体失败')
  }
  return res.json()
}

export async function deleteCustomAgent(agentId: string): Promise<void> {
  const res = await authClient().request(`${API_BASE}/agents/custom/${agentId}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || '删除智能体失败')
  }
}

export async function cloneCustomAgent(agentId: string): Promise<AgentInfo> {
  const res = await authClient().request(`${API_BASE}/agents/custom/${agentId}/clone`, {
    method: 'POST',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || '克隆智能体失败')
  }
  return res.json()
}
