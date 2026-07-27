/**
 * 记忆功能前端 API 客户端。
 *
 * P5.3 从 ``utils/api.ts`` 迁入：getMemories / deleteMemory。
 * 所有请求统一走 ``features/auth/client.ts`` 的 cookie + CSRF 流程。
 */
import { AuthClient } from '../auth/client'

const API_BASE = '/api'

function authClient(): AuthClient {
  return new AuthClient()
}

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
