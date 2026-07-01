import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  ArrowLeft,
  Brain,
  Trash2,
  RefreshCw,
  Heart,
  BookOpen,
  Lightbulb,
  Sparkles,
  Clock,
  TrendingUp,
} from 'lucide-react'
import { getMemories, deleteMemory, MemoriesResponse, MemoryItem } from '../utils/api'

const _CATEGORY_CONFIG: Record<
  string,
  { icon: typeof Heart; color: string; bg: string; border: string; label: string }
> = {
  preference: {
    icon: Heart,
    color: 'text-pink-500',
    bg: 'bg-pink-50',
    border: 'border-pink-100',
    label: '偏好',
  },
  fact: {
    icon: BookOpen,
    color: 'text-blue-500',
    bg: 'bg-blue-50',
    border: 'border-blue-100',
    label: '事实',
  },
  experience: {
    icon: Lightbulb,
    color: 'text-amber-500',
    bg: 'bg-amber-50',
    border: 'border-amber-100',
    label: '经验',
  },
}

type TabKey = 'all' | 'preference' | 'fact' | 'experience'

function MemoryCard({
  item,
  memoryType,
  onDeleted,
  index,
}: {
  item: MemoryItem
  memoryType: 'short_term' | 'long_term'
  onDeleted: () => void
  index: number
}) {
  const cfg = _CATEGORY_CONFIG[item.category] || _CATEGORY_CONFIG.fact
  const Icon = cfg.icon
  const [deleting, setDeleting] = useState(false)

  const handleDelete = async () => {
    setDeleting(true)
    try {
      await deleteMemory(memoryType, item.id)
      onDeleted()
    } catch {
      /* ignore */
    } finally {
      setDeleting(false)
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04, duration: 0.3 }}
      className={`group relative rounded-xl border ${cfg.border} bg-white p-4 hover:shadow-md transition-all`}
    >
      <div className="flex items-start gap-3">
        <div
          className={`w-9 h-9 rounded-lg ${cfg.bg} flex items-center justify-center flex-shrink-0`}
        >
          <Icon size={16} className={cfg.color} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm text-slate-800 leading-relaxed">{item.content}</p>
          <div className="flex items-center gap-2 mt-2">
            <span
              className={`text-[11px] font-medium px-2 py-0.5 rounded-full ${cfg.bg} ${cfg.color}`}
            >
              {cfg.label}
            </span>
            {item.experience_tag && (
              <span
                className={`text-[11px] font-medium px-2 py-0.5 rounded-full ${
                  item.experience_tag === 'success'
                    ? 'bg-emerald-50 text-emerald-600'
                    : 'bg-red-50 text-red-500'
                }`}
              >
                {item.experience_tag === 'success' ? '✓ 成功经验' : '✗ 失败教训'}
              </span>
            )}
            <span className="text-[11px] text-slate-300 flex items-center gap-0.5">
              <TrendingUp size={9} />
              提取{item.extraction_count}次
            </span>
            {item.last_accessed_at && (
              <span className="text-[11px] text-slate-300 flex items-center gap-0.5">
                <Clock size={9} />
                {new Date(item.last_accessed_at).toLocaleDateString()}
              </span>
            )}
          </div>
        </div>
        <button
          onClick={handleDelete}
          disabled={deleting}
          className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg text-slate-300 hover:text-red-400 hover:bg-red-50 transition-all flex-shrink-0"
          title="删除记忆"
        >
          <Trash2 size={14} />
        </button>
      </div>
      {memoryType === 'short_term' && (
        <div className="absolute top-3 right-10">
          <span className="text-[10px] bg-sky-50 text-sky-500 px-1.5 py-0.5 rounded-full">
            短期
          </span>
        </div>
      )}
    </motion.div>
  )
}

