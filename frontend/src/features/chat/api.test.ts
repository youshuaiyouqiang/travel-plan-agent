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

/** 用 ReadableStream 构造一个 SSE Response：比 new Response(string) 更稳。 */
function makeSSEResponse(body: string): Response {
  const encoder = new TextEncoder()
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode(body))
      controller.close()
    },
  })
  return new Response(stream, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  })
}

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

  it('parses the evidence SSE event with structured cards', async () => {
    const evidencePayload = [
      { source_id: 'src-a', source_name: 'A', url: 'https://a/x', claim: 'claim-1', status: 'verified' },
      { source_id: 'src-b', source_name: 'B', url: 'https://b/x', claim: 'claim-2', status: 'conflicted' },
    ]
    const sseBody =
      'data: ' +
      JSON.stringify({ type: 'evidence', data: evidencePayload }) +
      '\n\n' +
      'data: {"type":"chunk","data":"result"}\n\n' +
      'data: {"type":"done","data":{"handled_by":"news","next_controller":"locked_agent"}}\n\n'
    fetchMock.mockResolvedValueOnce(makeSSEResponse(sseBody))

    const events: StreamEvent[] = []
    for await (const event of sendMessageStream({ session_id: 's1', message: 'analyze' })) {
      events.push(event)
    }

    const evidence = events.find((e) => e.type === 'evidence')
    expect(evidence).toBeDefined()
    if (evidence && evidence.type === 'evidence') {
      expect(evidence.data).toHaveLength(2)
      expect(evidence.data[0].source_id).toBe('src-a')
      expect(evidence.data[0].status).toBe('verified')
      expect(evidence.data[1].status).toBe('conflicted')
    }
  })

  it('parses an empty evidence event (无证据) as type=evidence with [] data', async () => {
    const sseBody =
      'data: {"type":"evidence","data":[]}\n\n' +
      'data: {"type":"done","data":{"handled_by":"news","next_controller":"locked_agent"}}\n\n'
    fetchMock.mockResolvedValueOnce(makeSSEResponse(sseBody))

    const events: StreamEvent[] = []
    for await (const event of sendMessageStream({ session_id: 's1', message: 'analyze' })) {
      events.push(event)
    }

    const evidence = events.find((e) => e.type === 'evidence')
    expect(evidence).toBeDefined()
    if (evidence && evidence.type === 'evidence') {
      expect(evidence.data).toEqual([])
    }
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
