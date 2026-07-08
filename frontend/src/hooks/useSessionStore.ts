import { create } from 'zustand'
import { useAuthStore } from './useAuthStore'

function authHeaders(): HeadersInit {
  const token = useAuthStore.getState().token
  const headers: HeadersInit = { 'Content-Type': 'application/json' }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  return headers
}

export interface AgentAction {
  type: 'navigate'
  label: string
  path: string
  agent: string
  description: string
}

interface SessionState {
  activeAgent: string | null
  agentActions: AgentAction[]
  // ★ 多方案确认状态
  sessionConfirmedPlan: 'plan1' | 'plan2' | null
  isConfirming: boolean
  setActiveAgent: (agent: string | null) => void
  setAgentActions: (actions: AgentAction[]) => void
  clearAgentActions: () => void
  // ★ 多方案确认方法
  setSessionConfirmedPlan: (plan: 'plan1' | 'plan2' | null) => void
  confirmPlan: (planType: 'plan1' | 'plan2', itineraryId: string, sessionId: string) => Promise<void>
  revokeConfirm: (itineraryId: string, sessionId: string) => Promise<void>
  syncConfirmStatus: (sessionId: string) => Promise<void>
}

export const useSessionStore = create<SessionState>((set, get) => ({
  activeAgent: null,
  agentActions: [],
  sessionConfirmedPlan: null,
  isConfirming: false,
  setActiveAgent: (agent) => set({ activeAgent: agent }),
  setAgentActions: (actions) => set({ agentActions: actions }),
  clearAgentActions: () => set({ agentActions: [] }),
  // ★ 设置确认状态（用于会话切换时重置）
  setSessionConfirmedPlan: (plan) => set({ sessionConfirmedPlan: plan }),

  confirmPlan: async (planType, itineraryId, sessionId) => {
    set({ isConfirming: true })
    try {
      const res = await fetch(`/api/session/${sessionId}/confirm-plan`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ plan_type: planType === 'plan1' ? 'sightseeing' : 'budget', itinerary_id: itineraryId })
      })
      if (res.status === 409) {
        await get().syncConfirmStatus(sessionId)
        return
      }
      if (res.ok) {
        set({ sessionConfirmedPlan: planType })
      }
    } finally {
      set({ isConfirming: false })
    }
  },

  revokeConfirm: async (itineraryId, sessionId) => {
    try {
      const res = await fetch(`/api/session/${sessionId}/revoke-confirm`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ itinerary_id: itineraryId })
      })
      if (res.ok) {
        set({ sessionConfirmedPlan: null })
      }
    } catch {
      // ignore
    }
  },

  syncConfirmStatus: async (sessionId: string) => {
    try {
      const res = await fetch(`/api/session/${sessionId}/confirm-status`, { headers: authHeaders() })
      if (res.ok) {
        const data = await res.json()
        // 后端存储 sightseeing/budget，前端使用 plan1/plan2
        const planMap: Record<string, 'plan1' | 'plan2'> = { sightseeing: 'plan1', budget: 'plan2' }
        const mapped = data.confirmed_plan ? planMap[data.confirmed_plan] ?? null : null
        set({ sessionConfirmedPlan: mapped })
      }
    } catch {
      // ignore
    }
  },
}))
