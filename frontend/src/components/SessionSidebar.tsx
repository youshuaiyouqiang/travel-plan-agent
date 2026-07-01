import { useState, useEffect, useCallback } from 'react'
import { Plus, Trash2, MessageSquare, ChevronLeft, ChevronRight } from 'lucide-react'
import { useAuthStore } from '../hooks/useAuthStore'
import { useChatStore } from '../hooks/useChatStore'
import { listSessions, createSession, deleteSession, getSessionMessages } from '../utils/api'
import type { SessionInfo } from '../utils/api'

interface Props {
  onSessionChange: (sessionId: string) => void
  activeSessionId: string
}

/**
 * 会话列表栏 — 只负责会话历史展示与切换。
 * 位于 NavSidebar 右侧、对话区左侧。
 * sessions 存在全局 store，Home 卸载重挂载时不会丢失，避免每次返回都白屏重新加载。
 */
export function SessionSidebar({ onSessionChange, activeSessionId }: Props) {
  const [collapsed, setCollapsed] = useState(false)
  const [loading, setLoading] = useState(false)
  const { setSessionId, setUserId, loadMessages, resetSession } = useChatStore()
  const sessions = useChatStore((s) => s.sessions)
  const setSessions = useChatStore((s) => s.setSessions)

  const fetchSessions = useCallback(async () => {
    try {
      const list = await listSessions()
      setSessions(list)
    } catch {
      /* ignore */
    }
  }, [setSessions])

  // 挂载时：若 store 已有数据则立即显示，后台静默刷新；否则首次加载
  useEffect(() => {
    fetchSessions()
  }, [fetchSessions])

  const handleNewSession = async () => {
    setLoading(true)
    try {
      const result = await createSession()
      setSessionId(result.session_id)
      if (userId) setUserId(userId)
      loadMessages([])
      onSessionChange(result.session_id)
      await fetchSessions()
    } catch {
      resetSession()
      onSessionChange(useChatStore.getState().sessionId)
    } finally {
      setLoading(false)
    }
  }

  const handleSelectSession = async (session: SessionInfo) => {
    if (session.session_id === activeSessionId) return
    setSessionId(session.session_id)
    if (userId) setUserId(userId)
    try {
      const msgs = await getSessionMessages(session.session_id)
      loadMessages(msgs)
    } catch {
      loadMessages([])
    }
    onSessionChange(session.session_id)
  }

  const handleDeleteSession = async (e: React.MouseEvent, session: SessionInfo) => {
    e.stopPropagation()
    try {
      await deleteSession(session.session_id)
      if (session.session_id === activeSessionId) {
        resetSession()
        onSessionChange(useChatStore.getState().sessionId)
      }
      await fetchSessions()
    } catch {
      /* ignore */
    }
  }

  if (collapsed) {
    return (
      <div className="w-12 bg-white border-r border-slate-200 flex flex-col items-center py-4 gap-3 flex-shrink-0">
        <button
          onClick={() => setCollapsed(false)}
          className="p-2 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
          title="展开会话列表"
        >
          <ChevronRight size={18} />
        </button>
        <button
          onClick={handleNewSession}
          className="p-2 rounded-lg text-indigo-500 hover:bg-indigo-50 transition-colors"
          title="新建对话"
        >
          <Plus size={18} />
        </button>
      </div>
    )
  }

  return (
    <div className="w-64 bg-white border-r border-slate-200 flex flex-col flex-shrink-0">
      <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
        <span className="text-sm font-semibold text-slate-700">会话历史</span>
        <button
          onClick={() => setCollapsed(true)}
          className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
          title="收起会话列表"
        >
          <ChevronLeft size={16} />
        </button>
      </div>

      <div className="px-3 py-2">
        <button
          onClick={handleNewSession}
          disabled={loading}
          className="w-full flex items-center justify-center gap-1.5 rounded-lg bg-indigo-50 text-indigo-600 text-sm font-medium py-2 hover:bg-indigo-100 disabled:opacity-50 transition-colors"
        >
          <Plus size={15} />
          新建对话
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-1 scrollbar-thin">
        {sessions.length === 0 && (
          <p className="text-xs text-slate-400 text-center py-6">暂无对话记录</p>
        )}
        {sessions.map((session) => (
          <div
            key={session.session_id}
            onClick={() => handleSelectSession(session)}
            className={`group flex items-center gap-2 px-3 py-2.5 rounded-lg cursor-pointer transition-colors mb-0.5 ${
              session.session_id === activeSessionId
                ? 'bg-indigo-50 text-indigo-700'
                : 'text-slate-600 hover:bg-slate-50'
            }`}
          >
            <MessageSquare size={14} className="flex-shrink-0 opacity-60" />
            <div className="flex-1 min-w-0">
              <p className="text-sm truncate">{session.title}</p>
              <p className="text-xs text-slate-400 truncate">
                {session.message_count} 条消息
              </p>
            </div>
            <button
              onClick={(e) => handleDeleteSession(e, session)}
              className="opacity-0 group-hover:opacity-100 p-1 rounded text-slate-400 hover:text-red-500 transition-all flex-shrink-0"
              title="删除对话"
            >
              <Trash2 size={13} />
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
