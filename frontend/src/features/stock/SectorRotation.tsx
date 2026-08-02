/**
 * 板块轮动组件（Task 7）。
 *
 * 设计要点：
 * - 横向条形图：按 pct_chg 排序，红涨/绿跌
 * - 空数据 → "暂无数据" 占位；如果 tradeDate 是周六/周日（A股非交易日），
 *   改为更友好的"非交易日"提示，避免误导用户以为系统挂了
 * - 容器 aria-label + 键盘可达
 */
import { useMemo } from 'react'
import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'
import type { SectorPerformance } from './types'

/** 判断 YYYYMMDD 是否为 A 股交易日（仅判周末，不考虑节假日——节假日没数据可回退）。 */
function is_weekend_yyyymmdd(s: string): boolean {
  if (s.length !== 8 || !/^\d{8}$/.test(s)) return false
  const y = Number(s.slice(0, 4))
  const m = Number(s.slice(4, 6)) - 1
  const d = Number(s.slice(6, 8))
  const dt = new Date(y, m, d)
  const dow = dt.getDay()
  return dow === 0 || dow === 6
}

export interface SectorRotationProps {
  items: SectorPerformance[]
  /** 标题/上下文日期。 */
  tradeDate: string
  loading?: boolean
  error?: string | null
}

export function SectorRotation({
  items,
  tradeDate,
  loading,
  error,
}: SectorRotationProps) {
  const option = useMemo<EChartsOption | undefined>(() => {
    if (items.length === 0) return undefined
    // 按 pct_chg 降序排序
    const sorted = [...items].sort((a, b) => {
      const av = a.pct_chg ?? 0
      const bv = b.pct_chg ?? 0
      return bv - av
    })
    // 限制显示 top/bottom 各 10
    const top = sorted.slice(0, 10)
    const bottom = sorted.slice(-10).reverse()
    const merged = [...top, ...bottom].filter(
      (s, i, arr) => arr.findIndex((x) => x.sector_code === s.sector_code) === i,
    )
    return {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
      },
      grid: { left: 100, right: 30, top: 10, bottom: 30 },
      xAxis: {
        type: 'value',
        name: '涨跌幅',
        axisLabel: {
          formatter: (v: number) => `${(v * 100).toFixed(1)}%`,
        },
      },
      yAxis: {
        type: 'category',
        data: merged.map((s) => s.sector_name),
        inverse: true,
      },
      series: [
        {
          type: 'bar',
          data: merged.map((s) => ({
            value: s.pct_chg == null ? 0 : Number((s.pct_chg * 100).toFixed(2)),
            itemStyle: {
              color:
                s.pct_chg == null
                  ? '#94a3b8'
                  : s.pct_chg > 0
                    ? '#ef4444'
                    : s.pct_chg < 0
                      ? '#10b981'
                      : '#94a3b8',
            },
          })),
        },
      ],
    }
  }, [items])

  return (
    <section
      className="rounded-xl border border-slate-200 bg-white p-4"
      aria-label="板块轮动"
    >
      <header className="mb-3">
        <h3 className="text-sm font-semibold text-slate-700">
          板块轮动 · {tradeDate}
        </h3>
      </header>
      {error ? (
        <div
          className="flex h-64 items-center justify-center rounded-lg border border-rose-200 bg-rose-50 px-4 text-center text-sm text-rose-700"
          role="alert"
        >
          {error}
        </div>
      ) : loading ? (
        <div
          className="flex h-64 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-sm text-slate-500"
          role="status"
        >
          加载板块表现…
        </div>
      ) : items.length === 0 || !option ? (
        <div
          className="flex h-64 flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-slate-200 text-sm text-slate-400"
          role="status"
        >
          {is_weekend_yyyymmdd(tradeDate) ? (
            <>
              <div>{tradeDate} 为周六/周日，A 股不开市</div>
              <div className="text-xs">暂无板块行情</div>
            </>
          ) : (
            <div>暂无数据</div>
          )}
        </div>
      ) : (
        <div
          aria-label="板块轮动图"
          role="img"
          className="h-64 w-full"
        >
          <ReactECharts
            option={option}
            style={{ height: '100%', width: '100%' }}
            notMerge
            lazyUpdate
            opts={{ renderer: 'canvas' }}
          />
        </div>
      )}
    </section>
  )
}
