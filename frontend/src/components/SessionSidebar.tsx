import { useState, useEffect, useCallback, useRef } from 'react'
import { Plus, Trash2, MessageSquare, ChevronLeft, ChevronRight } from 'lucide-react'
import { useChatStore } from '../hooks/useChatStore'
import { listSessions, createSession, deleteSession } from '../features/chat/api'
import type { SessionInfo } from '../features/chat/api'

interface Props {
  /** 会话切换/新建回调：被点击的会话 ID 交给父组件处理。 */
  onSessionChange: (sessionId: string) => void
  /** 删除当前活跃会话回调：父组件决定下一个活跃会话。 */
  onDeleteActiveSession?: (deletedId: string) => void
  activeSessionId: string
  refreshTrigger?: number          // 外部递增此值可强制刷新会话列表
}

/**
 * 会话列表栏 — 只负责会话历史展示与切换。
 *
 * 设计契约（Task 2.2，修复 Bug 2 — 切换入口分散）：
 * - 本组件不直接修改 ``useChatStore`` 的 ``sessionId`` / ``messages`` /
 *   ``isEscalated`` / ``thinkingSteps``，所有 store 副作用收敛到
 *   ``Home`` 组件的 ``handleSessionChange`` / ``handleDeleteActiveSession``。
 * - 会话切换/新建通过 ``onSessionChange(newId)`` 回调触发；删除当前
 *   活跃会话通过 ``onDeleteActiveSession(deletedId)`` 回调触发。
 * - 仅 ``useChatStore.setSessions`` 用于更新会话列表（不涉及当前会话）。
 */
export function SessionSidebar({
  onSessionChange,
  onDeleteActiveSession,
  activeSessionId,
  refreshTrigger,
}: Props) {
  const [collapsed, setCollapsed] = useState(false)
  const [loading, setLoading] = useState(false)
  const setSessions = useChatStore((s) => s.setSessions)
  const sessions = useChatStore((s) => s.sessions)
  // 记录上次刷新时的 activeSessionId，避免首次挂载时多余请求
  const lastRefreshedForIdRef = useRef<string | null>(null)

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

  // 监听 activeSessionId 变化（切换会话/新建会话时自动刷新列表）
  useEffect(() => {
    if (activeSessionId && activeSessionId !== lastRefreshedForIdRef.current) {
      lastRefreshedForIdRef.current = activeSessionId
      fetchSessions()
    }
  }, [activeSessionId, fetchSessions])

  // 监听外部刷新信号（Home 发送消息成功后触发）
  useEffect(() => {
    if (refreshTrigger && refreshTrigger > 0) {
      fetchSessions()
    }
  }, [refreshTrigger, fetchSessions])

  const handleNewSession = async () => {
    setLoading(true)
    try {
      const result = await createSession()
      // 单入口：仅通知父组件切换到新会话，不直接改 store
      onSessionChange(result.session_id)
    } catch {
      // 新建失败时刷新列表，避免 UI 出现"幽灵"按钮状态
      await fetchSessions()
    } finally {
      setLoading(false)
    }
  }

  const handleSelectSession = (session: SessionInfo) => {
    if (session.session_id === activeSessionId) return
    // 单入口：仅通知父组件切换；store 副作用（清空消息/同步确认状态等）由 Home 集中处理
    onSessionChange(session.session_id)
  }

  const handleDeleteSession = async (e: React.MouseEvent, session: SessionInfo) => {
    e.stopPropagation()
    try {
      await deleteSession(session.session_id)
      if (session.session_id === activeSessionId) {
        // 当前活跃会话被删：通知父组件决定下一个活跃会话
        onDeleteActiveSession?.(session.session_id)
      } else {
        // 非当前活跃会话：仅刷新列表
        await fetchSessions()
      }
    } catch {
      /* ignore */
    }
  }

  if (collapsed) {
    return (
      <div className="w-12 bg-white border-l border-slate-200 flex flex-col items-center py-4 gap-3 flex-shrink-0">
        <button
          onClick={() => setCollapsed(false)}
          className="p-2 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
          title="展开会话列表"
        >
          <ChevronLeft size={18} />
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
    <div className="w-64 bg-white border-l border-slate-200 flex flex-col flex-shrink-0">
      <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
        <span className="text-sm font-semibold text-slate-700">会话历史</span>
        <button
          onClick={() => setCollapsed(true)}
          className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
          title="收起会话列表"
        >
          <ChevronRight size={16} />
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
