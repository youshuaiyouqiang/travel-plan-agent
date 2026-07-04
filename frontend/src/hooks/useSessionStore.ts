import { create } from 'zustand'

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

  confirmPlan: async (planType, itineraryId, sessionId) => {
    set({ isConfirming: true })
    try {
      const res = await fetch(`/api/session/${sessionId}/confirm-plan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
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
        headers: { 'Content-Type': 'application/json' },
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
      const res = await fetch(`/api/session/${sessionId}/confirm-status`)
      if (res.ok) {
        const data = await res.json()
        set({ sessionConfirmedPlan: data.confirmed_plan ?? null })
      }
    } catch {
      // ignore
    }
  },
}))
