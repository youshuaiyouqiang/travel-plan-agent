import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Trash2, MessageSquare, LogOut, ChevronLeft, ChevronRight, MapPin, Brain, ArrowRightLeft, Camera } from 'lucide-react'
import { useAuthStore } from '../hooks/useAuthStore'
import { useChatStore } from '../hooks/useChatStore'
import { listSessions, createSession, deleteSession, getSessionMessages, listItineraries, deleteItinerary, ItineraryListItem } from '../utils/api'
import type { SessionInfo } from '../utils/api'

interface Props {
  onSessionChange: (sessionId: string) => void
  activeSessionId: string
}

export function SessionSidebar({ onSessionChange, activeSessionId }: Props) {
  const [sessions, setSessions] = useState<SessionInfo[]>([])
  const [itineraries, setItineraries] = useState<ItineraryListItem[]>([])
  const [collapsed, setCollapsed] = useState(false)
  const [loading, setLoading] = useState(false)
  const [showItineraries, setShowItineraries] = useState(false)
  const logout = useAuthStore((s) => s.logout)
  const username = useAuthStore((s) => s.username)
  const navigate = useNavigate()
  const { setSessionId, setUserId, loadMessages, resetSession } = useChatStore()
  const userId = useAuthStore((s) => s.userId)

  const fetchSessions = useCallback(async () => {
    try {
      const list = await listSessions()
      setSessions(list)
    } catch {
      /* ignore */
    }
  }, [])

  const fetchItineraries = useCallback(async () => {
    try {
      const list = await listItineraries()
      setItineraries(list)
    } catch {
      /* ignore */
    }
  }, [])

  useEffect(() => {
    fetchSessions()
    fetchItineraries()
  }, [fetchSessions, fetchItineraries])

  const handleNewSession = async () => {
    setLoading(true)
    try {
      const result = await createSession()
      setSessionId(result.session_id)
      if (userId) setUserId(userId)
      loadMessages([])
      onSessionChange(result.session_id)
      await fetchSessions()
      await fetchItineraries()
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

  const handleLogout = () => {
    logout()
  }

  if (collapsed) {
    return (
      <div className="w-12 bg-white border-r border-slate-200 flex flex-col items-center py-4 gap-3 flex-shrink-0">
        <button
          onClick={() => setCollapsed(false)}
          className="p-2 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
          title="展开侧边栏"
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
        <span className="text-sm font-semibold text-slate-700 truncate">
          {username || '用户'}
        </span>
        <button
          onClick={() => setCollapsed(true)}
          className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
          title="收起侧边栏"
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

      <div className="px-3 py-3 border-t border-slate-100">
        <button
          onClick={() => setShowItineraries(!showItineraries)}
          className="w-full flex items-center justify-center gap-1.5 rounded-lg text-slate-500 text-sm py-2 hover:bg-sky-50 hover:text-sky-600 transition-colors"
        >
          <MapPin size={15} />
          我的行程
          {itineraries.length > 0 && (
            <span className="ml-1 text-[10px] bg-sky-100 text-sky-600 px-1.5 py-0.5 rounded-full font-medium">
              {itineraries.length}
            </span>
          )}
        </button>

        {showItineraries && itineraries.length > 0 && (
          <div className="mt-2 space-y-1 max-h-48 overflow-y-auto scrollbar-thin">
            {itineraries.map((itin) => (
              <div
                key={itin.id}
                className="group flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-slate-600 hover:bg-sky-50 transition-colors"
              >
                <button
                  onClick={() => navigate(`/itinerary/${itin.id}`)}
                  className="flex items-center gap-2 flex-1 min-w-0 text-left"
                >
                  <MapPin size={12} className="flex-shrink-0 text-sky-400" />
                  <div className="flex-1 min-w-0">
                    <p className="truncate text-xs font-medium">{itin.title}</p>
                    <p className="text-[10px] text-slate-400">{itin.destination}</p>
                  </div>
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); navigate(`/album/${itin.id}`) }}
                  className="opacity-0 group-hover:opacity-100 p-1 rounded text-slate-400 hover:text-indigo-500 transition-all flex-shrink-0"
                  title="相册"
                >
                  <Camera size={11} />
                </button>
                <button
                  onClick={async (e) => {
                    e.stopPropagation()
                    try {
                      await deleteItinerary(itin.id)
                      setItineraries((prev) => prev.filter((i) => i.id !== itin.id))
                    } catch { /* ignore */ }
                  }}
                  className="opacity-0 group-hover:opacity-100 p-1 rounded text-slate-400 hover:text-red-500 transition-all flex-shrink-0"
                  title="删除行程"
                >
                  <Trash2 size={11} />
                </button>
              </div>
            ))}
          </div>
        )}

        {showItineraries && itineraries.length === 0 && (
          <p className="text-xs text-slate-400 text-center py-2">暂无行程</p>
        )}
      </div>

      <div className="px-3 py-3 border-t border-slate-100">
        <button
          onClick={() => navigate('/memories')}
          className="w-full flex items-center justify-center gap-1.5 rounded-lg text-violet-500 text-sm py-2 hover:bg-violet-50 transition-colors font-medium"
        >
          <Brain size={15} />
          旅行记忆
        </button>
        {itineraries.length >= 2 && (
          <button
            onClick={() => navigate('/compare')}
            className="w-full flex items-center justify-center gap-1.5 rounded-lg text-sky-500 text-sm py-2 hover:bg-sky-50 transition-colors font-medium mt-1"
          >
            <ArrowRightLeft size={15} />
            行程对比
          </button>
        )}
      </div>

      <div className="px-3 py-3 border-t border-slate-100">
        <button
          onClick={handleLogout}
          className="w-full flex items-center justify-center gap-1.5 rounded-lg text-slate-500 text-sm py-2 hover:bg-slate-50 hover:text-slate-700 transition-colors"
        >
          <LogOut size={15} />
          退出登录
        </button>
      </div>
    </div>
  )
}
