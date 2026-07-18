/**
 * Task 3 — HotspotCard 单条热点卡片。
 *
 * 业务红线：
 * - 标题是原生 `<a target="_blank" rel="noopener noreferrer">`，点击直接打开原文 URL，
 *   不触发 AI 研判、不向回调传递新闻全文。
 * - "AI 深度研判"是独立按钮，调用 onAnalyze(item)，由父组件发起锁定会话创建。
 * - 仅展示标题、来源、摘要、发布时间；不展示/不传递任何 content/全文。
 */
import { ExternalLink, Sparkles } from 'lucide-react'
import type { HotspotItem } from '../../features/news/api'

interface Props {
  item: HotspotItem
  onAnalyze: (item: HotspotItem) => void
}

/**
 * 把 ISO 时间字符串格式化为简短的本地化展示；失败时回退原值。
 */
function formatPublished(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  // 仅展示 MM-DD HH:mm，避免与时区耦合的歧义
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function HotspotCard({ item, onAnalyze }: Props) {
  return (
    <article
      className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm hover:border-indigo-200 transition-colors"
      data-news-id={item.id}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-sm font-semibold text-slate-800 hover:text-indigo-600 transition-colors"
          >
            <span className="truncate">{item.title}</span>
            <ExternalLink size={12} className="shrink-0 text-slate-400" />
          </a>
          <div className="mt-1 flex items-center gap-2 text-[11px] text-slate-400">
            <span className="truncate">{item.source}</span>
            {item.published_at && (
              <>
                <span aria-hidden>·</span>
                <time dateTime={item.published_at}>{formatPublished(item.published_at)}</time>
              </>
            )}
          </div>
        </div>
        <button
          type="button"
          onClick={() => onAnalyze(item)}
          className="inline-flex items-center gap-1 rounded-lg border border-indigo-200 bg-indigo-50 px-2.5 py-1.5 text-xs font-medium text-indigo-700 hover:bg-indigo-100 transition-colors"
          aria-label="AI 深度研判"
          title="AI 深度研判"
        >
          <Sparkles size={12} />
          深度研判
        </button>
      </div>
      {item.summary && (
        <p className="mt-2 text-xs text-slate-500 line-clamp-2">{item.summary}</p>
      )}
    </article>
  )
}

export type { HotspotItem }
