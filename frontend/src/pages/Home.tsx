import { useState, useEffect, useCallback, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ChatWindow } from '../components/ChatWindow'
import { ChatInput } from '../components/ChatInput'
import { SessionSidebar } from '../components/SessionSidebar'
import { NavSidebar } from '../components/NavSidebar'
import { HotspotCard } from '../components/news/HotspotCard'
import { useChatStore } from '../hooks/useChatStore'
import { useAuthStore } from '../hooks/useAuthStore'
import { useSessionStore } from '../hooks/useSessionStore'
import { sendMessageStream, createSession, listSessions, getSessionMessages } from '../features/chat/api'
import { fetchAgents, type AgentInfo } from '../features/agent/api'
import { createAnalysisSession, getHotspots, type HotspotItem } from '../features/news/api'
import { triggerNewsAnalysis } from '../features/news/analysis'
import { Sparkles, Flame } from 'lucide-react'

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
  } = useChatStore()

  const authUserId = useAuthStore((s) => s.userId)
  // ★ Task 2.2 修复：activeSessionId 改为派生自 store.sessionId，
  //   避免 useState 双源导致切换时 sessionId 错位。
  const activeSessionId = useChatStore((s) => s.sessionId)
  const [agentMap, setAgentMap] = useState<Record<string, AgentInfo>>({})
  const activeAgent = useSessionStore((s) => s.activeAgent)
  const [sessionListRefresh, setSessionListRefresh] = useState(0)
  const [hotspots, setHotspots] = useState<HotspotItem[]>([])
  const [analyzing, setAnalyzing] = useState(false)
  const [analyzeError, setAnalyzeError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const thinkingClearedRef = useRef(false)
  // P2-2：mount 一次守卫，避免 StrictMode 双调用导致重复初始化
  const initRef = useRef(false)

  useEffect(() => {
    if (authUserId && !userId) {
      setUserId(authUserId)
    }
  }, [authUserId, userId, setUserId])

  // 拉取热点池（只读缓存；后端不发起外部抓取）
  useEffect(() => {
    getHotspots()
      .then((items) => setHotspots(items.slice(0, 6)))
      .catch(() => {
        // 热点拉取失败不阻塞主对话
      })
  }, [sessionListRefresh])

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

  /**
   * 会话切换唯一切入口（Task 2.2 单入口收敛）。
   *
   * 业务契约：
   * 1. 立刻 ``setSessionId``：让 header / ChatInput / 路由守卫等依赖
   *    ``useChatStore.sessionId`` 的组件同步刷新。
   * 2. 立刻 ``clearMessages``：避免切换瞬间展示旧会话消息。
   * 3. 同步重置 ``useSessionStore`` 临时态（activeAgent / agentActions /
   *    sessionConfirmedPlan）。
   * 4. 异步 ``getSessionMessages`` + ``loadMessages`` 加载新会话消息。
   * 5. 异步 ``syncConfirmStatus`` 恢复确认状态。
   * 6. ``setSessionListRefresh`` 通知 SessionSidebar 刷新列表。
   */
  const handleSessionChange = useCallback(async (newSessionId: string) => {
    setSessionId(newSessionId)
    useChatStore.getState().clearMessages()
    useSessionStore.getState().clearAgentActions()
    useSessionStore.getState().setActiveAgent(null)
    useSessionStore.getState().setSessionConfirmedPlan(null)
    try {
      const msgs = await getSessionMessages(newSessionId)
      useChatStore.getState().loadMessages(msgs)
    } catch {
      // 消息加载失败时，clearMessages 已生效，messages=[] 是预期
    }
    useSessionStore.getState().syncConfirmStatus(newSessionId)
    setSessionListRefresh((n) => n + 1)
  }, [setSessionId])

  const initSession = useCallback(async () => {
    try {
      // 先尝试恢复上一次的会话
      const sessions = await listSessions()
      if (sessions.length > 0) {
        await handleSessionChange(sessions[0].session_id)
        return
      }
      // 没有历史会话，创建新会话
      const result = await createSession()
      await handleSessionChange(result.session_id)
    } catch {
      // 兜底：清空展示态，避免残留上一个会话的消息
      useChatStore.getState().clearMessages()
      useSessionStore.getState().clearAgentActions()
      useSessionStore.getState().setActiveAgent(null)
      useSessionStore.getState().setSessionConfirmedPlan(null)
    }
  }, [handleSessionChange])

  useEffect(() => {
    // P2-2：ref 守卫确保只在 mount 后执行一次初始化，
    // 同时把 initSession 列入依赖以满足 exhaustive-deps。
    if (initRef.current) return
    initRef.current = true
    if (!sessionId) {
      initSession()
    }
  }, [sessionId, initSession])

  // 点击"AI 深度研判"：创建 news_analysis_locked 会话，并自动驱动新闻 Agent
  // 基于锚点做一次深度研判。用户期望"点了就要看到分析"，因此创建会话后立即
  // 以默认研判问题调用 handleSend，触发后端 news agent 启动。
  // 业务红线：仅发送研判指令文本，不向会话或请求注入新闻全文；锚点由后端
  // chat 端点按 session.news_id 自动注入到 user message 前面。
  // 核心流程（createSession → switchSession → sendAnalysisPrompt）由
  // features/news/analysis.ts 的 triggerNewsAnalysis 封装，便于单测。
  const handleAnalyzeHotspot = async (item: HotspotItem) => {
    if (analyzing) return
    setAnalyzing(true)
    setAnalyzeError(null)
    try {
      const { session } = await triggerNewsAnalysis(item, {
        createSession: createAnalysisSession,
        sendAnalysisPrompt: handleSend,
        switchSession: handleSessionChange,
      })
      // handleSessionChange 会清空展示态 activeAgent，这里再写回锁定 Agent，
      // 让 header 与后续对话反映 news_analysis_locked 状态。
      useSessionStore.getState().applySessionRecord({
        mode: session.mode,
        locked_agent_id: session.locked_agent_id,
        news_id: session.news_id,
      })
      setActiveAgent(session.locked_agent_id)
      // 触发会话列表刷新，让侧边栏看到新会话
      setSessionListRefresh((n) => n + 1)
    } catch (e) {
      setAnalyzeError(e instanceof Error ? e.message : '创建研判会话失败')
    } finally {
      setAnalyzing(false)
    }
  }

  const handleNewChat = useCallback(async () => {
    abortRef.current?.abort()
    try {
      const result = await createSession()
      if (authUserId) setUserId(authUserId)
      // ★ Task 2.2：收敛到 handleSessionChange 单入口
      await handleSessionChange(result.session_id)
    } catch {
      // 兜底：清空展示态
      useChatStore.getState().clearMessages()
      useSessionStore.getState().clearAgentActions()
      useSessionStore.getState().setActiveAgent(null)
      useSessionStore.getState().setSessionConfirmedPlan(null)
    }
  }, [authUserId, setUserId, handleSessionChange])

  /**
   * 删除当前活跃会话（Task 2.2 单入口收敛）。
   *
   * 由 ``SessionSidebar.handleDeleteSession`` 在删除当前活跃会话时调用。
   * 业务契约：删除后必须确保 UI 仍指向一个有效会话 —
   *  - 优先选择剩余列表中的第一个会话（保持上下文连续）
   *  - 若没有剩余会话，创建一个新会话
   *  - 任何情况下都通过 ``handleSessionChange`` 收敛切换副作用
   */
  const handleDeleteActiveSession = useCallback(async (deletedId: string) => {
    try {
      const list = await listSessions()
      useChatStore.getState().setSessions(list)
      const next = list.find((s) => s.session_id !== deletedId)
      if (next) {
        await handleSessionChange(next.session_id)
        return
      }
      // 没有剩余会话：新建一个
      const result = await createSession()
      await handleSessionChange(result.session_id)
    } catch {
      // 兜底：清空当前展示态
      useChatStore.getState().clearMessages()
      useSessionStore.getState().clearAgentActions()
      useSessionStore.getState().setActiveAgent(null)
      useSessionStore.getState().setSessionConfirmedPlan(null)
    }
  }, [handleSessionChange])

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
      // activeAgent 在默认会话中仅作展示态：不随请求发送 agent_id，
      // 由服务端按 session mode 决策路由。agent_locked 模式下锁定信息也已持久化在服务端。
      const stream = sendMessageStream(
        {
          session_id: currentSessionId,
          user_id: currentUserId,
          message: text,
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
            // 后端旧格式 done.data="escalated" 会被解析为 {handled_by:"escalated", next_controller:"yunhe"}
            if (event.data.handled_by === 'escalated') {
              setEscalated(true)
            }
            break
          case 'error':
            finishLastMessage()
            clearThinkingSteps()
            appendToLastMessage(`\n\n⚠️ ${event.data.message}`)
            break
          case 'status':
            // thinking 状态，前端已经通过 thinkingSteps 展示
            break
          case 'tool_status':
            addThinkingStep(event.data)
            break
          case 'route':
            // 智能体路由事件 — 更新展示态 activeAgent
            setActiveAgent(event.data.agent_id)
            break
          case 'control_returned':
            // 默认模式单轮委派完成：控制权回到云合，清空展示态 activeAgent
            setActiveAgent(null)
            break
          case 'actions':
            // 智能体操作建议 — 更新操作卡片
            setAgentActions(event.data)
            break
          case 'evidence':
            // 结构化 evidence 卡片：来自后端 news_analysis_locked 会话的 SSE 事件，
            // 在 agent 文本前推送。把卡片挂到当前 streaming 的 assistant 消息上，
            // 由 ChatWindow 在气泡下方用 EvidenceCards 组件渲染。
            useChatStore.getState().attachEvidenceCards(event.data)
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
              } else if (!Array.isArray(d) && d && typeof d.question === 'string') {
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

        {/* 欢迎态热点卡片：仅在没有消息时展示，独立于 ChatWindow 内的 TrendingBar */}
        {!hasMessages && hotspots.length > 0 && (
          <div className="border-b border-slate-100 bg-slate-50/50 px-4 py-3 flex-shrink-0">
            <div className="flex items-center gap-1.5 mb-2 text-xs font-medium text-slate-500">
              <Flame size={13} className="text-orange-400" />
              今日热点 · 点击"深度研判"进入新闻 Agent 锁定会话
            </div>
            <div className="flex gap-2 overflow-x-auto pb-1">
              {hotspots.map((item) => (
                <div key={item.id} className="w-[280px] shrink-0">
                  <HotspotCard item={item} onAnalyze={handleAnalyzeHotspot} />
                </div>
              ))}
            </div>
            {analyzing && (
              <p className="mt-2 text-xs text-indigo-500">正在创建研判会话…</p>
            )}
            {analyzeError && (
              <p className="mt-2 text-xs text-rose-500">{analyzeError}</p>
            )}
          </div>
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
        onDeleteActiveSession={handleDeleteActiveSession}
        activeSessionId={activeSessionId}
        refreshTrigger={sessionListRefresh}
      />
    </div>
  )
}
