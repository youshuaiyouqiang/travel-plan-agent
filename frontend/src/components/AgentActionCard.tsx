import { useNavigate } from 'react-router-dom'
import { ChevronRight, Map } from 'lucide-react'
import { useSessionStore, AgentAction } from '../hooks/useSessionStore'

export function AgentActionCard({ action }: { action: AgentAction }) {
  const navigate = useNavigate()
  const setActiveAgent = useSessionStore((s) => s.setActiveAgent)

  const handleClick = () => {
    // 确保智能体已激活（守卫才能放行）
    setActiveAgent(action.agent)
    navigate(action.path)
  }

  return (
    <button
      onClick={handleClick}
      className="mt-3 flex items-center gap-3 px-5 py-3.5 bg-gradient-to-r from-sky-500 to-blue-600 text-white rounded-2xl text-sm font-medium hover:from-sky-600 hover:to-blue-700 transition-all shadow-lg shadow-sky-200/60 active:scale-[0.97] w-fit max-w-md"
    >
      <div className="w-10 h-10 rounded-xl bg-white/20 flex items-center justify-center flex-shrink-0">
        <Map size={20} className="text-white" />
      </div>
      <div className="text-left flex-1">
        <div className="font-semibold text-[15px]">{action.label}</div>
        <div className="text-white/70 text-xs mt-0.5">{action.description}</div>
      </div>
      <ChevronRight size={16} className="text-white/60" />
    </button>
  )
}
