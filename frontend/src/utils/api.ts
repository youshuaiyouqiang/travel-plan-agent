/**
 * 通用 API 客户端 — 仅保留未迁入领域模块的函数。
 *
 * 已迁移：
 * - chat/session → ``features/chat/api.ts``（Task 3）
 * - travel（itineraries/share/geocode/drafts/archives）→ ``features/travel/api.ts``（Task 3）
 * - academic → ``features/academic/api.ts``（Task 3，仅类型）
 *
 * 仍保留在本模块：
 * - auth（register/login）
 * - trending、news favorites（``features/news/api.ts`` 由新闻计划维护，不在此处迁移）
 * - memory（计划明确不在本任务中调整）
 * - agent/skill/mcp 中心
 *
 * P0-1 修复：本文件不再使用 Bearer token + ``useAuthStore``；所有请求统一走
 * ``features/auth/client.ts`` 的 cookie + CSRF 流程。浏览器不持有长期认证令牌。
 */
import { AuthClient } from '../features/auth/client'

const API_BASE = '/api'

// 每次调用都构造 AuthClient，使其引用当前 ``globalThis.fetch``。
function authClient(): AuthClient {
  return new AuthClient()
}

function jsonHeaders(): HeadersInit {
  return { 'Content-Type': 'application/json' }
}

export interface AuthResponse {
  user_id: string
  username: string
}

export async function register(username: string, password: string): Promise<AuthResponse> {
  let res: Response
  try {
    res = await authClient().request(`${API_BASE}/auth/register`, {
      method: 'POST',
      headers: jsonHeaders(),
      body: JSON.stringify({ username, password }),
    })
  } catch {
    throw new Error('无法连接到服务器，请检查网络')
  }
  const data = await res.json().catch(() => ({ message: '服务器响应异常' }))
  if (!res.ok) {
    throw new Error(data.message || data.detail || '注册失败')
  }
  return data
}

export async function login(username: string, password: string): Promise<AuthResponse> {
  let res: Response
  try {
    res = await authClient().request(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: jsonHeaders(),
      body: JSON.stringify({ username, password }),
    })
  } catch {
    throw new Error('无法连接到服务器，请检查网络')
  }
  const data = await res.json().catch(() => ({ message: '服务器响应异常' }))
  if (!res.ok) {
    throw new Error(data.message || data.detail || '登录失败')
  }
  return data
}

// ==================== Trending / 新闻收藏（legacy） ====================

export interface TrendingItem {
  title: string
  tag: string
  summary: string
  url?: string
  img?: string
  hotScore?: string
  hotChange?: string
  source?: string
}

export async function getTrending(refresh: boolean = false): Promise<TrendingItem[]> {
  try {
    const url = refresh ? `${API_BASE}/news/trending?refresh=true` : `${API_BASE}/news/trending`
    const res = await authClient().request(url)
    if (!res.ok) return []
    const data = await res.json()
    return data.items || []
  } catch {
    return []
  }
}

export interface NewsFavorite {
  id: number
  title: string
  summary: string
  url: string
  source: string
  tag: string
  created_at: string
}

export async function listNewsFavorites(): Promise<NewsFavorite[]> {
  const res = await authClient().request(`${API_BASE}/news/favorites`)
  if (!res.ok) throw new Error('获取收藏失败')
  const data = await res.json()
  return data.favorites || []
}

export async function addNewsFavorite(item: {
  title: string
  summary?: string
  url?: string
  source?: string
  tag?: string
}): Promise<{ status: string }> {
  const res = await authClient().request(`${API_BASE}/news/favorites`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(item),
  })
  if (!res.ok) throw new Error('收藏失败')
  return res.json()
}

export async function deleteNewsFavorite(favoriteId: number): Promise<void> {
  const res = await authClient().request(`${API_BASE}/news/favorites/${favoriteId}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error('取消收藏失败')
}

// ==================== 记忆 ====================

export interface MemoryItem {
  id: number
  category: string
  category_label: string
  content: string
  experience_tag?: string
  extraction_count: number
  last_accessed_at: string
  created_at: string
}

export interface MemorySummary {
  total_ltm: number
  total_stm: number
  preferences: number
  facts: number
  experiences: number
}

export interface MemoriesResponse {
  long_term: MemoryItem[]
  short_term: MemoryItem[]
  summary: MemorySummary
}

export async function getMemories(): Promise<MemoriesResponse> {
  const res = await authClient().request(`${API_BASE}/memories`)
  if (!res.ok) {
    throw new Error('获取记忆失败')
  }
  return res.json()
}

export async function deleteMemory(memoryType: string, memoryId: number): Promise<void> {
  const res = await authClient().request(`${API_BASE}/memories/${memoryType}/${memoryId}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    throw new Error('删除记忆失败')
  }
}

// ===== Agent 中心 API =====

// 类型定义（字段与后端 AgentConfig 完全对齐）
export interface SkillInfo {
  name: string
  display_name: string
  description: string
  default_prompt: string
  requires_env: string[]
  env_configured: boolean
  icon: string
  tools?: string[]
  category?: string
}

export interface AgentInfo {
  id: string
  name: string
  description: string
  icon: string
  source: 'builtin' | 'custom'    // 与后端 AgentConfig.source 对齐
  skills?: string[]
  mcp_servers?: string[]
  is_public?: boolean
  status?: string                 // Phase 4: draft / published
  created_at?: string
  system_prompt?: string
  welcome_message?: string
  temperature?: number
  user_id?: string
}

export interface MCPToolInfo {
  name: string
  description: string
  proxy_name: string
  input_schema: unknown
  adapter_available: boolean
}

export interface MCPServerInfo {
  identifier: string
  name: string
  description: string
  instructions: string
  tools: MCPToolInfo[]
}

// 获取 skill 列表
export async function fetchSkills(): Promise<SkillInfo[]> {
  const res = await authClient().request(`${API_BASE}/skills`)
  if (!res.ok) throw new Error('获取 Skill 列表失败')
  const data = await res.json()
  return data.skills
}

// 获取单个 skill 详情
export async function fetchSkillDetail(name: string): Promise<SkillInfo> {
  const res = await authClient().request(`${API_BASE}/skills/${encodeURIComponent(name)}`)
  if (!res.ok) throw new Error('获取 Skill 详情失败')
  return res.json()
}

// 获取 MCP Server 列表
export async function fetchMCPServers(): Promise<MCPServerInfo[]> {
  const res = await authClient().request(`${API_BASE}/mcp/servers`)
  if (!res.ok) throw new Error('获取 MCP 列表失败')
  const data = await res.json()
  return data.servers
}

// 获取单个 MCP Server 详情
export async function fetchMCPServer(serverId: string): Promise<MCPServerInfo> {
  const res = await authClient().request(`${API_BASE}/mcp/servers/${encodeURIComponent(serverId)}`)
  if (!res.ok) throw new Error('获取 MCP 详情失败')
  return res.json()
}

// 获取智能体列表
export async function fetchAgents(): Promise<{
  builtin: AgentInfo[]
  custom: AgentInfo[]
  public: AgentInfo[]
}> {
  const res = await authClient().request(`${API_BASE}/agents`)
  if (!res.ok) throw new Error('获取智能体列表失败')
  return res.json()
}

// 创建自定义智能体
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

// 更新自定义智能体
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

// 删除自定义智能体
export async function deleteCustomAgent(agentId: string): Promise<void> {
  const res = await authClient().request(`${API_BASE}/agents/custom/${agentId}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || '删除智能体失败')
  }
}

// 克隆社区智能体
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
