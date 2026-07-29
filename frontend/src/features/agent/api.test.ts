/**
 * agent api 错误信息含 status code 回归测试。
 *
 * 验收要求：
 * - ``fetchAgents`` 在 401 时抛 ``ApiError`` 且 ``status === 401``，
 *   旧实现抛固定字符串 "获取智能体列表失败" 不带 status，会导致
 *   AgentCenter 的 ``msg.includes('401')`` 永远不命中、无法 logout。
 * - ``fetchAgents`` 在 500 时也抛 ``ApiError``。
 * - 成功路径（200）正常返回数据。
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { fetchAgents, createCustomAgent } from './api'
import { isApiError } from '../auth/errors'

function mockFetchOnce(response: { status: number; body: string; contentType?: string }) {
  const fetchMock = vi.fn(async () =>
    new Response(response.body, {
      status: response.status,
      headers: { 'Content-Type': response.contentType ?? 'application/json' },
    }),
  )
  globalThis.fetch = fetchMock as unknown as typeof globalThis.fetch
  return fetchMock
}

describe('agent/api (Task 3.1 — status-aware errors)', () => {
  let originalFetch: typeof globalThis.fetch

  beforeEach(() => {
    originalFetch = globalThis.fetch
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it('fetchAgents 401 抛 ApiError(status=401)', async () => {
    mockFetchOnce({ status: 401, body: 'unauthorized' })
    await expect(fetchAgents()).rejects.toMatchObject({
      name: 'ApiError',
      status: 401,
    })
  })

  it('fetchAgents 500 抛 ApiError(status=500)', async () => {
    mockFetchOnce({ status: 500, body: 'internal error' })
    try {
      await fetchAgents()
      throw new Error('should have thrown')
    } catch (err) {
      expect(isApiError(err)).toBe(true)
      if (isApiError(err)) {
        expect(err.status).toBe(500)
        expect(err.message).toContain('(500)')
      }
    }
  })

  it('fetchAgents 200 返回数据', async () => {
    mockFetchOnce({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ builtin: [], custom: [], public: [] }),
    })
    const data = await fetchAgents()
    expect(data.builtin).toEqual([])
    expect(data.custom).toEqual([])
    expect(data.public).toEqual([])
  })

  it('createCustomAgent 401 抛 ApiError(status=401)', async () => {
    mockFetchOnce({ status: 401, body: 'unauthorized' })
    try {
      await createCustomAgent({ name: 'x' })
      throw new Error('should have thrown')
    } catch (err) {
      expect(isApiError(err)).toBe(true)
      if (isApiError(err)) expect(err.status).toBe(401)
    }
  })
})