export function MemoryPage() {
  const navigate = useNavigate()
  const [data, setData] = useState<MemoriesResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<TabKey>('all')

  const fetchMemories = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getMemories()
      setData(res)
    } catch {
      /* ignore */
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchMemories()
  }, [fetchMemories])

  const allMemories: (MemoryItem & { memoryType: 'short_term' | 'long_term' })[] = []
  if (data) {
    for (const m of data.long_term) {
      allMemories.push({ ...m, memoryType: 'long_term' })
    }
    for (const m of data.short_term) {
      allMemories.push({ ...m, memoryType: 'short_term' })
    }
  }

  const filtered =
    tab === 'all' ? allMemories : allMemories.filter((m) => m.category === tab)

  const summary = data?.summary ?? {
    total_ltm: 0,
    total_stm: 0,
    preferences: 0,
    facts: 0,
    experiences: 0,
  }
  const total = summary.total_ltm + summary.total_stm

  const tabs: { key: TabKey; label: string; count: number }[] = [
    { key: 'all', label: '全部', count: total },
    { key: 'preference', label: '偏好', count: summary.preferences },
    { key: 'fact', label: '事实', count: summary.facts },
    { key: 'experience', label: '经验', count: summary.experiences },
  ]

  return (
    <div className="h-screen flex flex-col bg-slate-50">
      <header className="bg-white border-b border-slate-200 px-4 py-3 flex-shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/')}
            className="w-8 h-8 rounded-lg bg-slate-100 flex items-center justify-center text-slate-400 hover:bg-slate-200 transition-colors"
          >
            <ArrowLeft size={16} />
          </button>
          <div className="flex-1 min-w-0">
            <h1 className="text-base font-semibold text-slate-800">记忆</h1>
            <p className="text-xs text-slate-400 mt-0.5">
              AI 自动从对话中提取你的偏好、事实和经验
            </p>
          </div>
          <button
            onClick={fetchMemories}
            disabled={loading}
            className="p-2 rounded-lg text-slate-400 hover:text-sky-500 hover:bg-sky-50 transition-colors"
            title="刷新"
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </header>

      <div className="bg-white border-b border-slate-100 px-4 py-3 flex-shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-xs">
            <div className="w-7 h-7 rounded-lg bg-violet-50 flex items-center justify-center">
              <Brain size={14} className="text-violet-500" />
            </div>
            <span className="text-slate-500">
              {total}条记忆
            </span>
          </div>
          <div className="flex items-center gap-1.5 text-xs">
            <div className="w-7 h-7 rounded-lg bg-emerald-50 flex items-center justify-center">
              <Sparkles size={14} className="text-emerald-500" />
            </div>
            <span className="text-slate-500">
              {summary.total_ltm}条长期
            </span>
          </div>
          <div className="flex items-center gap-1.5 text-xs">
            <div className="w-7 h-7 rounded-lg bg-sky-50 flex items-center justify-center">
              <Clock size={14} className="text-sky-500" />
            </div>
            <span className="text-slate-500">
              {summary.total_stm}条短期
            </span>
          </div>
        </div>
      </div>

      <div className="bg-white border-b border-slate-100 px-4 py-2 flex-shrink-0">
        <div className="flex gap-1">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                tab === t.key
                  ? 'bg-violet-50 text-violet-600'
                  : 'text-slate-400 hover:bg-slate-50 hover:text-slate-600'
              }`}
            >
              {t.label}
              {t.count > 0 && (
                <span className="ml-1 text-[10px] opacity-60">{t.count}</span>
              )}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto px-4 py-4">
        {loading && !data ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-violet-400 to-purple-500 flex items-center justify-center mx-auto mb-4 animate-pulse">
                <Brain size={24} className="text-white" />
              </div>
              <p className="text-slate-400 text-sm">加载记忆中...</p>
            </div>
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <Brain size={40} className="text-slate-200 mx-auto mb-3" />
              <p className="text-slate-400 text-sm">
                {tab === 'all' ? '暂无记忆' : `暂无${_CATEGORY_CONFIG[tab]?.label || ''}记忆`}
              </p>
              <p className="text-slate-300 text-xs mt-1">
                对话中会自动提取你的偏好和经验
              </p>
            </div>
          </div>
        ) : (
          <div className="max-w-2xl mx-auto space-y-3">
            <AnimatePresence mode="popLayout">
              {filtered.map((m, i) => (
                <MemoryCard
                  key={`${m.memoryType}-${m.id}`}
                  item={m}
                  memoryType={m.memoryType}
                  onDeleted={fetchMemories}
                  index={i}
                />
              ))}
            </AnimatePresence>
          </div>
        )}
      </div>
    </div>
  )
}
