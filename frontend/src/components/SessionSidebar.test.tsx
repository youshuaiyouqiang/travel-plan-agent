/**
 * Task 2.2 失败测试：SessionSidebar 切换/新建/删除会话必须通过回调委托，
 * 不得直接修改 ``useChatStore.sessionId`` / ``useChatStore.messages``。
 *
 * 设计要点（修复 Bug 2 — 切换入口分散）：
 * - 会话切换、新建、删除的 store 副作用必须收敛到 ``Home`` 组件；
 *   ``SessionSidebar`` 仅负责渲染和触发回调。
 * - ``SessionSidebar`` 不得调用 ``useChatStore.setSessionId`` /
 *   ``useChatStore.loadMessages`` / ``useChatStore.resetSession``。
 * - ``onSessionChange(newId)`` 用于切换/新建；``onDeleteActiveSession(id)``
 *   用于删除当前活跃会话（Home 决定下一个会话）。
 *
 * 这些测试当前会失败，因为现有实现由 SessionSidebar 直接调用 store。
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { SessionSidebar } from './SessionSidebar'
import { useChatStore } from '../hooks/useChatStore'

vi.mock('../features/chat/api', () => ({
  listSessions: vi.fn(),
  createSession: vi.fn(),
  deleteSession: vi.fn(),
  getSessionMessages: vi.fn(),
}))

import {
  listSessions,
  createSession,
  deleteSession,
} from '../features/chat/api'

const mockedListSessions = vi.mocked(listSessions)
const mockedCreateSession = vi.mocked(createSession)
const mockedDeleteSession = vi.mocked(deleteSession)

function makeSession(id: string, title: string) {
  return {
    session_id: id,
    title,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    message_count: 0,
  }
}

describe('SessionSidebar (Task 2.2 — single session-change entry)', () => {
  beforeEach(() => {
    useChatStore.setState({
      sessionId: '',
      messages: [],
      isEscalated: false,
      thinkingSteps: [],
      sessions: [],
      sessionsLoadedAt: 0,
    })
    vi.clearAllMocks()
  })

  it('handleSelectSession: 只调用 onSessionChange，不修改 store.sessionId', async () => {
    mockedListSessions.mockResolvedValue([makeSession('s1', '会话1'), makeSession('s2', '会话2')])
    const onSessionChange = vi.fn()
    render(<SessionSidebar onSessionChange={onSessionChange} activeSessionId="s1" />)

    await waitFor(() => {
      expect(screen.getByText('会话2')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('会话2'))

    await waitFor(() => {
      expect(onSessionChange).toHaveBeenCalledWith('s2')
    })
    // ★ 关键断言：Sidebar 自身不得改 store.sessionId
    expect(useChatStore.getState().sessionId).toBe('')
  })

  it('handleNewSession: 只调用 onSessionChange(newId)，不修改 store.sessionId', async () => {
    mockedListSessions.mockResolvedValue([])
    mockedCreateSession.mockResolvedValue({
      session_id: 'new-session',
      user_id: 'u1',
      mode: 'yunhe_default',
      locked_agent_id: null,
      news_id: null,
    })
    const onSessionChange = vi.fn()
    render(<SessionSidebar onSessionChange={onSessionChange} activeSessionId="" />)

    await waitFor(() => {
      expect(mockedListSessions).toHaveBeenCalled()
    })

    const newChatBtn = screen.getByRole('button', { name: /新建对话/ })
    fireEvent.click(newChatBtn)

    await waitFor(() => {
      expect(onSessionChange).toHaveBeenCalledWith('new-session')
    })
    // ★ 关键断言：Sidebar 自身不得改 store.sessionId
    expect(useChatStore.getState().sessionId).toBe('')
  })

  it('handleDeleteSession(当前活跃): 调用 onDeleteActiveSession；不修改 store.sessionId', async () => {
    mockedListSessions.mockResolvedValue([makeSession('s1', '会话1')])
    mockedDeleteSession.mockResolvedValue(undefined)
    const onSessionChange = vi.fn()
    const onDeleteActiveSession = vi.fn()
    render(
      <SessionSidebar
        onSessionChange={onSessionChange}
        onDeleteActiveSession={onDeleteActiveSession}
        activeSessionId="s1"
      />,
    )

    await waitFor(() => {
      expect(screen.getByText('会话1')).toBeInTheDocument()
    })

    const deleteBtn = screen.getByTitle('删除对话')
    fireEvent.click(deleteBtn)

    await waitFor(() => {
      expect(mockedDeleteSession).toHaveBeenCalledWith('s1')
    })
    await waitFor(() => {
      expect(onDeleteActiveSession).toHaveBeenCalledWith('s1')
    })
    // ★ 关键断言：store.sessionId 保持不变（由 Home 决定下一个）
    expect(useChatStore.getState().sessionId).toBe('')
  })

  it('handleDeleteSession(非当前活跃): 不调用 onDeleteActiveSession', async () => {
    mockedListSessions.mockResolvedValue([
      makeSession('s1', '会话1'),
      makeSession('s2', '会话2'),
    ])
    mockedDeleteSession.mockResolvedValue(undefined)
    const onSessionChange = vi.fn()
    const onDeleteActiveSession = vi.fn()
    render(
      <SessionSidebar
        onSessionChange={onSessionChange}
        onDeleteActiveSession={onDeleteActiveSession}
        activeSessionId="s1"
      />,
    )

    await waitFor(() => {
      expect(screen.getByText('会话2')).toBeInTheDocument()
    })

    const deleteBtns = screen.getAllByTitle('删除对话')
    // 第二个按钮对应 s2（非当前活跃）
    fireEvent.click(deleteBtns[1])

    await waitFor(() => {
      expect(mockedDeleteSession).toHaveBeenCalledWith('s2')
    })
    // ★ 非活跃会话不应触发 onDeleteActiveSession
    expect(onDeleteActiveSession).not.toHaveBeenCalled()
  })
})
