/**
 * 技能中心前端 API 客户端。
 *
 * P5.3 从 ``utils/api.ts`` 迁入：fetchSkills / fetchSkillDetail 及 SkillInfo 类型。
 * 所有请求统一走 ``features/auth/client.ts`` 的 cookie + CSRF 流程。
 */
import { AuthClient } from '../auth/client'

const API_BASE = '/api'

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
  const res = await authClient().request(`${API_BASE}/skills`)
  if (!res.ok) throw new Error('获取 Skill 列表失败')
  const data = await res.json()
  return data.skills
}

export async function fetchSkillDetail(name: string): Promise<SkillInfo> {
  const res = await authClient().request(`${API_BASE}/skills/${encodeURIComponent(name)}`)
  if (!res.ok) throw new Error('获取 Skill 详情失败')
  return res.json()
}
