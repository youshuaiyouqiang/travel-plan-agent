/**
 * Task 3 — 新闻来源审核后台。
 *
 * 业务红线（来源：plans/2026-07-17-news-agent-and-sources.md Task 3 Step 3）：
 * - 路由对所有人开放，授权边界由后端 403 强制；普通用户访问会看到"无权访问"提示。
 * - 不接受客户端传入 admin_user_id；管理员 ID 由后端启动期从 CLAW_ADMIN_USERNAME 解析。
 * - 审核操作走 POST /admin/news/sources/{source_id}/review，decision/reason 由前端表单提供。
 */
import { useEffect, useState } from 'react'
import { ArrowLeft, ShieldCheck, History } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { AppLayout } from '../components/AppLayout'
import {
  listNewsSources,
  reviewNewsSource,
  listNewsSourceAudits,
  type NewsSource,
  type NewsSourceAudit,
  type SourceStatus,
} from '../features/news/api'

const STATUS_LABELS: Record<SourceStatus, string> = {
  pending: '待审核',
  enabled: '已启用',
  lead_only: '仅线索',
  rejected: '已拒绝',
  blocked: '已封禁',
  needs_review: '需复核',
}

const STATUS_BADGE: Record<SourceStatus, string> = {
  pending: 'bg-amber-100 text-amber-700',
  enabled: 'bg-emerald-100 text-emerald-700',
  lead_only: 'bg-slate-100 text-slate-700',
  rejected: 'bg-rose-100 text-rose-700',
  blocked: 'bg-red-100 text-red-700',
  needs_review: 'bg-violet-100 text-violet-700',
}

const DECISIONS: SourceStatus[] = [
  'enabled',
  'lead_only',
  'needs_review',
  'rejected',
  'blocked',
  'pending',
]

export function NewsAdmin() {
  const navigate = useNavigate()
  const [sources, setSources] = useState<NewsSource[]>([])
  const [audits, setAudits] = useState<NewsSourceAudit[]>([])
  const [forbidden, setForbidden] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reviewingId, setReviewingId] = useState<string | null>(null)
  const [decision, setDecision] = useState<SourceStatus>('enabled')
  const [reason, setReason] = useState('')

  const loadAll = async () => {
    setLoading(true)
    setError(null)
    setForbidden(false)
    try {
      const [srcs, auds] = await Promise.all([
        listNewsSources(),
        listNewsSourceAudits(),
      ])
      setSources(srcs)
      setAudits(auds)
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      if (msg === 'FORBIDDEN') {
        setForbidden(true)
      } else {
        setError(msg)
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadAll()
  }, [])

  const handleSubmitReview = async (sourceId: string) => {
    if (!reason.trim()) {
      setError('请填写审核理由')
      return
    }
    setError(null)
    try {
      await reviewNewsSource(sourceId, decision, reason.trim())
      setReviewingId(null)
      setReason('')
      setDecision('enabled')
      await loadAll()
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      setError(msg === 'FORBIDDEN' ? '无权执行审核' : msg)
    }
  }

  return (
    <AppLayout>
      <div className="mx-auto max-w-5xl px-6 py-6">
        <div className="mb-6 flex items-center gap-3">
          <button
            type="button"
            onClick={() => navigate('/')}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            aria-label="返回"
          >
            <ArrowLeft size={18} />
          </button>
          <ShieldCheck size={20} className="text-indigo-600" />
          <h1
            className="text-lg font-semibold text-slate-800"
            style={{ fontFamily: 'var(--font-display)' }}
          >
            新闻来源审核
          </h1>
        </div>

        {forbidden && (
          <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-6 text-center text-sm text-rose-700">
            无权访问此页面。请联系系统管理员配置 <code>CLAW_ADMIN_USERNAME</code>。
          </div>
        )}

        {error && !forbidden && (
          <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
            {error}
          </div>
        )}

        {!forbidden && (
          <>
            <section className="mb-8">
              <h2 className="mb-3 text-sm font-semibold text-slate-700">来源列表</h2>
              {loading ? (
                <p className="text-sm text-slate-400">加载中…</p>
              ) : sources.length === 0 ? (
                <p className="text-sm text-slate-400">暂无来源记录。</p>
              ) : (
                <ul className="space-y-2">
                  {sources.map((s) => (
                    <li
                      key={s.id}
                      className="rounded-lg border border-slate-200 bg-white px-4 py-3"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-slate-800">{s.name}</span>
                            <span
                              className={
                                'rounded-full px-2 py-0.5 text-[11px] font-medium ' +
                                (STATUS_BADGE[s.status] ?? 'bg-slate-100 text-slate-700')
                              }
                            >
                              {STATUS_LABELS[s.status] ?? s.status}
                            </span>
                          </div>
                          <p className="mt-0.5 text-xs text-slate-500">
                            {s.domain} · 层级 {s.tier}
                          </p>
                          {s.ai_reason && (
                            <p className="mt-1 text-xs text-slate-400">
                              评分：{s.ai_score ?? 'N/A'} · {s.ai_reason}
                            </p>
                          )}
                        </div>
                        <button
                          type="button"
                          onClick={() => {
                            setReviewingId(reviewingId === s.id ? null : s.id)
                            setReason('')
                            setDecision('enabled')
                          }}
                          className="rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-xs font-medium text-indigo-700 hover:bg-indigo-100"
                        >
                          {reviewingId === s.id ? '取消' : '审核'}
                        </button>
                      </div>
                      {reviewingId === s.id && (
                        <div className="mt-3 space-y-2 border-t border-slate-100 pt-3">
                          <label className="block text-xs text-slate-500">决策</label>
                          <select
                            value={decision}
                            onChange={(e) => setDecision(e.target.value as SourceStatus)}
                            className="w-full rounded-md border border-slate-200 bg-white px-2 py-1.5 text-sm"
                          >
                            {DECISIONS.map((d) => (
                              <option key={d} value={d}>
                                {STATUS_LABELS[d]}（{d}）
                              </option>
                            ))}
                          </select>
                          <label className="block text-xs text-slate-500">理由</label>
                          <textarea
                            value={reason}
                            onChange={(e) => setReason(e.target.value)}
                            rows={2}
                            placeholder="审核理由（必填，1-500 字）"
                            className="w-full rounded-md border border-slate-200 bg-white px-2 py-1.5 text-sm"
                          />
                          <button
                            type="button"
                            onClick={() => void handleSubmitReview(s.id)}
                            className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700"
                          >
                            提交审核
                          </button>
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section>
              <h2 className="mb-3 flex items-center gap-1.5 text-sm font-semibold text-slate-700">
                <History size={14} />
                审核审计
              </h2>
              {audits.length === 0 ? (
                <p className="text-sm text-slate-400">暂无审计记录。</p>
              ) : (
                <ul className="space-y-1.5">
                  {audits.map((a) => (
                    <li
                      key={a.id}
                      className="rounded-md border border-slate-100 bg-white px-3 py-2 text-xs"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-medium text-slate-700">
                          {STATUS_LABELS[a.previous_status as SourceStatus] ?? a.previous_status}
                          {' → '}
                          {STATUS_LABELS[a.decision] ?? a.decision}
                        </span>
                        <time className="text-slate-400">{a.created_at}</time>
                      </div>
                      <p className="mt-0.5 text-slate-500">{a.reason}</p>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </>
        )}
      </div>
    </AppLayout>
  )
}
