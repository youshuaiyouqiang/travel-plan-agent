import { create } from 'zustand'
import type { SessionInfo } from '../utils/api'

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
  clearMessages: () => set({ messages: [], isEscalated: false, sessionId: generateId(), thinkingSteps: [] }),
  loadMessages: (msgs) =>
    set({
      messages: msgs.map((m, i) => ({
        id: `loaded-${i}`,
        role: m.role as 'user' | 'assistant',
        content: m.content,
        timestamp: m.created_at ? new Date(m.created_at).getTime() : Date.now(),
      })),
    }),
  resetSession: () => set({ messages: [], isEscalated: false, sessionId: generateId(), thinkingSteps: [] }),
  setSessions: (sessions) => set({ sessions, sessionsLoadedAt: Date.now() }),
}))

function generateId(): string {
  return Math.random().toString(36).substring(2, 10) + Date.now().toString(36)
}
