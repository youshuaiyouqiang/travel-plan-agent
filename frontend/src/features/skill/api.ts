/**
 * 技能中心前端 API 客户端。
 *
 * P5.3 从 ``utils/api.ts`` 迁入：fetchSkills / fetchSkillDetail 及 SkillInfo 类型。
 * 所有请求统一走 ``features/auth/client.ts`` 的 cookie + CSRF 流程。
 *
 * 错误处理：抛 :class:`ApiError` 携带真实 HTTP status，便于 401 自动 logout。
 */
import { AuthClient } from '../auth/client'
import { ApiError } from '../auth/errors'

const API_BASE = '/api/v1'

function authClient(): AuthClient {
  return new AuthClient()
}

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

export async function fetchSkills(): Promise<SkillInfo[]> {
  const url = `${API_BASE}/skills`
  const res = await authClient().request(url)
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new ApiError(res.status, url, body, '获取 Skill 列表失败')
  }
  const data = await res.json()
  return data.skills
}

export async function fetchSkillDetail(name: string): Promise<SkillInfo> {
  const url = `${API_BASE}/skills/${encodeURIComponent(name)}`
  const res = await authClient().request(url)
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new ApiError(res.status, url, body, '获取 Skill 详情失败')
  }
  return res.json()
}
