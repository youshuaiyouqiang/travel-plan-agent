/**
 * Task 4 前端认证客户端测试。
 *
 * 覆盖范围：
 * - AuthClient 不向 localStorage / sessionStorage 持久化 token
 * - 所有请求附带 credentials: 'include'，让浏览器自动发送 cookie
 * - 对不安全方法（POST/PUT/PATCH/DELETE）自动注入 X-CSRF-Token header
 * - CSRF token 从 csrf_token cookie 读取
 */

import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { AuthClient } from './client'

describe('AuthClient', () => {
  let originalFetch: typeof globalThis.fetch
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    originalFetch = globalThis.fetch
    fetchMock = vi.fn(async () => new Response('{"ok":true}', { status: 200 }))
    globalThis.fetch = fetchMock as unknown as typeof globalThis.fetch
    localStorage.clear()
    sessionStorage.clear()
    document.cookie = 'csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/'
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    localStorage.clear()
    sessionStorage.clear()
    document.cookie = 'csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/'
  })

  it('does not persist an authentication token in browser storage', async () => {
    const client = new AuthClient()
    await client.request('/api/v1/sessions')
    expect(localStorage.getItem('token')).toBeNull()
    expect(sessionStorage.getItem('token')).toBeNull()
    expect(localStorage.getItem('auth_token')).toBeNull()
    expect(sessionStorage.getItem('auth_token')).toBeNull()
  })

  it('attaches credentials to requests', async () => {
    const client = new AuthClient()
    await client.request('/api/v1/sessions')
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [, init] = fetchMock.mock.calls[0]
    expect(init?.credentials).toBe('include')
  })

  it('does not add CSRF header for safe methods (GET/HEAD/OPTIONS)', async () => {
    const client = new AuthClient()
    document.cookie = 'csrf_token=csrf-value-123; path=/'
    await client.request('/api/v1/sessions')
    const [, init] = fetchMock.mock.calls[0]
    const headers = new Headers(init?.headers)
    expect(headers.has('X-CSRF-Token')).toBe(false)
  })

  it('adds matching X-CSRF-Token header for POST requests', async () => {
    const client = new AuthClient()
    document.cookie = 'csrf_token=csrf-value-123; path=/'
    await client.request('/api/v1/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
    const [, init] = fetchMock.mock.calls[0]
    const headers = new Headers(init?.headers)
    expect(headers.get('X-CSRF-Token')).toBe('csrf-value-123')
  })

  it('adds X-CSRF-Token header for PATCH/PUT/DELETE', async () => {
    const client = new AuthClient()
    document.cookie = 'csrf_token=csrf-patch; path=/'
    for (const method of ['PATCH', 'PUT', 'DELETE']) {
      await client.request('/api/v1/sessions/abc', { method })
      const call = fetchMock.mock.calls[fetchMock.mock.calls.length - 1]
      const [, init] = call
      const headers = new Headers(init?.headers)
      expect(headers.get('X-CSRF-Token')).toBe('csrf-patch')
    }
  })

  it('omits X-CSRF-Token header when csrf cookie is missing', async () => {
    const client = new AuthClient()
    await client.request('/api/v1/sessions', { method: 'POST' })
    const [, init] = fetchMock.mock.calls[0]
    const headers = new Headers(init?.headers)
    expect(headers.has('X-CSRF-Token')).toBe(false)
  })

  it('preserves caller-supplied headers while injecting CSRF', async () => {
    const client = new AuthClient()
    document.cookie = 'csrf_token=csrf-xyz; path=/'
    await client.request('/api/v1/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Trace-Id': 't1' },
      body: JSON.stringify({}),
    })
    const [, init] = fetchMock.mock.calls[0]
    const headers = new Headers(init?.headers)
    expect(headers.get('Content-Type')).toBe('application/json')
    expect(headers.get('X-Trace-Id')).toBe('t1')
    expect(headers.get('X-CSRF-Token')).toBe('csrf-xyz')
  })
})
