/**
 * ApiError 单测 — 修复"获取智能体列表失败"无状态码的回归测试。
 *
 * 验收要求：
 * - 构造 ``ApiError`` 时，``status`` 字段保留数值
 * - ``message`` 包含 ``(status)`` 状态码便于日志排查
 * - ``isApiError`` 精确识别 ApiError 实例
 * - ``extractStatus`` 从 ApiError 取 status，从普通 Error 返回 null
 */

import { describe, it, expect } from 'vitest'
import { ApiError, isApiError, extractStatus } from './errors'

describe('ApiError (Task 3.1 — status-aware API errors)', () => {
  it('preserves status as a number', () => {
    const err = new ApiError(401, '/api/v1/agents', 'unauthorized', '获取智能体列表失败')
    expect(err.status).toBe(401)
    expect(err.url).toBe('/api/v1/agents')
    expect(err.name).toBe('ApiError')
  })

  it('message includes "(status)" and trimmed body', () => {
    const err = new ApiError(401, '/api/v1/agents', 'unauthorized', '获取智能体列表失败')
    expect(err.message).toContain('(401)')
    expect(err.message).toContain('unauthorized')
  })

  it('message omits body when body is empty', () => {
    const err = new ApiError(500, '/api/v1/x', '', '失败')
    expect(err.message).toBe('失败 (500)')
  })

  it('message truncates body longer than 200 chars with ellipsis', () => {
    const longBody = 'x'.repeat(300)
    const err = new ApiError(500, '/api/v1/x', longBody, '失败')
    expect(err.message).toContain('(500)')
    expect(err.message).toContain('…')
    expect(err.message.length).toBeLessThan(longBody.length)
  })

  it('isApiError returns true for ApiError, false for plain Error and other values', () => {
    const apiErr = new ApiError(401, '/x', '', '失败')
    const plainErr = new Error('failed')
    expect(isApiError(apiErr)).toBe(true)
    expect(isApiError(plainErr)).toBe(false)
    expect(isApiError('string error')).toBe(false)
    expect(isApiError(null)).toBe(false)
    expect(isApiError(undefined)).toBe(false)
    expect(isApiError({ status: 401 })).toBe(false)
  })

  it('extractStatus returns status for ApiError, null for others', () => {
    const apiErr = new ApiError(403, '/x', '', '失败')
    expect(extractStatus(apiErr)).toBe(403)
    expect(extractStatus(new Error('failed'))).toBeNull()
    expect(extractStatus('string')).toBeNull()
    expect(extractStatus(null)).toBeNull()
  })
})
