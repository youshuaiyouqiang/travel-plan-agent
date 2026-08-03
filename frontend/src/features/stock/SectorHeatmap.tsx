/**
 * 板块轮动热力图（多日）。
 *
 * 设计要点：
 * - 横轴：交易日（多日，最新在右）
 * - 纵轴：板块名（每日涨幅前 5 + 跌幅前 3 去重合集）
 * - 颜色：红涨绿跌，深浅表示涨跌幅绝对值
 * - 空数据 → "暂无数据" 占位
 * - 容器 aria-label + 键盘可达
 */
import { useMemo } from 'react'
import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'
import type { SectorPerformance } from './types'

/** 每日取涨幅前 N 和跌幅前 N。 */
const TOP_GAINERS = 5
const TOP_LOSERS = 3

export interface SectorHeatmapProps {
  /** 多日板块数据（来自 /charts/sector）。 */
  series: SectorPerformance[]
  /** 截止日期（标题展示）。 */
  endDate: string
  /** 窗口天数。 */
  days: number
  loading?: boolean
  error?: string | null
}

/** YYYYMMDD → MM-DD 友好显示。 */
function fmtDateShort(s: string): string {
  if (s.length !== 8) return s
  return `${s.slice(4, 6)}-${s.slice(6, 8)}`
}

/** 按日期分组。 */
function groupByDate(
  series: SectorPerformance[],
): Map<string, SectorPerformance[]> {
  const map = new Map<string, SectorPerformance[]>()
  for (const s of series) {
    const list = map.get(s.trade_date)
    if (list) {
      list.push(s)
    } else {
      map.set(s.trade_date, [s])
    }
  }
  return map
}

export function SectorHeatmap({
  series,
  endDate,
  days,
  loading,
  error,
}: SectorHeatmapProps) {
  const option = useMemo<EChartsOption | undefined>(() => {
    if (series.length === 0) return undefined

    // 按日期分组
    const byDate = groupByDate(series)
    // 日期升序（旧→新，热力图左→右）
    const dates = [...byDate.keys()].sort()

    // 每日取涨幅前 5 + 跌幅前 3，收集所有出现的板块名
    const sectorSet = new Set<string>()
    for (const [, items] of byDate) {
      const sorted = [...items].sort((a, b) => {
        const av = a.pct_chg ?? -999
        const bv = b.pct_chg ?? -999
        return bv - av
      })
      const gainers = sorted.slice(0, TOP_GAINERS)
      const losers = sorted.slice(-TOP_LOSERS).reverse()
      for (const s of [...gainers, ...losers]) {
        sectorSet.add(s.sector_name)
      }
    }

    // 板块名列表（按出现频率排序，高频在上）
    const sectorCounts = new Map<string, number>()
    for (const name of sectorSet) {
      sectorCounts.set(name, 0)
    }
    for (const [, items] of byDate) {
      const sorted = [...items].sort((a, b) => {
        const av = a.pct_chg ?? -999
        const bv = b.pct_chg ?? -999
        return bv - av
      })
      const gainers = sorted.slice(0, TOP_GAINERS)
      const losers = sorted.slice(-TOP_LOSERS).reverse()
      for (const s of [...gainers, ...losers]) {
        if (sectorCounts.has(s.sector_name)) {
          sectorCounts.set(s.sector_name, (sectorCounts.get(s.sector_name) ?? 0) + 1)
        }
      }
    }
    const sectors = [...sectorCounts.entries()]
      .sort((a, b) => b[1] - a[1])
      .map((e) => e[0])

    // 构建热力图数据：[xIndex, yIndex, value]
    const heatData: Array<[number, number, number]> = []
    for (let xi = 0; xi < dates.length; xi++) {
      const items = byDate.get(dates[xi]) ?? []
      const byName = new Map(items.map((s) => [s.sector_name, s]))
      for (let yi = 0; yi < sectors.length; yi++) {
        const s = byName.get(sectors[yi])
        heatData.push([xi, yi, s?.pct_chg ?? 0])
      }
    }

    // 颜色范围：以最大绝对值为对称轴
    const maxAbs = Math.max(
      1,
      ...heatData.map((d) => Math.abs(d[2])),
    )

    return {
      tooltip: {
        trigger: 'item',
        formatter: (params: unknown) => {
          const p = params as {
            value: [number, number, number]
            name: string
          }
          const [xi, yi, val] = p.value
          const dt = dates[xi] ?? ''
          const sec = sectors[yi] ?? ''
          return `${fmtDateShort(dt)} ${sec}<br/>涨跌幅：${val.toFixed(2)}%`
        },
      },
      grid: { left: 100, right: 30, top: 10, bottom: 60 },
      xAxis: {
        type: 'category',
        data: dates.map(fmtDateShort),
        splitArea: { show: true },
        axisLabel: { rotate: 45, fontSize: 11 },
      },
      yAxis: {
        type: 'category',
        data: sectors,
        splitArea: { show: true },
        axisLabel: { fontSize: 11 },
        inverse: true,
      },
      series: [
        {
          type: 'heatmap',
          data: heatData,
          label: {
            show: true,
            fontSize: 9,
            formatter: (params: unknown) => {
              const p = params as { value: [number, number, number] }
              const val = p.value[2]
              if (val === 0) return ''
              return `${val.toFixed(1)}`
            },
          },
          emphasis: {
            itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.3)' },
          },
        },
      ],
      visualMap: {
        type: 'continuous',
        orient: 'horizontal',
        left: 'center',
        bottom: 0,
        min: -maxAbs,
        max: maxAbs,
        inRange: { color: ['#10b981', '#f0fdf4', '#ffffff', '#fef2f2', '#ef4444'] },
        text: ['涨', '跌'],
        textStyle: { fontSize: 11 },
      },
    }
  }, [series])

  return (
    <section
      className="rounded-xl border border-slate-200 bg-white p-4"
      aria-label="板块轮动热力图"
    >
      <header className="mb-3">
        <h3 className="text-sm font-semibold text-slate-700">
          板块轮动热力图 · 近 {days} 日（截至 {endDate}）
        </h3>
        <p className="mt-0.5 text-xs text-slate-500">
          每日涨幅前 {TOP_GAINERS} + 跌幅前 {TOP_LOSERS} 板块
        </p>
      </header>
      {error ? (
        <div
          className="flex h-80 items-center justify-center rounded-lg border border-rose-200 bg-rose-50 px-4 text-center text-sm text-rose-700"
          role="alert"
        >
          {error}
        </div>
      ) : loading ? (
        <div
          className="flex h-80 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-sm text-slate-500"
          role="status"
        >
          加载板块轮动…
        </div>
      ) : series.length === 0 || !option ? (
        <div
          className="flex h-80 flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-slate-200 text-sm text-slate-400"
          role="status"
        >
          <div>暂无多日板块数据</div>
          <div className="text-xs">请先抓取最近 {days} 个交易日的板块数据</div>
        </div>
      ) : (
        <div
          aria-label="板块轮动热力图"
          role="img"
          className="h-80 w-full"
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
