import { create } from 'zustand'

export interface AgentAction {
  type: 'navigate'
  label: string
  path: string
  agent: string
  description: string
}

interface SessionState {
  activeAgent: string | null       // 当前激活的智能体
  agentActions: AgentAction[]      // 当前智能体建议的操作
  setActiveAgent: (agent: string | null) => void
  setAgentActions: (actions: AgentAction[]) => void
  clearAgentActions: () => void
}

export const useSessionStore = create<SessionState>((set) => ({
  activeAgent: null,
  agentActions: [],
  setActiveAgent: (agent) => set({ activeAgent: agent }),
  setAgentActions: (actions) => set({ agentActions: actions }),
  clearAgentActions: () => set({ agentActions: [] }),
}))
