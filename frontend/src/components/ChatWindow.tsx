import { useRef, useEffect } from 'react'
import { Message, ThinkingStep } from '../hooks/useChatStore'
import { useSessionStore } from '../hooks/useSessionStore'
import { User, AlertTriangle, MapPin, Sparkles, ThumbsUp, Loader2, Check } from 'lucide-react'
import { AgentActivationBanner } from './AgentActivationBanner'
import { AgentActionCard } from './AgentActionCard'
import { TrendingBar } from './TrendingBar'

import type { AgentInfo } from '../utils/api'

// ★ 多方案锚点解析
const MULTI_PLAN_ANCHOR_RE = /<!--MULTI_PLAN:(.*?)-->/

interface PlanMeta {
  type: string       // "sightseeing" | "budget"
  version: string    // "v1" | "v2" ...
}

interface MultiPlanAnchor {
  plans: Record<string, PlanMeta>
}

function parseMultiPlanAnchor(content: string): MultiPlanAnchor | null {
  const m = content.match(MULTI_PLAN_ANCHOR_RE)
  if (!m) return null
  const plans: Record<string, PlanMeta> = {}
  for (const part of m[1].split(',')) {
    const [key, val] = part.split('=')
    if (!key || !val) continue
    const [type, version] = val.split(':')
    plans[key] = { type, version: version || 'v1' }
  }
  return Object.keys(plans).length > 0 ? { plans } : null
}

interface Props {
  messages: Message[]
  isLoading: boolean
  isEscalated: boolean
  thinkingSteps: ThinkingStep[]
  onQuickSend?: (text: string) => void
  /** 当前激活的智能体信息（用于 WelcomeScreen 展示介绍） */
  currentAgentInfo?: AgentInfo | null
}

function _renderContent(content: string, isUser: boolean) {
  if (isUser) return content

  const parts = content.split(/(【基于记忆：[^】]+】)/g)
  if (parts.length <= 1) return content

  return parts.map((part, i) => {
    const match = part.match(/【基于记忆：([^】]+)】/)
    if (match) {
      return (
        <span
          key={i}
          className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-md bg-violet-50 text-violet-600 text-xs font-medium align-middle mx-0.5 border border-violet-100"
          title={`基于记忆：${match[1]}`}
        >
          <svg width="10" height="10" viewBox="0 0 16 16" fill="currentColor" className="flex-shrink-0">
            <path d="M8 1a4 4 0 0 0-4 4v2H3a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V8a1 1 0 0 0-1-1h-1V5a4 4 0 0 0-4-4zm2.5 6h-5V5a2.5 2.5 0 0 1 5 0v2z"/>
          </svg>
          {match[1]}
        </span>
      )
    }
    return part
  })
}

function _isItineraryConfirmPrompt(content: string): boolean {
  // 只要包含行程安排内容，就显示"满意，生成概览"按钮
  const hasItinerary = /第[1-9]天|第[一二三四五六七八九]天|Day\s*[1-9]|行程安排|每日行程/.test(content)
  return hasItinerary
}

