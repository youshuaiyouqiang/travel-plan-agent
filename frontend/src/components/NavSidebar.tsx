import { useNavigate, useLocation } from 'react-router-dom'
import { Bot, Brain, LogOut, Sparkles } from 'lucide-react'
import { useAuthStore } from '../hooks/useAuthStore'

/**
 * 左侧导航栏 — 通用智能体框架的主导航。
 * 只放模块入口：Agent 中心、记忆、退出登录。
 * 不含会话列表（会话列表在 SessionSidebar，位于本栏右侧）。
 */
export function NavSidebar() {
  const navigate = useNavigate()
  const location = useLocation()
  const username = useAuthStore((s) => s.username)
  const logout = useAuthStore((s) => s.logout)

  const isAgentCenter = location.pathname.startsWith('/agents')
  const isMemories = location.pathname.startsWith('/memories')

  return (
    <div className="w-56 bg-white border-r border-slate-200 flex flex-col flex-shrink-0">
      {/* Logo / 品牌区 */}
      <div className="px-4 py-4 border-b border-slate-100 flex items-center gap-2">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-sky-400 to-blue-500 flex items-center justify-center shadow-sm">
          <Sparkles size={16} className="text-white" />
        </div>
        <span
          className="text-sm font-semibold text-slate-800"
          style={{ fontFamily: 'var(--font-display)' }}
        >
          Claw
        </span>
      </div>

      {/* 导航模块 */}
      <nav className="flex-1 px-3 py-3 space-y-1">
        <button
          onClick={() => navigate('/agents')}
          className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
            isAgentCenter
              ? 'bg-indigo-50 text-indigo-700'
              : 'text-slate-600 hover:bg-slate-50'
          }`}
        >
          <Bot size={18} className="flex-shrink-0" />
          Agent 中心
        </button>
        <button
          onClick={() => navigate('/memories')}
          className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
            isMemories
              ? 'bg-violet-50 text-violet-700'
              : 'text-slate-600 hover:bg-slate-50'
          }`}
        >
          <Brain size={18} className="flex-shrink-0" />
          记忆
        </button>
      </nav>

      {/* 用户区 */}
      <div className="px-3 py-3 border-t border-slate-100">
        <div className="px-3 py-2 mb-1">
          <p className="text-xs text-slate-400">当前用户</p>
          <p className="text-sm text-slate-700 truncate">{username || '未登录'}</p>
        </div>
        <button
          onClick={logout}
          className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm font-medium text-slate-500 hover:bg-slate-50 hover:text-slate-700 transition-colors"
        >
          <LogOut size={18} className="flex-shrink-0" />
          退出登录
        </button>
      </div>
    </div>
  )
}
