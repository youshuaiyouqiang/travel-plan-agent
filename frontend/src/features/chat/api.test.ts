/**
 * Task 3 chat API 契约测试。
 *
 * 覆盖范围：
 * - `sendMessageStream` 不向请求体写入客户端 `user_id`/`agent_id`（用户身份只能来自服务端认证上下文）
 * - 请求路径使用 `/api/v1/chat/stream`（与后端 v1 路由前缀一致）
 * - SSE 事件按 `chunk` / `route` / `error` / `done` 四类做判别联合解析
 */
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { sendMessageStream } from './api'
import type { StreamEvent } from './types'

describe('chat api', () => {
  let originalFetch: typeof globalThis.fetch
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    originalFetch = globalThis.fetch
    fetchMock = vi.fn()
    globalThis.fetch = fetchMock as unknown as typeof globalThis.fetch
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it('does not send client user_id with chat requests', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response('data: {"type":"done","data":{"handled_by":"yunhe","next_controller":"yunhe"}}\n\n', {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
      }),
    )

    const stream = sendMessageStream({ session_id: 's1', message: 'hello' })
    // 必须迭代才能触发 fetch
    let next = await stream.next()
    while (!next.done) {
      next = await stream.next()
    }

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/chat/stream',
      expect.objectContaining({
        body: JSON.stringify({ session_id: 's1', message: 'hello' }),
      }),
    )
  })

  it('parses SSE events into the discriminated StreamEvent union', async () => {
    const sseBody =
      'data: {"type":"chunk","data":"hello"}\n\n' +
      'data: {"type":"route","data":{"agent_id":"news","delegated":true}}\n\n' +
      'data: {"type":"done","data":{"handled_by":"news","next_controller":"locked_agent"}}\n\n'
    fetchMock.mockResolvedValueOnce(
      new Response(sseBody, {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
      }),
    )

    const events: StreamEvent[] = []
    for await (const event of sendMessageStream({ session_id: 's1', message: 'hi' })) {
      events.push(event)
    }

    expect(events).toEqual([
      { type: 'chunk', data: 'hello' },
      { type: 'route', data: { agent_id: 'news', delegated: true } },
      { type: 'done', data: { handled_by: 'news', next_controller: 'locked_agent' } },
    ])
  })

  it('throws AUTH_EXPIRED on 401 responses', async () => {
    fetchMock.mockResolvedValueOnce(new Response('{"detail":"unauthorized"}', { status: 401 }))

    await expect(async () => {
      const stream = sendMessageStream({ session_id: 's1', message: 'hi' })
      let next = await stream.next()
      while (!next.done) {
        next = await stream.next()
      }
    }).rejects.toThrow('AUTH_EXPIRED')
  })
})
