/**
 * 认证功能前端 API 客户端。
 *
 * P5.3 从 ``utils/api.ts`` 迁入：register / login。
 * 所有请求统一走 ``features/auth/client.ts`` 的 cookie + CSRF 流程；
 * 浏览器不持有长期认证令牌。
 */
import { AuthClient } from './client'

const API_BASE = '/api'

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

export async function fetchMe(): Promise<AuthResponse | null> {
  // 获取当前登录用户信息，未登录返回 null。
  let res: Response
  try {
    res = await authClient().request(`${API_BASE}/auth/me`)
  } catch {
    return null
  }
  if (!res.ok) {
    return null
  }
  const data = await res.json().catch(() => null)
  if (!data || !data.user_id) {
    return null
  }
  return data as AuthResponse
}
