import { Navigate } from 'react-router-dom'
import { useSessionStore } from '../hooks/useSessionStore'

interface Props {
  agent: string
  children: React.ReactNode
}

/** 智能体路由守卫：只有对应智能体激活时才放行 */
export function AgentRouteGuard({ agent, children }: Props) {
  const activeAgent = useSessionStore((s) => s.activeAgent)

  if (activeAgent !== agent) {
    // 智能体未激活，重定向回对话页
    return <Navigate to="/" replace />
  }

  return <>{children}</>
}
