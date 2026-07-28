/**
 * 观察池视图组件（Task 7）。
 *
 * 设计要点：
 * - 显示当前观察池股票（按 category 分组）
 * - 空数据 → "暂无数据" 占位
 * - 入池/出池由父页面 / IndexPage 处理
 */
import { Trash2 } from 'lucide-react'
import type { WatchlistStock } from './types'

/** 类别 → 展示标签。 */
const CATEGORY_LABELS: Record<number, string> = {
  1: '主线龙头',
  2: '周期共振',
  3: '低位补涨',
  4: '分歧抗跌',
  5: '观察池候选',
}

export interface WatchlistProps {
  items: WatchlistStock[]
  onRemove?: (stockCode: string) => void
  loading?: boolean
  error?: string | null
}

export function Watchlist({ items, onRemove, loading, error }: WatchlistProps) {
  if (loading) {
    return (
      <div
        className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-500"
        role="status"
      >
        加载观察池…
      </div>
    )
  }
  if (error) {
    return (
      <div
        className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700"
        role="alert"
      >
        {error}
      </div>
    )
  }
  if (items.length === 0) {
    return (
      <div
        className="rounded-xl border border-dashed border-slate-200 bg-white p-4 text-center text-sm text-slate-400"
        role="status"
      >
        暂无观察池股票
      </div>
    )
  }

  // 按 category 分组
  const grouped: Record<number, WatchlistStock[]> = {}
  for (const s of items) {
    if (!grouped[s.category]) grouped[s.category] = []
    grouped[s.category].push(s)
  }
  const categories = Object.keys(grouped)
    .map((k) => Number(k))
    .sort((a, b) => a - b)

  return (
    <section
      className="rounded-xl border border-slate-200 bg-white p-4"
      aria-label="观察池"
    >
      <header className="mb-3">
        <h3 className="text-sm font-semibold text-slate-700">
          观察池（{items.length} 只）
        </h3>
      </header>
      <div className="space-y-4">
        {categories.map((cat) => (
          <div key={cat}>
            <p className="mb-1.5 text-xs font-medium text-slate-500">
              {CATEGORY_LABELS[cat] ?? `类别 ${cat}`}（{grouped[cat].length}）
            </p>
            <ul className="divide-y divide-slate-100">
              {grouped[cat].map((s) => (
                <li
                  key={s.stock_code}
                  className="flex items-center justify-between py-1.5"
                >
                  <div className="flex-1 min-w-0">
                    <p className="truncate text-sm font-medium text-slate-700">
                      {s.stock_name}
                      <span className="ml-1 text-xs text-slate-400">
                        {s.stock_code}
                      </span>
                    </p>
                    {s.notes && (
                      <p className="truncate text-xs text-slate-500">
                        {s.notes}
                      </p>
                    )}
                  </div>
                  {onRemove && (
                    <button
                      type="button"
                      onClick={() => onRemove(s.stock_code)}
                      className="ml-2 rounded-md p-1 text-slate-400 hover:bg-rose-50 hover:text-rose-600"
                      aria-label={`移除 ${s.stock_name}`}
                    >
                      <Trash2 size={14} />
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  )
}
