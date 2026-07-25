/**
 * triggerNewsAnalysis 单元测试。
 *
 * 覆盖范围：
 * - 默认情况下按 createSession → switchSession → sendAnalysisPrompt 顺序触发
 * - sendAnalysisPrompt 收到的 prompt 默认值是研判指令；自定义 prompt 可覆盖
 * - autoSend=false 时仅创建会话，不切换、不发送
 * - createSession 抛错时整个流程不进入 send 阶段，错误直接抛出
 * - sendAnalysisPrompt 抛错时不吞异常，调用方 try/catch 统一处理
 * - 不向 chat 端点传递任何新闻全文字段（仅依赖后端按 news_id 注入锚点）
 */
import { describe, it, expect, vi } from 'vitest'

import {
  DEFAULT_NEWS_ANALYSIS_PROMPT,
  triggerNewsAnalysis,
} from './analysis'
import type { AnalysisSessionResult, HotspotItem } from './api'

const item: HotspotItem = {
  id: 'news-1',
  title: '示例热点',
  source: '示例来源',
  url: 'https://example.com/n1',
  summary: '示例摘要',
  published_at: '2026-07-25T00:00:00Z',
}

const fakeSession: AnalysisSessionResult = {
  session_id: 'sess-abc',
  mode: 'news_analysis_locked',
  locked_agent_id: 'news',
  news_id: 'news-1',
  anchor: {
    id: 'news-1',
    title: '示例热点',
    source: '示例来源',
    url: 'https://example.com/n1',
    summary: '示例摘要',
    published_at: '2026-07-25T00:00:00Z',
  },
}

describe('triggerNewsAnalysis', () => {
  it('默认按 createSession → switchSession → sendAnalysisPrompt 顺序触发', async () => {
    const order: string[] = []
    const createSession = vi.fn(async (newsId: string) => {
      order.push(`create:${newsId}`)
      return fakeSession
    })
    const switchSession = vi.fn(async (sessionId: string) => {
      order.push(`switch:${sessionId}`)
    })
    const sendAnalysisPrompt = vi.fn((text: string) => {
      order.push(`send:${text}`)
    })

    const result = await triggerNewsAnalysis(item, {
      createSession,
      sendAnalysisPrompt,
      switchSession,
    })

    expect(order).toEqual([
      'create:news-1',
      'switch:sess-abc',
      `send:${DEFAULT_NEWS_ANALYSIS_PROMPT}`,
    ])
    expect(result.session).toBe(fakeSession)
    expect(result.prompt).toBe(DEFAULT_NEWS_ANALYSIS_PROMPT)
  })

  it('switchSession 必须在 sendAnalysisPrompt 之前完成', async () => {
    // send handler 内部通常依赖 useChatStore.getState().sessionId 拿当前会话；
    // 一旦顺序反了，会把消息发到旧会话。这是关键顺序保证。
    const events: string[] = []
    await triggerNewsAnalysis(item, {
      createSession: vi.fn(async () => {
        events.push('create')
        return fakeSession
      }),
      switchSession: vi.fn(async () => {
        events.push('switch')
      }),
      sendAnalysisPrompt: vi.fn(() => {
        events.push('send')
      }),
    })
    expect(events.indexOf('switch')).toBeLessThan(events.indexOf('send'))
    expect(events.indexOf('create')).toBeLessThan(events.indexOf('switch'))
  })

  it('支持自定义 prompt 文本', async () => {
    const sendAnalysisPrompt = vi.fn()
    const customPrompt = '请重点分析这条新闻的政策影响'
    const result = await triggerNewsAnalysis(
      item,
      {
        createSession: vi.fn(async () => fakeSession),
        sendAnalysisPrompt,
        switchSession: vi.fn(async () => undefined),
      },
      { prompt: customPrompt },
    )
    expect(sendAnalysisPrompt).toHaveBeenCalledWith(customPrompt)
    expect(result.prompt).toBe(customPrompt)
  })

  it('autoSend=false 时只创建会话，不切换、不发送', async () => {
    const createSession = vi.fn(async () => fakeSession)
    const switchSession = vi.fn()
    const sendAnalysisPrompt = vi.fn()

    const result = await triggerNewsAnalysis(
      item,
      { createSession, switchSession, sendAnalysisPrompt },
      { autoSend: false },
    )

    expect(createSession).toHaveBeenCalledTimes(1)
    expect(switchSession).not.toHaveBeenCalled()
    expect(sendAnalysisPrompt).not.toHaveBeenCalled()
    expect(result.session).toBe(fakeSession)
    expect(result.prompt).toBe('')
  })

  it('不提供 switchSession 时直接进入 send 阶段', async () => {
    // 允许调用方在某些场景下自行管理会话切换（如已在新会话上下文中）。
    const sendAnalysisPrompt = vi.fn()
    const order: string[] = []
    await triggerNewsAnalysis(item, {
      createSession: vi.fn(async () => {
        order.push('create')
        return fakeSession
      }),
      sendAnalysisPrompt: (text) => {
        order.push('send')
        sendAnalysisPrompt(text)
      },
    })
    expect(order).toEqual(['create', 'send'])
    expect(sendAnalysisPrompt).toHaveBeenCalledWith(DEFAULT_NEWS_ANALYSIS_PROMPT)
  })

  it('createSession 抛错时直接抛出，send 不会被调用', async () => {
    const error = new Error('创建会话失败')
    const createSession = vi.fn(async () => {
      throw error
    })
    const sendAnalysisPrompt = vi.fn()

    await expect(
      triggerNewsAnalysis(item, {
        createSession,
        sendAnalysisPrompt,
        switchSession: vi.fn(),
      }),
    ).rejects.toBe(error)
    expect(sendAnalysisPrompt).not.toHaveBeenCalled()
  })

  it('sendAnalysisPrompt 抛错时不吞异常', async () => {
    const error = new Error('send 失败')
    const sendAnalysisPrompt = vi.fn(() => {
      throw error
    })
    await expect(
      triggerNewsAnalysis(item, {
        createSession: vi.fn(async () => fakeSession),
        sendAnalysisPrompt,
        switchSession: vi.fn(),
      }),
    ).rejects.toBe(error)
  })

  it('默认 prompt 不含新闻全文字段（仅研判指令）', () => {
    // 业务红线：前端不向 chat 端点传递新闻全文；锚点由后端按 news_id 注入。
    expect(DEFAULT_NEWS_ANALYSIS_PROMPT).not.toMatch(item.title)
    expect(DEFAULT_NEWS_ANALYSIS_PROMPT).not.toMatch(item.summary)
    expect(DEFAULT_NEWS_ANALYSIS_PROMPT).not.toMatch(item.url)
  })
})
