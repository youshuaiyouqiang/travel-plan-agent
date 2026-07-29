/**
 * API 错误：携带 HTTP status code 便于上层精确决策。
 *
 * 设计要点（修复 Bug "获取智能体列表失败没状态码"）：
 * - 旧实现 ``fetchAgents`` 抛固定字符串 ``new Error('获取智能体列表失败')``，
 *   不带 status code，组件层 ``msg.includes('401')`` 永远不命中，
 *   导致 401 错误无法触发 ``logout``，用户看到通用错误文案。
 * - ``ApiError`` 通过 ``status`` 字段传递真实 HTTP 状态，组件层用
 *   ``isApiError(err) && err.status === 401`` 即可精确识别。
 * - ``message`` 自动拼接 ``(status)`` 与服务端响应体前 200 字符，
 *   既保留调试信息又让用户能看到真实错误（如 401 鉴权失败、
 *   500 内部错误、404 端点不存在等）。
 */

const MAX_BODY_IN_MSG = 200

export class ApiError extends Error {
  readonly status: number
  readonly url: string
  readonly body: string

  constructor(status: number, url: string, body: string, fallbackMsg: string) {
    const trimmedBody = body.trim()
    const bodyInMsg = trimmedBody
      ? trimmedBody.length > MAX_BODY_IN_MSG
        ? trimmedBody.slice(0, MAX_BODY_IN_MSG) + '…'
        : trimmedBody
      : ''
    const msg = bodyInMsg
      ? `${fallbackMsg} (${status}): ${bodyInMsg}`
      : `${fallbackMsg} (${status})`
    super(msg)
    this.name = 'ApiError'
    this.status = status
    this.url = url
    this.body = body
  }
}

export function isApiError(err: unknown): err is ApiError {
  return err instanceof ApiError
}

/** 从 ApiError 或任意 Error 中提取 status；非 ApiError 返回 null。 */
export function extractStatus(err: unknown): number | null {
  return isApiError(err) ? err.status : null
}