export function ChatWindow({ messages, isLoading, isEscalated, thinkingSteps, onQuickSend, currentAgentInfo }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const activeAgent = useSessionStore((s) => s.activeAgent)
  const agentActions = useSessionStore((s) => s.agentActions)
  const sessionConfirmedPlan = useSessionStore((s) => s.sessionConfirmedPlan)
  const isConfirming = useSessionStore((s) => s.isConfirming)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  // 一旦已生成行程概览，禁用所有版本的"满意"按钮，防止重复生成。
  // P1-13：改用结构化 agentActions 检测（navigate 类型且 path 含 /itinerary/），
  // 不再从自由文本正则提取 itinerary_id。
  const hasConfirmedItinerary = agentActions.some(
    (a) => a.type === 'navigate' && typeof a.path === 'string' && a.path.includes('/itinerary/')
  )

  return (
    <div className="flex-1 overflow-y-auto scrollbar-thin px-4 py-6 space-y-4">
      {messages.length === 0 && <WelcomeScreen onQuickSend={onQuickSend} />}

      {messages.map((msg) => (
        <div
          key={msg.id}
          className={`animate-fade-in-up flex gap-3 max-w-3xl mx-auto ${
            msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'
          }`}
        >
          <Avatar role={msg.role} />
          <div
            className={`flex-1 min-w-0 ${
              msg.role === 'user' ? 'flex flex-col items-end' : ''
            }`}
          >
            <div
              className={`inline-block rounded-2xl px-4 py-3 max-w-[85%] text-[15px] leading-relaxed whitespace-pre-wrap break-words ${
                msg.role === 'user'
                  ? 'bg-sky-500 text-white rounded-br-md'
                  : 'bg-white text-slate-800 shadow-sm border border-slate-100 rounded-bl-md'
              }`}
            >
              {_renderContent(msg.content, msg.role === 'user')}
              {msg.isStreaming && (
                <span className="inline-block w-[2px] h-[1em] bg-sky-500 ml-0.5 align-middle animate-blink" />
              )}
            </div>
            {msg.status === 'escalated' && (
              <div className="mt-2 inline-flex items-center gap-1.5 text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded-full px-3 py-1">
                <AlertTriangle size={12} />
                已转接旅行顾问
              </div>
            )}
            {msg.role === 'assistant' && !msg.isStreaming && (() => {
  const anchor = parseMultiPlanAnchor(msg.content)
  const isSinglePlan = !anchor && _isItineraryConfirmPrompt(msg.content)
  const hasAnyConfirmed = sessionConfirmedPlan !== null

  // 单方案降级（旧流程或无锚点）
  if (isSinglePlan && !anchor) {
    return (
      <div className="mt-3 flex gap-2">
        <button
          onClick={() => onQuickSend?.('满意，请生成行程概览')}
          disabled={hasConfirmedItinerary}
          className={`flex items-center gap-1.5 px-4 py-2.5 rounded-xl text-sm font-medium transition-all active:scale-[0.98] ${
            hasConfirmedItinerary
              ? 'bg-slate-100 text-slate-400 cursor-not-allowed'
              : 'bg-gradient-to-r from-emerald-500 to-green-500 text-white hover:from-emerald-600 hover:to-green-600 shadow-md shadow-emerald-200'
          }`}
        >
          <ThumbsUp size={15} />
          {hasConfirmedItinerary ? '已生成概览' : '满意，生成概览'}
        </button>
      </div>
    )
  }

  // 无锚点且非单方案 → 不渲染按钮
  if (!anchor) return null

  // 多方案双按钮
  return (
    <div className="mt-3 flex gap-3 flex-wrap">
      {hasAnyConfirmed ? (
        <>
          <div className="text-xs text-slate-400 bg-slate-50 rounded-xl px-4 py-2.5 border border-slate-200">
            {sessionConfirmedPlan === 'plan1'
              ? '✅ 方案一（景点打卡型）已确认，行程概览已生成'
              : '方案一（景点打卡型）——本次会话已选择方案二'}
          </div>
          <div className="text-xs text-slate-400 bg-slate-50 rounded-xl px-4 py-2.5 border border-slate-200">
            {sessionConfirmedPlan === 'plan2'
              ? '✅ 方案二（经济实惠型）已确认，行程概览已生成'
              : '方案二（经济实惠型）——本次会话已选择方案一'}
          </div>
          <button
            onClick={() => {
              if (window.confirm('确定要更换方案吗？当前方案的概览将保留但标记为已废弃')) {
                const actions = useSessionStore.getState().agentActions
                const itineraryAction = actions.find(a => a.type === 'navigate' && a.path.includes('/itinerary/'))
                if (itineraryAction) {
                  const itineraryId = itineraryAction.path.split('/itinerary/')[1]?.split('/')[0] || ''
                  useSessionStore.getState().revokeConfirm(itineraryId, '')
                }
              }
            }}
            className="text-xs text-amber-600 hover:text-amber-700 underline"
          >
            ↩️ 撤销确认，重新选择
          </button>
        </>
      ) : (
        <>
          {anchor.plans.plan1 && (
            <button
              onClick={() => onQuickSend?.('选方案一，请生成景点打卡型行程概览')}
              disabled={isConfirming}
              className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl text-sm font-medium transition-all active:scale-[0.98] bg-gradient-to-r from-sky-500 to-blue-500 text-white hover:from-sky-600 hover:to-blue-600 shadow-md shadow-sky-200 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Sparkles size={15} />
              为方案一生成概览
              <span className="text-xs opacity-80">({anchor.plans.plan1.type})</span>
            </button>
          )}
          {anchor.plans.plan2 && (
            <button
              onClick={() => onQuickSend?.('选方案二，请生成经济实惠型行程概览')}
              disabled={isConfirming}
              className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl text-sm font-medium transition-all active:scale-[0.98] bg-gradient-to-r from-emerald-500 to-green-500 text-white hover:from-emerald-600 hover:to-green-600 shadow-md shadow-emerald-200 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <ThumbsUp size={15} />
              为方案二生成概览
              <span className="text-xs opacity-80">({anchor.plans.plan2.type})</span>
            </button>
          )}
        </>
      )}
    </div>
  )
})()}
            {/* P1-13：行程概览跳转按钮已移除，改由 agentActions 中的 navigate 类型
                action 通过 AgentActionCard 渲染（结构化，避免正则误匹配）。 */}
          </div>
        </div>
      ))}

      {isLoading && !messages.some((m) => m.isStreaming) && thinkingSteps.length === 0 && <TypingIndicator />}

      {isLoading && thinkingSteps.length > 0 && <ThinkingStepsIndicator steps={thinkingSteps} />}

      {isEscalated && !isLoading && messages.length > 0 && (
        <div className="max-w-3xl mx-auto">
          <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-amber-100 flex items-center justify-center flex-shrink-0">
              <AlertTriangle size={16} className="text-amber-600" />
            </div>
            <div>
              <p className="text-sm font-medium text-amber-800">旅行顾问接入中</p>
              <p className="text-xs text-amber-600">正在为您转接专属旅行顾问</p>
            </div>
          </div>
        </div>
      )}

      {/* 智能体激活提示 — 显示在消息列表底部。
          P1-14：传入结构化的 currentAgentInfo（由父组件从 agentMap 查询），
          支持任意 builtin / custom 智能体动态展示，不再硬编码 travel。 */}
      {activeAgent && (
        <div className="flex justify-center">
          <AgentActivationBanner agentInfo={currentAgentInfo} />
        </div>
      )}

      {/* 操作卡片 — 显示在最新一条助手消息之后 */}
      {agentActions.length > 0 && (
        <div className="flex justify-start max-w-3xl mx-auto">
          {agentActions.map((action, i) => (
            <AgentActionCard key={i} action={action} />
          ))}
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  )
}

function Avatar({ role }: { role: 'user' | 'assistant' }) {
  if (role === 'user') {
    return (
      <div className="w-8 h-8 rounded-full bg-sky-100 flex items-center justify-center flex-shrink-0">
        <User size={16} className="text-sky-600" />
      </div>
    )
  }
  return (
    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-sky-400 to-blue-500 flex items-center justify-center flex-shrink-0 shadow-sm">
      <MapPin size={16} className="text-white" />
    </div>
  )
}

function WelcomeScreen({ onQuickSend, currentAgentInfo }: { onQuickSend?: (text: string) => void; currentAgentInfo?: AgentInfo | null }) {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-4">
      {/* 当前智能体介绍 */}
      <div className="mb-6">
        <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-sky-400 to-blue-500 flex items-center justify-center mx-auto mb-4 shadow-lg shadow-sky-200">
          {currentAgentInfo?.icon ? (
            <span className="text-2xl leading-none">{currentAgentInfo.icon}</span>
          ) : (
            <Sparkles size={28} className="text-white" />
          )}
        </div>
        <h2
          className="text-xl font-bold text-slate-800 mb-1"
          style={{ fontFamily: 'var(--font-display)' }}
        >
          {currentAgentInfo?.name ?? '云合 智能助手'}
        </h2>
        <p className="text-slate-500 text-sm max-w-md">
          {currentAgentInfo?.welcome_message
            ? currentAgentInfo.welcome_message
            : currentAgentInfo?.description
              ? currentAgentInfo.description
              : '我是你的通用 AI 助手，可以自由对话、回答问题。也可以在 Agent 中心选择专业智能体来处理特定任务。'}
        </p>
      </div>

      {/* 热搜标签云 */}
      <div className="w-full mb-8">
        <TrendingBar onSelect={(text) => onQuickSend?.(text)} />
      </div>

      {/* 提示 */}
      <p className="text-xs text-slate-300">输入任意问题开始对话</p>
    </div>
  )
}

function TypingIndicator() {
  return (
    <div className="animate-fade-in-up flex gap-3 max-w-3xl mx-auto">
      <div className="w-8 h-8 rounded-full bg-gradient-to-br from-sky-400 to-blue-500 flex items-center justify-center flex-shrink-0 shadow-sm">
        <MapPin size={16} className="text-white" />
      </div>
      <div className="bg-white rounded-2xl rounded-bl-md px-5 py-4 shadow-sm border border-slate-100">
        <div className="flex gap-1.5">
          <span className="typing-dot w-2 h-2 bg-slate-400 rounded-full inline-block" />
          <span className="typing-dot w-2 h-2 bg-slate-400 rounded-full inline-block" />
          <span className="typing-dot w-2 h-2 bg-slate-400 rounded-full inline-block" />
        </div>
      </div>
    </div>
  )
}

function ThinkingStepsIndicator({ steps }: { steps: ThinkingStep[] }) {
  return (
    <div className="animate-fade-in-up flex gap-3 max-w-3xl mx-auto">
      <div className="w-8 h-8 rounded-full bg-gradient-to-br from-sky-400 to-blue-500 flex items-center justify-center flex-shrink-0 shadow-sm">
        <MapPin size={16} className="text-white" />
      </div>
      <div className="bg-white rounded-2xl rounded-bl-md px-5 py-4 shadow-sm border border-slate-100 min-w-[180px]">
        <div className="space-y-2">
          {steps.map((step) => (
            <div key={step.id} className="flex items-center gap-2 text-sm">
              {step.status === 'active' ? (
                <Loader2 size={14} className="text-sky-500 animate-spin flex-shrink-0" />
              ) : (
                <Check size={14} className="text-emerald-500 flex-shrink-0" />
              )}
              <span className={step.status === 'active' ? 'text-sky-600 font-medium' : 'text-slate-400'}>
                {step.text}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
