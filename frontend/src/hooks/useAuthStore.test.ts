/**
 * P0-1 回归测试：浏览器长期认证 Token 不得被 Zustand persist 持久化。
 *
 * 验收要求：
 * - ``useAuthStore`` 持久化到 ``localStorage['yunhe-auth']`` 的内容只允许包含
 *   ``userId`` / ``username`` / ``isAuthenticated`` 三个 UI 展示字段。
 * - 任何位置都不得写入 ``token`` / ``auth_token`` 等长期认证凭据。
 * - ``utils/api.ts`` 的 ``login`` / ``register`` 在成功路径上不得向 localStorage / sessionStorage
 *   写入 token 字段（cookie 由浏览器自动管理，JS 不可读）。
 */
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { useAuthStore } from './useAuthStore'
import { login, register } from '../features/auth/api'

describe('useAuthStore persist (P0-1)', () => {
  let originalFetch: typeof globalThis.fetch
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    originalFetch = globalThis.fetch
    fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ user_id: 'u1', username: 'alice' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    globalThis.fetch = fetchMock as unknown as typeof globalThis.fetch
    localStorage.clear()
    sessionStorage.clear()
    document.cookie = 'csrf_token=csrf-abc; path=/'
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    localStorage.clear()
    sessionStorage.clear()
  })

  it('does not store a token field in the persisted yunhe-auth entry', () => {
    useAuthStore.getState().login('u1', 'alice')
    // zustand persist 同步写入 localStorage
    const raw = localStorage.getItem('yunhe-auth')
    expect(raw).not.toBeNull()
    const parsed = JSON.parse(raw as string)
    // state 字段是 zustand persist 包装层；真实 state 在 .state
    const state = parsed?.state ?? parsed
    expect(state).toBeDefined()
    expect(state).not.toHaveProperty('token')
    expect(state).not.toHaveProperty('auth_token')
    expect(state.userId).toBe('u1')
    expect(state.username).toBe('alice')
    expect(state.isAuthenticated).toBe(true)
  })

  it('does not write any auth token to localStorage or sessionStorage after login()', async () => {
    await login('alice', 'secret123')
    // 登录成功后不得在浏览器存储写入 token 字段
    for (const store of [localStorage, sessionStorage]) {
      for (let i = 0; i < store.length; i++) {
        const key = store.key(i)
        if (key === null) continue
        const value = store.getItem(key) ?? ''
        // 任何 key 不得是 token / auth_token
        expect(key).not.toBe('token')
        expect(key).not.toBe('auth_token')
        // yunhe-auth 内不得包含 token 字段
        if (key === 'yunhe-auth') {
          expect(value).not.toMatch(/"token"\s*:/)
          expect(value).not.toMatch(/"auth_token"\s*:/)
        }
      }
    }
  })

  it('does not write any auth token to localStorage or sessionStorage after register()', async () => {
    await register('alice', 'secret123')
    for (const store of [localStorage, sessionStorage]) {
      for (let i = 0; i < store.length; i++) {
        const key = store.key(i)
        if (key === null) continue
        const value = store.getItem(key) ?? ''
        expect(key).not.toBe('token')
        expect(key).not.toBe('auth_token')
        if (key === 'yunhe-auth') {
          expect(value).not.toMatch(/"token"\s*:/)
          expect(value).not.toMatch(/"auth_token"\s*:/)
        }
      }
    }
  })

  it('login() and register() requests do not include an Authorization header', async () => {
    await login('alice', 'secret123')
    const loginCall = fetchMock.mock.calls[0]
    const [, loginInit] = loginCall
    const loginHeaders = new Headers(loginInit?.headers ?? {})
    expect(loginHeaders.has('Authorization')).toBe(false)

    fetchMock.mockClear()
    await register('alice2', 'secret456')
    const regCall = fetchMock.mock.calls[0]
    const [, regInit] = regCall
    const regHeaders = new Headers(regInit?.headers ?? {})
    expect(regHeaders.has('Authorization')).toBe(false)
  })
})
