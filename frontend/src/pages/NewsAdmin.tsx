/**
 * Task 3 — 新闻来源审核后台。
 *
 * 业务红线（来源：plans/2026-07-17-news-agent-and-sources.md Task 3 Step 3）：
 * - 路由对所有人开放，授权边界由后端 403 强制；普通用户访问会看到"无权访问"提示。
 * - 不接受客户端传入 admin_user_id；管理员 ID 由后端启动期从 YUNHE_ADMIN_USERNAME 解析。
 * - 审核操作走 POST /admin/news/sources/{source_id}/review，decision/reason 由前端表单提供。
 * - 区分 scoring_mode：builtin_whitelist 显示"产品内置"徽章，无评分；
 *   ai_candidate 显示"AI 评分"徽章，含 6 维度子分明细。
 */
import { useEffect, useState } from 'react'
import { ArrowLeft, ShieldCheck, History, Database } from 'lucide-react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { AppLayout } from '../components/AppLayout'
import {
  listNewsSources,
  reviewNewsSource,
  listNewsSourceAudits,
  listNewsSourceInits,
  registerBuiltinSource,
  type NewsSource,
  type NewsSourceAudit,
  type NewsSourceInit,
  type SourceStatus,
  type ScoringMode,
  type SourceSubscores,
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

const SCORING_MODE_LABELS: Record<ScoringMode, string> = {
  builtin_whitelist: '产品内置',
  ai_candidate: 'AI 评分',
}

const SCORING_MODE_BADGE: Record<ScoringMode, string> = {
  builtin_whitelist: 'bg-slate-200 text-slate-700',
  ai_candidate: 'bg-indigo-100 text-indigo-700',
}

const SUBSCORE_LABELS: Record<keyof SourceSubscores, string> = {
  publisher_authority: '主体权威性',
  domain_brand: '域名-品牌一致性',
  topic_relevance: '领域相关性',
  editorial_standard: '编辑标准',
  accessibility: '可访问性',
  risk_signals: '风险信号',
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
  const [searchParams] = useSearchParams()
  const focusedSourceId = searchParams.get('source')
  const [sources, setSources] = useState<NewsSource[]>([])
  const [audits, setAudits] = useState<NewsSourceAudit[]>([])
  const [inits, setInits] = useState<NewsSourceInit[]>([])
  const [forbidden, setForbidden] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reviewingId, setReviewingId] = useState<string | null>(null)
  const [decision, setDecision] = useState<SourceStatus>('enabled')
  const [reason, setReason] = useState('')
  const [registerOpen, setRegisterOpen] = useState(false)
  const [registerDomain, setRegisterDomain] = useState('')
  const [registerName, setRegisterName] = useState('')
  const [registerTier, setRegisterTier] = useState<
    'mainstream' | 'aggregator' | 'official'
  >('mainstream')

  const loadAll = async () => {
    setLoading(true)
    setError(null)
    setForbidden(false)
    try {
      const [srcs, auds, initsResp] = await Promise.all([
        listNewsSources(),
        listNewsSourceAudits(),
        listNewsSourceInits(),
      ])
      setSources(srcs)
      setAudits(auds)
      setInits(initsResp)
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

  // 支持从证据卡片跳转过来时高亮并滚动定位到该来源。
  // 触发条件：URL 含 ?source=xxx 且来源已加载。
  useEffect(() => {
    if (!focusedSourceId || loading || sources.length === 0) return
    const el = document.getElementById(`source-${focusedSourceId}`)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }, [focusedSourceId, loading, sources])

  // focused 来源的视觉强调（仅短促高亮，不持久）。
  const isFocused = (id: string) => id === focusedSourceId

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

  const handleSubmitRegister = async () => {
    if (!registerDomain.trim() || !registerName.trim()) {
      setError('域名与名称均必填')
      return
    }
    setError(null)
    try {
      await registerBuiltinSource({
        domain: registerDomain.trim(),
        name: registerName.trim(),
        tier: registerTier,
      })
      setRegisterOpen(false)
      setRegisterDomain('')
      setRegisterName('')
      setRegisterTier('mainstream')
      await loadAll()
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      setError(msg === 'FORBIDDEN' ? '无权执行注册' : msg)
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
            无权访问此页面。请联系系统管理员配置 <code>YUNHE_ADMIN_USERNAME</code>。
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
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-sm font-semibold text-slate-700">来源列表</h2>
                <button
                  type="button"
                  onClick={() => setRegisterOpen((v) => !v)}
                  className="rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-xs font-medium text-indigo-700 hover:bg-indigo-100"
                >
                  {registerOpen ? '取消' : '注册内置白名单'}
                </button>
              </div>
              {registerOpen && (
                <div className="mb-3 space-y-2 rounded-lg border border-indigo-200 bg-indigo-50/50 px-4 py-3">
                  <div className="flex gap-2">
                    <input
                      type="text"
                      placeholder="域名（如 example.com）"
                      value={registerDomain}
                      onChange={(e) => setRegisterDomain(e.target.value)}
                      className="flex-1 rounded-md border border-slate-200 bg-white px-2 py-1.5 text-sm"
                    />
                    <input
                      type="text"
                      placeholder="显示名"
                      value={registerName}
                      onChange={(e) => setRegisterName(e.target.value)}
                      className="flex-1 rounded-md border border-slate-200 bg-white px-2 py-1.5 text-sm"
                    />
                    <select
                      value={registerTier}
                      onChange={(e) =>
                        setRegisterTier(
                          e.target.value as
                            | 'mainstream'
                            | 'aggregator'
                            | 'official',
                        )
                      }
                      className="rounded-md border border-slate-200 bg-white px-2 py-1.5 text-sm"
                    >
                      <option value="mainstream">mainstream</option>
                      <option value="aggregator">aggregator</option>
                      <option value="official">official</option>
                    </select>
                  </div>
                  <button
                    type="button"
                    onClick={() => void handleSubmitRegister()}
                    className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700"
                  >
                    提交注册
                  </button>
                </div>
              )}
              {loading ? (
                <p className="text-sm text-slate-400">加载中…</p>
              ) : sources.length === 0 ? (
                <p className="text-sm text-slate-400">暂无来源记录。</p>
              ) : (
                <ul className="space-y-2">
                  {sources.map((s) => (
                    <li
                      key={s.id}
                      id={`source-${s.id}`}
                      className={
                        'rounded-lg border bg-white px-4 py-3 transition-colors ' +
                        (isFocused(s.id)
                          ? 'border-indigo-300 ring-2 ring-indigo-200'
                          : 'border-slate-200')
                      }
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-slate-800">
                              {s.name}
                            </span>
                            <span
                              className={
                                'rounded-full px-2 py-0.5 text-[11px] font-medium ' +
                                (STATUS_BADGE[s.status] ??
                                  'bg-slate-100 text-slate-700')
                              }
                            >
                              {STATUS_LABELS[s.status] ?? s.status}
                            </span>
                            <span
                              className={
                                'rounded-full px-2 py-0.5 text-[11px] font-medium ' +
                                (SCORING_MODE_BADGE[s.scoring_mode] ??
                                  'bg-slate-100 text-slate-700')
                              }
                            >
                              {SCORING_MODE_LABELS[s.scoring_mode] ??
                                s.scoring_mode}
                            </span>
                          </div>
                          <p className="mt-0.5 text-xs text-slate-500">
                            {s.domain} · 层级 {s.tier}
                          </p>
                          {s.scoring_mode === 'builtin_whitelist' ? (
                            <p className="mt-1 text-xs text-slate-400">
                              内置白名单 · 来源元数据由产品配置，不参与 AI 评分
                            </p>
                          ) : (
                            <>
                              <p className="mt-1 text-xs text-slate-400">
                                评分：{s.ai_score ?? 'N/A'} ·{' '}
                                {s.ai_reason || '无理由'}
                              </p>
                              {s.ai_subscores &&
                                Object.keys(s.ai_subscores).length > 0 && (
                                  <details className="mt-1 text-xs text-slate-500">
                                    <summary className="cursor-pointer text-slate-400 hover:text-slate-600">
                                      6 维度子分明细
                                    </summary>
                                    <ul className="mt-1 space-y-0.5 pl-2">
                                      {(
                                        Object.keys(SUBSCORE_LABELS) as Array<
                                          keyof SourceSubscores
                                        >
                                      ).map((k) => {
                                        const v = s.ai_subscores[k]
                                        if (v == null) return null
                                        return (
                                          <li
                                            key={k}
                                            className="flex justify-between"
                                          >
                                            <span>
                                              {SUBSCORE_LABELS[k]}
                                            </span>
                                            <span className="font-mono text-slate-600">
                                              {v.toFixed(2)}
                                            </span>
                                          </li>
                                        )
                                      })}
                                    </ul>
                                  </details>
                                )}
                            </>
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
                          <label className="block text-xs text-slate-500">
                            决策
                          </label>
                          <select
                            value={decision}
                            onChange={(e) =>
                              setDecision(e.target.value as SourceStatus)
                            }
                            className="w-full rounded-md border border-slate-200 bg-white px-2 py-1.5 text-sm"
                          >
                            {DECISIONS.map((d) => (
                              <option key={d} value={d}>
                                {STATUS_LABELS[d]}（{d}）
                              </option>
                            ))}
                          </select>
                          <label className="block text-xs text-slate-500">
                            理由
                          </label>
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

            <section className="mb-8">
              <h2 className="mb-3 flex items-center gap-1.5 text-sm font-semibold text-slate-700">
                <Database size={14} />
                来源初始化
              </h2>
              {inits.length === 0 ? (
                <p className="text-sm text-slate-400">暂无来源初始化事件。</p>
              ) : (
                <ul className="space-y-1.5">
                  {inits.map((i) => (
                    <li
                      key={i.id}
                      className="rounded-md border border-slate-100 bg-white px-3 py-2 text-xs"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-medium text-slate-700">
                          {i.domain} · 层级 {i.tier}
                        </span>
                        <time className="text-slate-400">{i.init_at}</time>
                      </div>
                      <p className="mt-0.5 text-slate-500">
                        <span
                          className={
                            'mr-1 inline-block rounded-full px-1.5 py-0.5 text-[10px] font-medium ' +
                            (SCORING_MODE_BADGE[i.scoring_mode] ??
                              'bg-slate-100 text-slate-700')
                          }
                        >
                          {SCORING_MODE_LABELS[i.scoring_mode] ??
                            i.scoring_mode}
                        </span>
                        {i.init_reason}
                      </p>
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
                <p className="text-sm text-slate-400">
                  尚无管理员审核记录。点击来源右侧的「审核」按钮开始审核。
                </p>
              ) : (
                <ul className="space-y-1.5">
                  {audits.map((a) => (
                    <li
                      key={a.id}
                      data-testid={`audit-${a.id}`}
                      data-source-id={a.source_id}
                      className="rounded-md border border-slate-100 bg-white px-3 py-2 text-xs"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-medium text-slate-700">
                          {a.source_domain || '(来源已删除)'}
                          {a.source_name ? ` · ${a.source_name}` : ''}
                        </span>
                        <time className="text-slate-400">{a.created_at}</time>
                      </div>
                      <div className="mt-0.5 flex items-center gap-2 text-slate-500">
                        <span>
                          {STATUS_LABELS[a.previous_status as SourceStatus] ??
                            a.previous_status}
                          {' → '}
                          {STATUS_LABELS[a.decision] ?? a.decision}
                        </span>
                        <span className="text-slate-300">·</span>
                        <span className="text-slate-400">系统管理员</span>
                      </div>
                      <p className="mt-0.5 text-slate-500" data-testid={`audit-reason-${a.id}`}>
                        理由：{a.reason}
                      </p>
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
