/**
 * 大盘快照组件（Task 7）。
 *
 * 设计要点：
 * - 显示三大指数（sh/sz/cyb）+ 成交额 + 连续下跌天数 + MA20 状态
 * - 数据缺失显示 "—"（不臆测）
 * - 加载/错误态可访问（role=status / role=alert）
 */
import { ArrowUpRight, ArrowDownRight, Minus } from 'lucide-react'
import type { MarketSnapshot } from './types'

export interface MarketOverviewProps {
  snapshot: MarketSnapshot | null
  loading: boolean
  error: string | null
}

function IndexCard({
  label,
  value,
}: {
  label: string
  value: number | null
}) {
  if (value === null) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white px-3 py-2.5">
        <p className="text-xs text-slate-500">{label}</p>
        <p className="mt-1 text-lg font-semibold text-slate-400">—</p>
      </div>
    )
  }
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2.5">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-1 text-lg font-semibold text-slate-800">
        {value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}
      </p>
    </div>
  )
}

function VolumeCard({
  totalVolume,
  volumeChangePct,
}: {
  totalVolume: number | null
  volumeChangePct: number | null
}) {
  if (totalVolume === null) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white px-3 py-2.5">
        <p className="text-xs text-slate-500">两市成交额</p>
        <p className="mt-1 text-lg font-semibold text-slate-400">—</p>
      </div>
    )
  }
  const changeNode =
    volumeChangePct === null ? null : (
      <span
        className={
          volumeChangePct > 0
            ? 'ml-1 inline-flex items-center text-xs text-rose-500'
            : volumeChangePct < 0
              ? 'ml-1 inline-flex items-center text-xs text-emerald-500'
              : 'ml-1 inline-flex items-center text-xs text-slate-500'
        }
      >
        {volumeChangePct > 0 ? (
          <ArrowUpRight size={12} />
        ) : volumeChangePct < 0 ? (
          <ArrowDownRight size={12} />
        ) : (
          <Minus size={12} />
        )}
        {(volumeChangePct * 100).toFixed(1)}%
      </span>
    )
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2.5">
      <p className="text-xs text-slate-500">两市成交额（亿）</p>
      <p className="mt-1 text-lg font-semibold text-slate-800">
        {totalVolume.toLocaleString('zh-CN', { maximumFractionDigits: 0 })}
        {changeNode}
      </p>
    </div>
  )
}

function Ma20StatusBadge({ status }: { status: string | null }) {
  if (status === null) {
    return <span className="text-slate-400">—</span>
  }
  if (status === 'above') {
    return <span className="text-rose-500">站上 MA20</span>
  }
  if (status === 'below') {
    return <span className="text-emerald-500">跌破 MA20</span>
  }
  return <span className="text-slate-500">{status}</span>
}

export function MarketOverview({ snapshot, loading, error }: MarketOverviewProps) {
  if (loading) {
    return (
      <div
        className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-500"
        role="status"
      >
        加载大盘快照…
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
  if (!snapshot) {
    return (
      <div
        className="rounded-xl border border-dashed border-slate-200 bg-white p-4 text-center text-sm text-slate-400"
        role="status"
      >
        暂无数据
      </div>
    )
  }

  return (
    <section
      className="rounded-xl border border-slate-200 bg-white p-4"
      aria-label="大盘快照"
    >
      <header className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-700">
          大盘快照 · {snapshot.trade_date}
        </h3>
        <span className="text-xs text-slate-500">
          连续下跌 {snapshot.consecutive_down_days} 日 ·{' '}
          <Ma20StatusBadge status={snapshot.ma20_status} />
        </span>
      </header>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <IndexCard label="上证" value={snapshot.sh_index} />
        <IndexCard label="深证" value={snapshot.sz_index} />
        <IndexCard label="创业板" value={snapshot.cyb_index} />
        <VolumeCard
          totalVolume={snapshot.total_volume}
          volumeChangePct={snapshot.volume_change_pct}
        />
      </div>
    </section>
  )
}
