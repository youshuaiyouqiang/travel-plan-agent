/**
 * Task 3 — EvidenceCards 证据卡片集合。
 *
 * 业务红线：
 * - 只渲染 verified / conflicted 的 EvidenceCard；正式事实结论仅由 enabled 来源支撑。
 * - unverified_leads 不得作为证据卡片呈现，也不得在此区域显示其 claim/source_name。
 * - conflicted 必须可见标识，便于用户识别分歧。
 */
import { CheckCircle2, AlertTriangle, ExternalLink } from 'lucide-react'
import type { EvidenceCard, UnverifiedLead } from '../../features/news/api'

interface Props {
  cards: EvidenceCard[]
  /** 未审核线索；本组件不渲染其内容，仅接受 prop 以强制类型契约。 */
  unverifiedLeads?: UnverifiedLead[]
  /** 可选：未审核线索数量提示（独立区块，不暴露 claim 文本）。 */
  showLeadCount?: boolean
}

export function EvidenceCards({ cards, unverifiedLeads = [], showLeadCount = false }: Props) {
  if (cards.length === 0 && (!showLeadCount || unverifiedLeads.length === 0)) {
    return null
  }

  return (
    <section aria-label="证据卡片" className="space-y-2">
      {cards.map((card, idx) => {
        const isConflicted = card.status === 'conflicted'
        return (
          <article
            key={`${card.source_name}-${idx}`}
            role="article"
            className={
              'rounded-lg border px-3 py-2 text-xs ' +
              (isConflicted
                ? 'border-amber-200 bg-amber-50/60'
                : 'border-emerald-200 bg-emerald-50/60')
            }
          >
            <div className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-1 font-medium text-slate-700">
                {isConflicted ? (
                  <AlertTriangle size={12} className="text-amber-600" />
                ) : (
                  <CheckCircle2 size={12} className="text-emerald-600" />
                )}
                {card.source_name}
                {isConflicted && (
                  <span
                    className="ml-1 rounded-full bg-amber-200/70 px-1.5 py-0.5 text-[10px] font-semibold text-amber-800"
                    aria-label="conflicted"
                  >
                    冲突
                  </span>
                )}
              </span>
              {card.url && (
                <a
                  href={card.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-0.5 text-slate-400 hover:text-indigo-600"
                  aria-label="查看来源"
                >
                  <ExternalLink size={11} />
                </a>
              )}
            </div>
            <p className="mt-1 text-slate-600">{card.claim}</p>
          </article>
        )
      })}

      {showLeadCount && unverifiedLeads.length > 0 && (
        <p className="text-[11px] text-slate-400">
          另有 {unverifiedLeads.length} 条未审核线索，不作为正式证据呈现。
        </p>
      )}
    </section>
  )
}

export type { EvidenceCard, UnverifiedLead }
