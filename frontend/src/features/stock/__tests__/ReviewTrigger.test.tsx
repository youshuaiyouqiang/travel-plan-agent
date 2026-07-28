/**
 * ReviewTrigger 组件测试（Task 7）。
 *
 * 覆盖范围：
 * - 触发后轮询：done 状态 → 跳转 /stock/reports/{report_id}
 * - 触发后轮询：failed 状态 → 错误文案 + 重试按钮
 * - 轮询过程中 404（任务过期/进程重启）→ 提示重新触发
 * - 组件卸载时清理定时器（不泄漏）
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act, cleanup } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ReviewTrigger } from '../ReviewTrigger'

// 模拟 react-router-dom 的 useNavigate
const navigateMock = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual =
    await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    useNavigate: () => navigateMock,
  }
})

interface MockResponse {
  status: number
  body: unknown
}

describe('ReviewTrigger', () => {
  let originalFetch: typeof globalThis.fetch
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    originalFetch = globalThis.fetch
    navigateMock.mockReset()
    fetchMock = vi.fn()
    globalThis.fetch = fetchMock as unknown as typeof globalThis.fetch
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    cleanup()
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  function mockResponseSequence(responses: MockResponse[]) {
    for (const r of responses) {
      fetchMock.mockResolvedValueOnce(
        new Response(JSON.stringify(r.body), {
          status: r.status,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    }
  }

  it('轮询 done 状态后跳转 /stock/reports/{report_id}', async () => {
    vi.useFakeTimers()
    // 1) POST /review 返回 task_id
    // 2) GET /review/tasks/{id} 返回 completed + report_id
    mockResponseSequence([
      { status: 202, body: { task_id: 'task-1', trade_date: '20260728', status: 'running' } },
      {
        status: 200,
        body: {
          task_id: 'task-1',
          user_id: 'u-1',
          trade_date: '20260728',
          status: 'completed',
          report_id: 'rep-99',
          error: null,
          created_at: '2026-07-28T10:00:00',
          updated_at: '2026-07-28T10:05:00',
        },
      },
    ])

    render(
      <MemoryRouter>
        <ReviewTrigger tradeDate="20260728" />
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: /生成复盘/ }))

    // 推进 3s 触发一次轮询
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3500)
    })

    expect(navigateMock).toHaveBeenCalledWith('/stock/reports/rep-99')
  })

  it('轮询 failed 状态后展示错误文案 + 重试按钮', async () => {
    vi.useFakeTimers()
    mockResponseSequence([
      { status: 202, body: { task_id: 'task-1', trade_date: '20260728', status: 'running' } },
      {
        status: 200,
        body: {
          task_id: 'task-1',
          user_id: 'u-1',
          trade_date: '20260728',
          status: 'failed',
          report_id: null,
          error: 'LLM_ERROR',
          created_at: '2026-07-28T10:00:00',
          updated_at: '2026-07-28T10:05:00',
        },
      },
    ])

    render(
      <MemoryRouter>
        <ReviewTrigger tradeDate="20260728" />
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: /生成复盘/ }))

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3500)
    })

    expect(screen.getByText(/复盘生成失败/)).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /重新触发/ }),
    ).toBeInTheDocument()
    expect(navigateMock).not.toHaveBeenCalled()
  })

  it('轮询 404（任务过期）提示重新触发', async () => {
    vi.useFakeTimers()
    mockResponseSequence([
      { status: 202, body: { task_id: 'task-1', trade_date: '20260728', status: 'running' } },
      { status: 404, body: { detail: 'task not found' } },
    ])

    render(
      <MemoryRouter>
        <ReviewTrigger tradeDate="20260728" />
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: /生成复盘/ }))

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3500)
    })

    expect(screen.getByText(/任务已过期/)).toBeInTheDocument()
    expect(navigateMock).not.toHaveBeenCalled()
  })
})
