import { useState, useEffect, useCallback, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ChatWindow } from '../components/ChatWindow'
import { ChatInput } from '../components/ChatInput'
import { SessionSidebar } from '../components/SessionSidebar'
import { NavSidebar } from '../components/NavSidebar'
import { useChatStore } from '../hooks/useChatStore'
import { useAuthStore } from '../hooks/useAuthStore'
import { useSessionStore } from '../hooks/useSessionStore'
import { sendMessageStream, createSession, listSessions, getSessionMessages, fetchAgents, type AgentInfo } from '../utils/api'
import { Sparkles } from 'lucide-react'

export function Home() {
  const [searchParams, setSearchParams] = useSearchParams()
  const setActiveAgent = useSessionStore((s) => s.setActiveAgent)
  const setAgentActions = useSessionStore((s) => s.setAgentActions)
  const clearAgentActions = useSessionStore((s) => s.clearAgentActions)
  const {
    messages,
    isLoading,
    sessionId,
    userId,
    isEscalated,
    thinkingSteps,
    addMessage,
    appendToLastMessage,
    finishLastMessage,
    setLoading,
    setEscalated,
    setSessionId,
    setUserId,
    addThinkingStep,
    clearThinkingSteps,
    resetSession,
  } = useChatStore()

  const authUserId = useAuthStore((s) => s.userId)
  const [activeSessionId, setActiveSessionId] = useState(sessionId)
  const [agentMap, setAgentMap] = useState<Record<string, AgentInfo>>({})
  const activeAgent = useSessionStore((s) => s.activeAgent)
  const [sessionListRefresh, setSessionListRefresh] = useState(0)
  const abortRef = useRef<AbortController | null>(null)
  const thinkingClearedRef = useRef(false)

  useEffect(() => {
    if (authUserId && !userId) {
      setUserId(authUserId)
    }
  }, [authUserId, userId, setUserId])

  // 加载智能体列表，用于 header 动态显示当前激活智能体的名称/图标
  useEffect(() => {
    fetchAgents()
      .then((data) => {
        const map: Record<string, AgentInfo> = {}
        for (const a of [...data.builtin, ...data.custom, ...data.public]) {
          map[a.id] = a
        }
        setAgentMap(map)
      })
      .catch(() => {
        // 加载失败时 header 退回通用标题
      })
  }, [])

  // 读取 URL 中的 agent 参数，激活对应智能体（来自 Agent 中心"使用"按钮）
  useEffect(() => {
    const agentFromUrl = searchParams.get('agent')
    if (agentFromUrl) {
      setActiveAgent(agentFromUrl)
      // 用完即清，避免刷新后仍锁定
      searchParams.delete('agent')
      setSearchParams(searchParams, { replace: true })
    }
  }, [searchParams, setActiveAgent, setSearchParams])

  useEffect(() => {
    if (!sessionId) {
      initSession()
    }
  }, [])

  const initSession = useCallback(async () => {
    try {
      // 先尝试恢复上一次的会话
      const sessions = await listSessions()
      if (sessions.length > 0) {
        const lastSession = sessions[0]
        setSessionId(lastSession.session_id)
        if (authUserId) setUserId(authUserId)
        setActiveSessionId(lastSession.session_id)
        // 恢复该会话的消息
        try {
          const msgs = await getSessionMessages(lastSession.session_id)
          useChatStore.getState().loadMessages(msgs)
        } catch {
          // 消息加载失败，不阻塞
        }
        // ★ 恢复确认状态（页面刷新时同步sessionConfirmedPlan）
        useSessionStore.getState().syncConfirmStatus(lastSession.session_id)
        return
      }
      // 没有历史会话，创建新会话
      const result = await createSession()
      setSessionId(result.session_id)
      if (authUserId) setUserId(authUserId)
      setActiveSessionId(result.session_id)
    } catch {
      resetSession()
      setActiveSessionId(useChatStore.getState().sessionId)
    }
  }, [authUserId, setSessionId, setUserId, resetSession])

  const handleSessionChange = async (newSessionId: string) => {
    setActiveSessionId(newSessionId)
    setSessionId(newSessionId)
    resetSession()
    // 清除旧会话的临时状态
    useSessionStore.getState().clearAgentActions()
    useSessionStore.getState().setActiveAgent(null)
    // ★ 先重置确认状态，避免异步期间渲染使用旧值
    useSessionStore.getState().setSessionConfirmedPlan(null)
    // 从服务端恢复确认状态
    useSessionStore.getState().syncConfirmStatus(newSessionId)
    try {
      const msgs = await getSessionMessages(newSessionId)
      useChatStore.getState().loadMessages(msgs)
    } catch {
      // 消息加载失败，不阻塞
    }
  }

  const handleNewChat = async () => {
    abortRef.current?.abort()
    try {
      const result = await createSession()
      resetSession()
      setSessionId(result.session_id)
      if (authUserId) setUserId(authUserId)
      setActiveSessionId(result.session_id)
    } catch {
      resetSession()
      setActiveSessionId(useChatStore.getState().sessionId)
    }
  }

  const handleStop = () => {
    abortRef.current?.abort()
    finishLastMessage()
    setLoading(false)
  }

  const handleSend = async (text: string) => {
    addMessage({ role: 'user', content: text })
    // 先添加一条空的 assistant 消息，后续通过 appendToLastMessage 逐步填充
    addMessage({ role: 'assistant', content: '', isStreaming: true })
    setLoading(true)
    clearThinkingSteps()
    thinkingClearedRef.current = false
    // 清空上一轮的操作卡片
    clearAgentActions()

    const controller = new AbortController()
    abortRef.current = controller

    try {
      const currentSessionId = useChatStore.getState().sessionId
      const currentUserId = useChatStore.getState().userId
      const currentAgentId = useSessionStore.getState().activeAgent
      const stream = sendMessageStream(
        {
          session_id: currentSessionId,
          user_id: currentUserId,
          message: text,
          agent_id: currentAgentId ?? undefined,
        },
        controller.signal,
      )

      for await (const event of stream) {
        if (controller.signal.aborted) break

        switch (event.type) {
          case 'chunk':
            appendToLastMessage(event.data)
            // 收到第一个文本 chunk 时清除思考步骤（只执行一次）
            if (!thinkingClearedRef.current && useChatStore.getState().thinkingSteps.length > 0) {
              clearThinkingSteps()
              thinkingClearedRef.current = true
            }
            break
          case 'done':
            finishLastMessage()
            clearThinkingSteps()
            if (event.data === 'escalated') {
              setEscalated(true)
            }
            break
          case 'error':
            finishLastMessage()
            clearThinkingSteps()
            appendToLastMessage(`\n\n⚠️ ${event.data}`)
            break
          case 'status':
            // thinking 状态，前端已经通过 thinkingSteps 展示
            break
          case 'tool_status':
            addThinkingStep(event.data)
            break
          case 'route':
            // 智能体路由事件 — 更新激活态
            setActiveAgent(event.data)
            break
          case 'actions':
            // 智能体操作建议 — 更新操作卡片
            setAgentActions(event.data)
            break
          case 'need_input':
            // DynamicAgent 追问：把问题作为一条 assistant 消息追加显示。
            // 后端 data 形态可能为：
            //   - string（已构造好的问题文案）
            //   - string[]（缺失字段列表，如 ["destination", "date"]）
            //   - { question: string; field?: string }（文档示例形态）
            finishLastMessage()
            clearThinkingSteps()
            {
              const d = event.data
              let question = '请补充更多信息'
              if (typeof d === 'string') {
                question = d
              } else if (Array.isArray(d) && d.length > 0) {
                question = `请补充以下信息：${d.join('、')}`
              } else if (d && typeof d === 'object' && typeof d.question === 'string') {
                question = d.question
              }
              addMessage({
                role: 'assistant',
                content: `📋 ${question}`,
                isStreaming: false,
              })
            }
            break
        }
      }
    } catch (err) {
      if (controller.signal.aborted) {
        finishLastMessage()
        // 如果流式消息为空，添加停止提示
        const lastMsg = useChatStore.getState().messages.at(-1)
        if (lastMsg && lastMsg.role === 'assistant' && !lastMsg.content.trim()) {
          appendToLastMessage('⏹ 已停止生成')
        }
      } else if (err instanceof Error && err.message === 'AUTH_EXPIRED') {
        finishLastMessage()
        useAuthStore.getState().logout()
        return
      } else {
        finishLastMessage()
        const lastMsg = useChatStore.getState().messages.at(-1)
        if (lastMsg && lastMsg.role === 'assistant' && !lastMsg.content.trim()) {
          appendToLastMessage(`服务暂时不可用：${err instanceof Error ? err.message : '未知错误'}。请稍后重试。`)
        }
      }
    } finally {
      setLoading(false)
      abortRef.current = null
      // 消息发送完成后刷新右侧会话列表，确保新会话/消息数更新
      setSessionListRefresh((n) => n + 1)
    }
  }

  const currentAgent = activeAgent ? agentMap[activeAgent] : undefined
  const hasMessages = messages.length > 0

  return (
    <div className="h-screen flex bg-slate-50">
      <NavSidebar />

      <div className="flex-1 flex flex-col min-w-0">
        {/* 空对话时隐藏 header，让欢迎页更简洁（豆包风格） */}
        {hasMessages && (
          <header className="bg-white border-b border-slate-200 px-4 py-3 flex items-center gap-3 flex-shrink-0">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-sky-400 to-blue-500 flex items-center justify-center shadow-sm">
              {currentAgent?.icon ? (
                <span className="text-lg leading-none">{currentAgent.icon}</span>
              ) : (
                <Sparkles size={18} className="text-white" />
              )}
            </div>
            <div>
              <h1
                className="text-base font-semibold text-slate-800 leading-tight"
                style={{ fontFamily: 'var(--font-display)' }}
              >
                {currentAgent?.name ?? '云合 智能助手'}
              </h1>
              <p className="text-xs text-slate-400">
                {currentAgent?.description ?? '通用智能体 · 多技能协作 · 自由对话'}
              </p>
            </div>
          </header>
        )}

        <ChatWindow
          messages={messages}
          isLoading={isLoading}
          isEscalated={isEscalated}
          thinkingSteps={thinkingSteps}
          onQuickSend={handleSend}
          currentAgentInfo={currentAgent}
        />

        <ChatInput
          onSend={handleSend}
          isLoading={isLoading}
          isEscalated={isEscalated}
          onClear={handleNewChat}
          onStop={handleStop}
          agents={Object.values(agentMap)}
          activeAgentId={activeAgent ?? null}
          onAgentChange={(id) => setActiveAgent(id)}
        />
      </div>

      <SessionSidebar
        onSessionChange={handleSessionChange}
        activeSessionId={activeSessionId}
        refreshTrigger={sessionListRefresh}
      />
    </div>
  )
}
