import { useState, useRef, useEffect } from 'react'
import { Send, RotateCcw, Square, ChevronDown, Bot } from 'lucide-react'
import type { AgentInfo } from '../features/agent/api'

interface Props {
  onSend: (message: string) => void
  isLoading: boolean
  isEscalated: boolean
  onClear: () => void
  onStop: () => void
  agents: AgentInfo[]
  activeAgentId: string | null
  onAgentChange: (agentId: string) => void
}

export function ChatInput({ onSend, isLoading, isEscalated, onClear, onStop, agents, activeAgentId, onAgentChange }: Props) {
  const [text, setText] = useState('')
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  // 点击外部关闭下拉框
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleSubmit = () => {
    const trimmed = text.trim()
    if (!trimmed || isLoading) return
    onSend(trimmed)
    setText('')
    setTimeout(() => {
      inputRef.current?.focus()
    }, 50)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const disabled = isLoading || isEscalated

  const currentAgent = agents.find((a) => a.id === activeAgentId)
  const bottomLabel = currentAgent?.name ?? '云合 智能助手'

  return (
    <div className="border-t border-slate-200 bg-white px-4 py-3">
      <div className="max-w-3xl mx-auto flex items-end gap-2">
        <button
          onClick={onClear}
          className="p-2 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors flex-shrink-0"
          title="新对话"
        >
          <RotateCcw size={18} />
        </button>
        <div className="flex-1 relative">
          <textarea
            ref={inputRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              isEscalated
                ? '人工客服接入中，请稍候...'
                : '请输入您的问题...'
            }
            disabled={disabled}
            rows={1}
            className="w-full resize-none rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 pr-12 text-[15px] text-slate-800 placeholder:text-slate-400 focus:outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            style={{ maxHeight: '120px' }}
            onInput={(e) => {
              const target = e.target as HTMLTextAreaElement
              target.style.height = 'auto'
              target.style.height = Math.min(target.scrollHeight, 120) + 'px'
            }}
          />
          {isLoading ? (
            <button
              onClick={onStop}
              className="absolute right-2 bottom-2 p-2 rounded-lg bg-red-500 text-white hover:bg-red-600 transition-all"
              title="停止生成"
            >
              <Square size={16} />
            </button>
          ) : (
            <button
              onClick={handleSubmit}
              disabled={!text.trim() || disabled}
              className="absolute right-2 bottom-2 p-2 rounded-lg bg-indigo-500 text-white hover:bg-indigo-600 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
            >
              <Send size={16} />
            </button>
          )}
        </div>
        {/* 智能体选择器 */}
        <div className="relative flex-shrink-0" ref={dropdownRef}>
          <button
            onClick={() => setDropdownOpen(!dropdownOpen)}
            disabled={isLoading}
            className="flex items-center gap-1.5 px-3 py-2.5 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-sm font-medium transition-colors disabled:opacity-50"
            title="切换智能体"
          >
            <Bot size={16} className="text-indigo-500" />
            <span className="max-w-[80px] truncate">
              {currentAgent?.name ?? '云合'}
            </span>
            <ChevronDown size={14} className={`text-slate-400 transition-transform ${dropdownOpen ? 'rotate-180' : ''}`} />
          </button>
          {dropdownOpen && (
            <div className="absolute bottom-full right-0 mb-2 w-56 bg-white rounded-xl border border-slate-200 shadow-lg py-1 z-50">
              {agents.map((agent) => (
                <button
                  key={agent.id}
                  onClick={() => {
                    onAgentChange(agent.id)
                    setDropdownOpen(false)
                  }}
                  className={`w-full flex items-center gap-2.5 px-3 py-2.5 text-left text-sm transition-colors ${
                    agent.id === activeAgentId
                      ? 'bg-indigo-50 text-indigo-700 font-medium'
                      : 'text-slate-700 hover:bg-slate-50'
                  }`}
                >
                  <span className="text-base leading-none">{agent.icon}</span>
                  <div className="flex-1 min-w-0">
                    <div className="truncate">{agent.name}</div>
                    <div className="text-xs text-slate-400 truncate">{agent.description}</div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
      <p className="text-center text-xs text-slate-400 mt-2">
        {bottomLabel} · AI 生成内容仅供参考
      </p>
    </div>
  )
}
