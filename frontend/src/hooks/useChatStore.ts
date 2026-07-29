import { create } from 'zustand'
import type { SessionInfo } from '../features/chat/api'
import type { EvidenceCard } from '../features/news/api'

export interface ThinkingStep {
  id: string
  text: string
  status: 'active' | 'done'
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  status?: string
  timestamp: number
  isStreaming?: boolean
  /**
   * 仅新闻研判会话（``news_analysis_locked``）下由后端 SSE ``evidence`` 事件
   * 注入；非研判会话与未收到事件时为 ``undefined``。空数组表示"无证据"占位，
   * 与"事件丢失"语义不同。
   *
   * 用于在 assistant 消息气泡下方独立渲染结构化 :class:`EvidenceCards` 组件，
   * 不混入 LLM 文本结论。
   */
  evidenceCards?: EvidenceCard[]
}

interface ChatState {
  messages: Message[]
  isLoading: boolean
  sessionId: string
  userId: string
  isEscalated: boolean
  thinkingSteps: ThinkingStep[]
  sessions: SessionInfo[]
  sessionsLoadedAt: number
  addMessage: (msg: Omit<Message, 'id' | 'timestamp'>) => void
  appendToLastMessage: (chunk: string) => void
  finishLastMessage: () => void
  /**
   * 把 evidence 卡片挂到最近一条 assistant 消息（优先选正在 streaming 的，
   * 否则取最后一条 assistant 消息）。没有可挂载消息时**新增**一条 assistant
   * 元消息承载 evidence，避免事件丢失。
   */
  attachEvidenceCards: (cards: EvidenceCard[]) => void
  setLoading: (loading: boolean) => void
  setSessionId: (id: string) => void
  setUserId: (id: string) => void
  setEscalated: (v: boolean) => void
  addThinkingStep: (text: string) => void
  clearThinkingSteps: () => void
  clearMessages: () => void
  loadMessages: (msgs: Array<{ role: string; content: string; created_at?: string }>) => void
  resetSession: () => void
  setSessions: (sessions: SessionInfo[]) => void
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  isLoading: false,
  sessionId: '',
  userId: '',
  isEscalated: false,
  thinkingSteps: [],
  sessions: [],
  sessionsLoadedAt: 0,
  addMessage: (msg) =>
    set((state) => ({
      messages: [
        ...state.messages,
        { ...msg, id: generateId(), timestamp: Date.now() },
      ],
    })),
  appendToLastMessage: (chunk: string) =>
    set((state) => {
      const messages = [...state.messages]
      const last = messages[messages.length - 1]
      if (last && last.role === 'assistant') {
        messages[messages.length - 1] = {
          ...last,
          content: last.content + chunk,
          isStreaming: true,
        }
      }
      return { messages }
    }),
  finishLastMessage: () =>
    set((state) => {
      const messages = [...state.messages]
      const last = messages[messages.length - 1]
      if (last && last.role === 'assistant') {
        messages[messages.length - 1] = {
          ...last,
          isStreaming: false,
        }
      }
      return { messages }
    }),
  attachEvidenceCards: (cards: EvidenceCard[]) =>
    set((state) => {
      const messages = [...state.messages]
      // 优先复用最近一条 streaming 的 assistant；否则取最后一条 assistant
      let targetIdx = -1
      for (let i = messages.length - 1; i >= 0; i--) {
        if (messages[i].role === 'assistant') {
          targetIdx = i
          if (messages[i].isStreaming) break
        }
      }
      if (targetIdx >= 0) {
        messages[targetIdx] = {
          ...messages[targetIdx],
          evidenceCards: cards,
        }
      } else {
        // 无可挂载消息：插入一条 assistant 元消息承载 evidence
        messages.push({
          id: generateId(),
          role: 'assistant',
          content: '',
          evidenceCards: cards,
          timestamp: Date.now(),
        })
      }
      return { messages }
    }),
  setLoading: (loading) => set({ isLoading: loading }),
  setSessionId: (id) => set({ sessionId: id }),
  setUserId: (id) => set({ userId: id }),
  setEscalated: (v) => set({ isEscalated: v }),
  addThinkingStep: (text: string) =>
    set((state) => {
      const steps = [...state.thinkingSteps]
      // 将上一步标记为完成
      if (steps.length > 0) {
        steps[steps.length - 1] = { ...steps[steps.length - 1], status: 'done' }
      }
      steps.push({ id: generateId(), text, status: 'active' })
      return { thinkingSteps: steps }
    }),
  clearThinkingSteps: () => set({ thinkingSteps: [] }),
  clearMessages: () => set({ messages: [], isEscalated: false, thinkingSteps: [] }),
  loadMessages: (msgs) =>
    set({
      messages: msgs.map((m, i) => ({
        id: `loaded-${i}`,
        role: m.role as 'user' | 'assistant',
        content: m.content,
        timestamp: m.created_at ? new Date(m.created_at).getTime() : Date.now(),
      })),
    }),
  resetSession: () => set({ messages: [], isEscalated: false, thinkingSteps: [] }),
  setSessions: (sessions) => set({ sessions, sessionsLoadedAt: Date.now() }),
}))

function generateId(): string {
  return Math.random().toString(36).substring(2, 10) + Date.now().toString(36)
}
