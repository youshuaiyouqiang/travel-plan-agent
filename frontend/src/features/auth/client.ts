/**
 * Task 4 AuthClient — cookie + CSRF 浏览器认证客户端。
 *
 * 设计要点：
 * - 不向 localStorage / sessionStorage 持久化 token（遵守 AGENTS.md 安全约束）
 * - 所有请求附带 `credentials: 'include'`，让浏览器自动发送 HttpOnly cookie
 * - 对不安全方法（POST/PUT/PATCH/DELETE）从 `csrf_token` cookie 读取值并注入 `X-CSRF-Token` header
 * - 安全方法（GET/HEAD/OPTIONS）不需要 CSRF header
 * - 调用方传入的自定义 header 被保留，CSRF header 自动追加
 */

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])
const CSRF_HEADER = 'X-CSRF-Token'
const CSRF_COOKIE = 'csrf_token'

/** 从 document.cookie 读取指定 cookie 值；不存在返回 null。 */
function readCookie(name: string): string | null {
  if (typeof document === 'undefined' || !document.cookie) return null
  const prefix = `${name}=`
  const parts = document.cookie.split(';')
  for (const raw of parts) {
    const trimmed = raw.trim()
    if (trimmed.startsWith(prefix)) {
      const value = trimmed.slice(prefix.length)
      return decodeURIComponent(value)
    }
  }
  return null
}

export interface AuthClientInit {
  /** 可选：覆盖默认 fetch（便于测试注入）。 */
  fetchImpl?: typeof fetch
}

export class AuthClient {
  private readonly fetchImpl: typeof fetch

  constructor(init: AuthClientInit = {}) {
    this.fetchImpl = init.fetchImpl ?? globalThis.fetch.bind(globalThis)
  }

  /**
   * 发起经过 cookie + CSRF 处理的请求。
   *
   * @param path 请求路径（相对路径或绝对 URL）
   * @param init 标准 fetch init，调用方可传 headers/body 等
   */
  async request(path: string, init: RequestInit = {}): Promise<Response> {
    const method = (init.method ?? 'GET').toUpperCase()
    const headers = new Headers(init.headers ?? {})

    if (!SAFE_METHODS.has(method)) {
      const csrf = readCookie(CSRF_COOKIE)
      if (csrf) {
        // 调用方未显式提供 X-CSRF-Token 时才注入；显式提供则尊重调用方
        if (!headers.has(CSRF_HEADER)) {
          headers.set(CSRF_HEADER, csrf)
        }
      }
    }

    return this.fetchImpl(path, {
      ...init,
      method,
      headers,
      credentials: 'include',
    })
  }
}
