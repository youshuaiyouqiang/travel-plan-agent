/**
 * Task 2.1 失败测试：会话切换语义修复。
 *
 * 覆盖范围（修复 Bug 2）：
 * - ``useChatStore.clearMessages`` **不得**重置 sessionId（避免覆盖
 *   调用方的 setSessionId）
 * - ``useChatStore.resetSession`` **不得**重置 sessionId（同上）
 * - ``useChatStore.setSessionId`` 同步设置后，``getState().sessionId``
 *   立刻反映新值（这是切换流程的同步锚点）
 * - ``useChatStore.loadMessages`` 不会触碰 sessionId
 *
 * 设计要点：
 * - 切换会话的副作用必须收敛到"调用方 setSessionId + 同步 clearMessages +
 *   异步 loadMessages"三步；store 的辅助方法只做最小变更，不替调用方
 *   决定 sessionId
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { useChatStore } from './useChatStore'

describe('useChatStore session-switch semantics (Task 2.1)', () => {
  beforeEach(() => {
    // 每个用例前重置 store 到空状态
    useChatStore.getState().setSessionId('')
    useChatStore.setState({
      messages: [],
      isEscalated: false,
      thinkingSteps: [],
    })
  })

  describe('clearMessages must not touch sessionId', () => {
    it('preserves an explicit sessionId when clearing messages', () => {
      const store = useChatStore.getState()
      store.setSessionId('session-A')
      // 模拟 Home.handleSessionChange 的预期流程：
      // 1) setSessionId 2) clearMessages (must keep 'session-A') 3) loadMessages
      store.setSessionId('session-B')
      useChatStore.getState().clearMessages()

      expect(useChatStore.getState().sessionId).toBe('session-B')
    })

    it('clears messages, isEscalated, thinkingSteps but not sessionId', () => {
      const store = useChatStore.getState()
      store.setSessionId('session-X')
      // 注入非空数据
      useChatStore.getState().addMessage({ role: 'user', content: 'hi' })
      useChatStore.getState().addMessage({ role: 'assistant', content: 'a' })
      useChatStore.setState({ isEscalated: true })
      useChatStore.getState().addThinkingStep('step')

      useChatStore.getState().clearMessages()

      const after = useChatStore.getState()
      expect(after.messages).toEqual([])
      expect(after.isEscalated).toBe(false)
      expect(after.thinkingSteps).toEqual([])
      // ★ 关键断言：sessionId 必须保持
      expect(after.sessionId).toBe('session-X')
    })
  })

  describe('resetSession must not touch sessionId', () => {
    it('preserves sessionId when calling resetSession', () => {
      useChatStore.getState().setSessionId('session-Y')
      useChatStore.getState().resetSession()

      expect(useChatStore.getState().sessionId).toBe('session-Y')
    })

    it('still clears messages, isEscalated, thinkingSteps', () => {
      useChatStore.getState().setSessionId('session-Z')
      useChatStore.getState().addMessage({ role: 'user', content: 'msg' })
      useChatStore.setState({ isEscalated: true })

      useChatStore.getState().resetSession()

      const after = useChatStore.getState()
      expect(after.messages).toEqual([])
      expect(after.isEscalated).toBe(false)
      expect(after.sessionId).toBe('session-Z')
    })
  })

  describe('setSessionId is the single source of sessionId', () => {
    it('overrides any prior sessionId', () => {
      useChatStore.getState().setSessionId('old')
      useChatStore.getState().setSessionId('new')
      expect(useChatStore.getState().sessionId).toBe('new')
    })

    it('clearMessages / resetSession after setSessionId keeps the new value', () => {
      // 模拟 Home.handleSessionChange 的完整三步
      useChatStore.getState().setSessionId('session-A')
      useChatStore.getState().addMessage({ role: 'user', content: 'a' })
      useChatStore.getState().clearMessages()
      useChatStore.getState().loadMessages([{ role: 'user', content: 'b' }])

      const after = useChatStore.getState()
      expect(after.sessionId).toBe('session-A')
      expect(after.messages).toHaveLength(1)
      expect(after.messages[0].content).toBe('b')
    })
  })

  describe('loadMessages must not touch sessionId', () => {
    it('keeps the current sessionId when loading messages', () => {
      useChatStore.getState().setSessionId('session-K')
      useChatStore.getState().loadMessages([
        { role: 'user', content: 'u1' },
        { role: 'assistant', content: 'a1' },
      ])

      expect(useChatStore.getState().sessionId).toBe('session-K')
      expect(useChatStore.getState().messages).toHaveLength(2)
    })
  })
})
