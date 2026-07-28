/**
 * 复盘文展示组件（Task 7）。
 *
 * 设计要点：
 * - 渲染 Markdown 复盘文（LLM 输出的 9 章节 + 风险声明）
 * - 状态徽章：completed / degraded / no_data
 * - 不解析 Markdown 任何敏感字段；纯展示层
 */
import { useMemo } from 'react'
import type { ReviewReport } from './types'

const STATUS_BADGE: Record<string, { label: string; cls: string }> = {
  completed: { label: '已生成', cls: 'bg-emerald-100 text-emerald-700' },
  degraded: { label: '降级（缺章节）', cls: 'bg-amber-100 text-amber-700' },
  no_data: { label: '无数据', cls: 'bg-slate-100 text-slate-600' },
}

export interface ReviewReportViewProps {
  report: ReviewReport | null
  loading: boolean
  error: string | null
}

/** 极简 Markdown → HTML：只处理 ## 标题、列表、段落。 */
function renderMarkdown(md: string): string {
  const escaped = md
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  const lines = escaped.split('\n')
  const out: string[] = []
  let inList = false
  for (const raw of lines) {
    const line = raw.trimEnd()
    if (line.startsWith('## ')) {
      if (inList) {
        out.push('</ul>')
        inList = false
      }
      out.push(
        `<h2 class="mt-6 mb-2 text-base font-semibold text-slate-800">${escapeInline(line.slice(3))}</h2>`,
      )
    } else if (line.startsWith('- ')) {
      if (!inList) {
        out.push('<ul class="ml-4 list-disc space-y-1 text-sm text-slate-700">')
        inList = true
      }
      out.push(`<li>${escapeInline(line.slice(2))}</li>`)
    } else if (line.length === 0) {
      if (inList) {
        out.push('</ul>')
        inList = false
      }
      out.push('<div class="h-2"></div>')
    } else {
      if (inList) {
        out.push('</ul>')
        inList = false
      }
      out.push(
        `<p class="my-1.5 text-sm leading-relaxed text-slate-700">${escapeInline(line)}</p>`,
      )
    }
  }
  if (inList) out.push('</ul>')
  return out.join('')
}

function escapeInline(s: string): string {
  return s
    .replace(/`/g, '&#96;')
    .replace(/\*\*/g, '&#42;&#42;')
}

export function ReviewReportView({ report, loading, error }: ReviewReportViewProps) {
  const html = useMemo(
    () => (report ? renderMarkdown(report.content) : ''),
    [report],
  )

  if (loading) {
    return (
      <div
        className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-500"
        role="status"
      >
        加载复盘文…
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
  if (!report) {
    return (
      <div
        className="rounded-xl border border-dashed border-slate-200 bg-white p-4 text-center text-sm text-slate-400"
        role="status"
      >
        暂无复盘文
      </div>
    )
  }

  const badge = STATUS_BADGE[report.status] ?? {
    label: report.status,
    cls: 'bg-slate-100 text-slate-600',
  }

  return (
    <article
      className="rounded-xl border border-slate-200 bg-white p-5"
      aria-label="复盘文"
    >
      <header className="mb-4 flex items-center justify-between border-b border-slate-100 pb-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-800">
            复盘 · {report.trade_date}
          </h2>
          <p className="mt-0.5 text-xs text-slate-500">
            生成于 {new Date(report.created_at).toLocaleString('zh-CN')}
          </p>
        </div>
        <span
          className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${badge.cls}`}
        >
          {badge.label}
        </span>
      </header>
      <div
        className="prose prose-slate max-w-none"
        dangerouslySetInnerHTML={{ __html: html }}
      />
    </article>
  )
}
