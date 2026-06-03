import { useRef, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Message, ThinkingStep } from '../hooks/useChatStore'
import { Bot, User, AlertTriangle, MapPin, TrendingUp, RefreshCw, Eye, ThumbsUp, Map, Loader2, Check } from 'lucide-react'
import { getTrending, TrendingItem } from '../utils/api'

interface Props {
  messages: Message[]
  isLoading: boolean
  isEscalated: boolean
  thinkingSteps: ThinkingStep[]
  onQuickSend?: (text: string) => void
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

function _extractItineraryId(content: string): string | null {
  const match = content.match(/itinerary_id["\s:]+["']?([a-f0-9]{16})/i)
  if (match) return match[1]
  const match2 = content.match(/行程概览已生成.*?id[：:]\s*([a-f0-9]{16})/i)
  if (match2) return match2[1]
  const match3 = content.match(/([a-f0-9]{16})/i)
  if (match3 && content.includes('行程概览')) return match3[1]
  return null
}

function _isItineraryConfirmPrompt(content: string): boolean {
  // 只要包含行程安排内容，就显示"满意，生成概览"按钮
  const hasItinerary = /第[1-9]天|第[一二三四五六七八九]天|Day\s*[1-9]|行程安排|每日行程/.test(content)
  return hasItinerary
}

export function ChatWindow({ messages, isLoading, isEscalated, thinkingSteps, onQuickSend }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  const handleViewItinerary = (itineraryId: string) => {
    navigate(`/itinerary/${itineraryId}`)
  }

  // 一旦已生成行程概览，禁用所有版本的"满意"按钮，防止重复生成
  const hasConfirmedItinerary = messages.some(
    (m) => m.role === 'assistant' && _extractItineraryId(m.content)
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
            {msg.role === 'assistant' && !msg.isStreaming && _isItineraryConfirmPrompt(msg.content) && (
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
            )}
            {msg.role === 'assistant' && !msg.isStreaming && _extractItineraryId(msg.content) && (
              <button
                onClick={() => handleViewItinerary(_extractItineraryId(msg.content)!)}
                className="mt-3 flex items-center gap-3 px-5 py-3.5 bg-gradient-to-r from-sky-500 to-blue-600 text-white rounded-2xl text-sm font-medium hover:from-sky-600 hover:to-blue-700 transition-all shadow-lg shadow-sky-200/60 active:scale-[0.97] w-fit"
              >
                <div className="w-10 h-10 rounded-xl bg-white/20 flex items-center justify-center flex-shrink-0">
                  <Map size={20} className="text-white" />
                </div>
                <div className="text-left">
                  <div className="font-semibold text-[15px]">查看行程概览</div>
                  <div className="text-white/70 text-xs mt-0.5">点击查看完整行程卡片</div>
                </div>
                <Eye size={16} className="text-white/60 ml-2" />
              </button>
            )}
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

function WelcomeScreen({ onQuickSend }: { onQuickSend?: (text: string) => void }) {
  const [items, setItems] = useState<TrendingItem[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  const fetchTrending = async (isRefresh: boolean = false) => {
    if (isRefresh) {
      setRefreshing(true)
    } else {
      setLoading(true)
    }
    const data = await getTrending(isRefresh)
    setItems(data)
    setLoading(false)
    setRefreshing(false)
  }

  useEffect(() => {
    fetchTrending()
  }, [])

  const handleClick = (item: TrendingItem) => {
    if (onQuickSend) {
      const contentPart = item.content
        ? `\n\n资讯详情：${item.content}`
        : `\n\n简介：${item.summary}`
      onQuickSend(`我看到了一条旅游资讯：${item.title}${contentPart}\n\n请帮我分析一下这个目的地，介绍一下特色和旅行建议`)
    }
  }

  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-4">
      <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-sky-400 to-blue-500 flex items-center justify-center mb-6 shadow-lg shadow-sky-200">
        <MapPin size={32} className="text-white" />
      </div>
      <h2
        className="text-2xl font-bold text-slate-800 mb-2"
        style={{ fontFamily: 'var(--font-display)' }}
      >
        Claw 旅行规划师
      </h2>
      <p className="text-slate-500 text-sm max-w-md mb-6">
        告诉我你想去哪里，我来帮你搜索机票酒店、规划行程、推荐美食。
        你的专属AI旅行助手，让每一次出发都轻松无忧。
      </p>

      <div className="w-full max-w-md">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-1.5 text-sm font-medium text-slate-600">
            <TrendingUp size={14} className="text-orange-500" />
            旅游热点资讯
          </div>
          <button
            onClick={() => fetchTrending(true)}
            disabled={refreshing}
            className="flex items-center gap-1 text-xs text-slate-400 hover:text-sky-500 transition-colors"
          >
            <RefreshCw size={12} className={refreshing ? 'animate-spin' : ''} />
            换一批
          </button>
        </div>

        {loading ? (
          <div className="grid grid-cols-2 gap-2.5">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-24 rounded-xl bg-slate-100 animate-pulse" />
            ))}
          </div>
        ) : items.length > 0 ? (
          <div className="grid grid-cols-2 gap-2.5">
            {items.map((item, idx) => (
              <button
                key={idx}
                onClick={() => handleClick(item)}
                className="text-left relative overflow-hidden rounded-xl border border-slate-200 hover:border-sky-300 transition-all group h-24"
              >
                {item.img && (
                  <img
                    src={item.img}
                    alt=""
                    className="absolute inset-0 w-full h-full object-cover opacity-20 group-hover:opacity-30 transition-opacity"
                    loading="lazy"
                  />
                )}
                <div className="relative z-10 px-3 py-2.5 h-full flex flex-col justify-between">
                  <div>
                    <div className="flex items-center gap-1.5 mb-1">
                      <span className="text-[10px] font-medium text-orange-500 bg-orange-50/80 px-1.5 py-0.5 rounded flex-shrink-0">
                        {item.tag}
                      </span>
                      {item.hotChange === 'up' && (
                        <span className="text-[10px] text-red-400">↑</span>
                      )}
                      {item.hotChange === 'down' && (
                        <span className="text-[10px] text-green-400">↓</span>
                      )}
                    </div>
                    <p className="text-xs font-medium text-slate-700 group-hover:text-sky-600 truncate transition-colors">
                      {item.title}
                    </p>
                  </div>
                  <p className="text-[11px] text-slate-400 leading-tight truncate">
                    {item.summary}
                  </p>
                </div>
              </button>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            {[
              '🗺️ 帮我规划云南5日游',
              '✈️ 查北京到三亚机票',
              '🏨 三亚海景酒店推荐',
              '🍜 成都必吃美食攻略',
            ].map((text) => (
              <QuickAction key={text} text={text} onClick={onQuickSend} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function QuickAction({ text, onClick }: { text: string; onClick?: (text: string) => void }) {
  return (
    <button
      onClick={() => onClick?.(text)}
      className="text-left px-4 py-3 rounded-xl border border-slate-200 bg-white hover:border-sky-300 hover:bg-sky-50 transition-all text-sm text-slate-600 hover:text-sky-600"
    >
      {text}
    </button>
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
