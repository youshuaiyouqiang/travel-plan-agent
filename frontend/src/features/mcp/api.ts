/**
 * MCP 中心前端 API 客户端。
 *
 * P5.3 从 ``utils/api.ts`` 迁入：fetchMCPServers / fetchMCPServer 及
 * MCPServerInfo / MCPToolInfo 类型。
 * 所有请求统一走 ``features/auth/client.ts`` 的 cookie + CSRF 流程。
 */
import { AuthClient } from '../auth/client'

const API_BASE = '/api'

function authClient(): AuthClient {
  return new AuthClient()
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

export async function fetchMCPServers(): Promise<MCPServerInfo[]> {
  const res = await authClient().request(`${API_BASE}/mcp/servers`)
  if (!res.ok) throw new Error('获取 MCP 列表失败')
  const data = await res.json()
  return data.servers
}

export async function fetchMCPServer(serverId: string): Promise<MCPServerInfo> {
  const res = await authClient().request(`${API_BASE}/mcp/servers/${encodeURIComponent(serverId)}`)
  if (!res.ok) throw new Error('获取 MCP 详情失败')
  return res.json()
}
