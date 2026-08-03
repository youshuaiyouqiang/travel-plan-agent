/**
 * 板块轮动追踪热力图（多日 + 时间轴）。
 *
 * 核心设计——板块生命周期追踪（含观察期）：
 * - 进入条件：当日涨幅排名前 2 → 开始追踪
 * - 持续条件：涨幅排名仍在前 5 → 继续追踪
 * - 触发观察：涨幅排名跌出前 5 或强度倒数后 3 → 进入观察期（不立即退出）
 * - 观察期：继续追踪 GRACE_DAYS 天；若期间重回前 5 → 恢复正常追踪
 * - 退出条件：观察期满仍未重回前 5 → 停止追踪
 * - 重新进入：退出后再次进入前 2 → 恢复追踪（中间留空断档）
 *
 * 视觉（一眼看轮动）：
 * - 横轴：交易日（旧→新，左→右），可通过底部滑块拖动浏览历史
 * - 纵轴：板块名（按首次进入日期排序，形成阶梯状轮动轨迹）
 * - 正常追踪：红涨绿跌色块（无文字标签，悬停看详情）
 * - 观察期：半透明 + 琥珀色虚线边框
 * - 进入日：橙色实线边框
 * - 退出日：灰色实线边框 + 半透明
 * - 当前活跃：蓝色实线边框
 * - 未追踪：透明，一眼看出板块强势期
 */
import { useEffect, useMemo, useState } from 'react'
import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'
import type { SectorPerformance } from './types'

/** 进入追踪的排名门槛。 */
const ENTER_RANK = 2
/** 持续追踪的排名门槛（跌出即触发观察期）。 */
const STAY_RANK = 5
/** 强度倒数后 N 名触发观察期。 */
const EXIT_BOTTOM_RANK = 3
/** 观察期天数：触发后继续追踪 N 天，仍未重回前 5 则退出。 */
const GRACE_DAYS = 3

export interface SectorHeatmapProps {
  /** 多日板块数据（来自 /charts/sector，建议传 60 天供滑块浏览）。 */
  series: SectorPerformance[]
  /** 截止日期（初始窗口右端）。 */
  endDate: string
  /** 可见窗口天数（热力图同时展示的天数）。 */
  days: number
  loading?: boolean
  error?: string | null
}

/** YYYYMMDD → MM-DD。 */
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

/** 单个追踪周期。 */
interface TrackingPeriod {
  enter: string
  exit: string | null
  /** 观察期起始日期（null = 未触发观察）。 */
  graceStart: string | null
}

/** 被追踪的板块。 */
interface TrackedSector {
  name: string
  periods: TrackingPeriod[]
}

/** 某日某板块的追踪状态。 */
interface TrackStatus {
  tracked: boolean
  isEnter: boolean
  isExit: boolean
  isGrace: boolean
}

/** 检查板块在某日是否被追踪。 */
function checkTracked(
  sector: TrackedSector,
  date: string,
): TrackStatus {
  for (const p of sector.periods) {
    if (date >= p.enter && (p.exit === null || date <= p.exit)) {
      const isEnter = date === p.enter
      const isExit = p.exit !== null && date === p.exit
      const isGrace =
        !isEnter && !isExit && p.graceStart !== null && date >= p.graceStart
      return { tracked: true, isEnter, isExit, isGrace }
    }
  }
  return { tracked: false, isEnter: false, isExit: false, isGrace: false }
}

/** 热力图数据点（携带进入/退出/活跃/观察标记）。 */
interface HeatPoint {
  value: [number, number, number]
  isEnter: boolean
  isExit: boolean
  isActive: boolean
  isGrace: boolean
  /** 观察期第几天（1-based，null = 非观察期）。 */
  graceDay: number | null
}

/** 追踪计算结果。 */
interface TrackResult {
  trackedList: TrackedSector[]
  dates: string[]
  dailyData: Map<string, Map<string, { rank: number; pct_chg: number }>>
}

/** 活跃板块信息（含观察期标记）。 */
interface ActiveSectorInfo {
  name: string
  inGrace: boolean
}

/**
 * 计算板块追踪轨迹（含观察期逻辑）。
 *
 * 算法：
 * 1. 每日按 pct_chg 降序排名
 * 2. 从旧到新扫描：
 *    - 已追踪板块排名 > STAY_RANK 或在倒数后 EXIT_BOTTOM_RANK → 触发观察期
 *    - 观察期内重回前 5 → 清除观察期，恢复正常追踪
 *    - 观察期满 GRACE_DAYS 天仍未重回前 5 → 退出
 *    - 未追踪板块排名 ≤ ENTER_RANK → 进入
 * 3. 支持退出后重新进入（新开一个 period）
 */
function computeTrackedSectors(series: SectorPerformance[]): TrackResult {
  const byDate = groupByDate(series)
  const dates = [...byDate.keys()].sort()

  // 每日排名
  const dailyData = new Map<
    string,
    Map<string, { rank: number; pct_chg: number }>
  >()
  for (const date of dates) {
    const items = byDate.get(date) ?? []
    const sorted = [...items].sort(
      (a, b) => (b.pct_chg ?? -999) - (a.pct_chg ?? -999),
    )
    const rankMap = new Map<string, { rank: number; pct_chg: number }>()
    sorted.forEach((s, i) =>
      rankMap.set(s.sector_name, {
        rank: i + 1,
        pct_chg: s.pct_chg ?? 0,
      }),
    )
    dailyData.set(date, rankMap)
  }

  // 追踪扫描
  const tracked = new Map<string, TrackedSector>()

  for (let dateIdx = 0; dateIdx < dates.length; dateIdx++) {
    const date = dates[dateIdx]
    const rankMap = dailyData.get(date)!
    const totalSectors = rankMap.size
    const bottomThreshold = totalSectors - EXIT_BOTTOM_RANK + 1

    // 先检查观察期 / 退出
    for (const [, t] of tracked) {
      const current = t.periods[t.periods.length - 1]
      if (current && current.exit === null) {
        const info = rankMap.get(t.name)
        const isOutOfTop5 = !info || info.rank > STAY_RANK
        const isBottom3 =
          info && totalSectors > STAY_RANK && info.rank >= bottomThreshold

        if (isOutOfTop5 || isBottom3) {
          // 触发观察期
          if (current.graceStart === null) {
            current.graceStart = date
          }
          // 检查观察期是否已满
          const graceStartIdx = dates.indexOf(current.graceStart)
          const graceDays = dateIdx - graceStartIdx
          if (graceDays >= GRACE_DAYS) {
            current.exit = date
          }
        } else {
          // 重回前 5 → 清除观察期
          current.graceStart = null
        }
      }
    }

    // 再检查进入
    for (const [name, info] of rankMap) {
      if (info.rank > ENTER_RANK) continue
      const t = tracked.get(name)
      const current = t?.periods[t.periods.length - 1]
      if (current && current.exit === null) continue // 已在追踪
      // 开始新周期
      if (t) {
        t.periods.push({ enter: date, exit: null, graceStart: null })
      } else {
        tracked.set(name, {
          name,
          periods: [{ enter: date, exit: null, graceStart: null }],
        })
      }
    }
  }

  // 按首次进入日期排序
  const trackedList = [...tracked.values()].sort((a, b) =>
    a.periods[0].enter.localeCompare(b.periods[0].enter),
  )

  return { trackedList, dates, dailyData }
}

/** 判断板块在可见窗口内是否活跃（追踪期延伸到窗口右端之后）。 */
function isSectorActiveInWindow(
  sector: TrackedSector,
  visibleEndDate: string,
): boolean {
  return sector.periods.some(
    (p) =>
      p.enter <= visibleEndDate &&
      (p.exit === null || p.exit > visibleEndDate),
  )
}

/** 判断板块在窗口右端是否处于观察期。 */
function isSectorInGraceAtDate(
  sector: TrackedSector,
  date: string,
): boolean {
  for (const p of sector.periods) {
    if (
      p.graceStart !== null &&
      date >= p.graceStart &&
      (p.exit === null || p.exit >= date)
    ) {
      return true
    }
  }
  return false
}

export function SectorHeatmap({
  series,
  endDate,
  days,
  loading,
  error,
}: SectorHeatmapProps) {
  // 全量追踪计算（在全部数据上，不只可见窗口）
  const trackResult = useMemo(
    () => (series.length > 0 ? computeTrackedSectors(series) : null),
    [series],
  )

  const allDates = trackResult?.dates ?? []
  const totalDays = allDates.length
  const visibleDays = Math.min(days, totalDays)
  const maxWindowStart = Math.max(0, totalDays - visibleDays)

  // 窗口位置（默认：最新 = maxWindowStart）
  const [windowStartIdx, setWindowStartIdx] = useState(maxWindowStart)
  useEffect(() => {
    setWindowStartIdx(maxWindowStart)
  }, [maxWindowStart])

  const clampedStart = Math.min(windowStartIdx, maxWindowStart)
  const visibleDates = allDates.slice(
    clampedStart,
    clampedStart + visibleDays,
  )
  const visibleStartDate = visibleDates[0] ?? endDate
  const visibleEndDate = visibleDates[visibleDates.length - 1] ?? endDate
  const showSlider = totalDays > visibleDays

  // 活跃板块（相对于可见窗口右端）
  const activeSectors = useMemo<ActiveSectorInfo[]>(() => {
    if (!trackResult) return []
    return trackResult.trackedList
      .filter((t) => isSectorActiveInWindow(t, visibleEndDate))
      .map((t) => ({
        name: t.name,
        inGrace: isSectorInGraceAtDate(t, visibleEndDate),
      }))
  }, [trackResult, visibleEndDate])

  // 图表配置（仅渲染可见窗口）
  const option = useMemo<EChartsOption | undefined>(() => {
    if (!trackResult || trackResult.trackedList.length === 0) return undefined
    if (visibleDates.length === 0) return undefined

    const { trackedList, dates, dailyData } = trackResult

    // 可见日期 → x 索引映射
    const dateToX = new Map<string, number>()
    visibleDates.forEach((d, i) => dateToX.set(d, i))

    // 构建热力图数据（仅可见日期）
    const heatData: HeatPoint[] = []
    for (let yi = 0; yi < trackedList.length; yi++) {
      const sector = trackedList[yi]
      const activeInWindow = isSectorActiveInWindow(sector, visibleEndDate)

      // 找该板块在可见窗口内最后被追踪的日期
      let lastTrackedVisibleDate: string | null = null
      for (const d of visibleDates) {
        if (checkTracked(sector, d).tracked) {
          lastTrackedVisibleDate = d
        }
      }

      for (const d of visibleDates) {
        const xi = dateToX.get(d)!
        const status = checkTracked(sector, d)
        if (!status.tracked) continue
        const info = dailyData.get(d)?.get(sector.name)
        if (!info) continue

        const isActiveCell =
          activeInWindow && d === lastTrackedVisibleDate && !status.isExit

        // 计算观察期第几天
        let graceDay: number | null = null
        if (status.isGrace) {
          for (const p of sector.periods) {
            if (
              p.graceStart !== null &&
              d >= p.graceStart &&
              (p.exit === null || d <= p.exit)
            ) {
              graceDay = dates.indexOf(d) - dates.indexOf(p.graceStart)
              break
            }
          }
        }

        heatData.push({
          value: [xi, yi, info.pct_chg],
          isEnter: status.isEnter,
          isExit: status.isExit,
          isActive: isActiveCell,
          isGrace: status.isGrace,
          graceDay,
        })
      }
    }

    if (heatData.length === 0) return undefined

    const maxAbs = Math.max(1, ...heatData.map((d) => Math.abs(d.value[2])))
    const sectorNames = trackedList.map((t) => t.name)

    return {
      tooltip: {
        trigger: 'item',
        formatter: (params: unknown) => {
          const p = params as {
            value: [number, number, number]
            data: HeatPoint
          }
          const [xi, yi, val] = p.value
          const dt = visibleDates[xi] ?? ''
          const sec = sectorNames[yi] ?? ''
          const info = dailyData.get(dt)?.get(sec)
          const rankStr = info ? `#${info.rank}` : '-'
          let statusStr: string
          if (p.data.isEnter) {
            statusStr = '⬆ 进入'
          } else if (p.data.isExit) {
            statusStr = '⬇ 退出'
          } else if (p.data.isGrace) {
            const gd = p.data.graceDay ?? 0
            statusStr = `👁 观察中 (第${gd}天/共${GRACE_DAYS}天)`
          } else if (p.data.isActive) {
            statusStr = '● 活跃'
          } else {
            statusStr = '持续'
          }
          const chgStr =
            val >= 0 ? `+${val.toFixed(2)}%` : `${val.toFixed(2)}%`
          const chgColor = val >= 0 ? '#dc2626' : '#16a34a'
          return (
            `<b>${sec}</b> · ${fmtDateShort(dt)}<br/>` +
            `涨跌幅：<span style="color:${chgColor};font-weight:600">${chgStr}</span><br/>` +
            `排名：${rankStr}  状态：${statusStr}`
          )
        },
      },
      grid: { left: 100, right: 16, top: 8, bottom: 60 },
      xAxis: {
        type: 'category',
        data: visibleDates.map(fmtDateShort),
        splitArea: { show: true },
        axisLine: { lineStyle: { color: '#cbd5e1' } },
        axisLabel: { fontSize: 11, color: '#475569' },
      },
      yAxis: {
        type: 'category',
        data: sectorNames,
        splitArea: { show: true },
        axisLine: { lineStyle: { color: '#cbd5e1' } },
        axisLabel: { fontSize: 11, color: '#334155' },
        inverse: true,
      },
      series: [
        {
          type: 'heatmap',
          data: heatData.map((d) => {
            // 优先级：enter > exit > grace > active > normal
            let borderColor: string
            let borderWidth: number
            let borderType: 'solid' | 'dashed' = 'solid'
            let opacity = 1

            if (d.isEnter) {
              borderColor = '#f59e0b'
              borderWidth = 2.5
            } else if (d.isExit) {
              borderColor = '#64748b'
              borderWidth = 2.5
              opacity = 0.55
            } else if (d.isGrace) {
              borderColor = '#f59e0b'
              borderWidth = 2
              borderType = 'dashed'
              opacity = 0.5
            } else if (d.isActive) {
              borderColor = '#3b82f6'
              borderWidth = 2.5
            } else {
              borderColor = '#fff'
              borderWidth = 1
            }

            return {
              value: d.value,
              isEnter: d.isEnter,
              isExit: d.isExit,
              isActive: d.isActive,
              isGrace: d.isGrace,
              graceDay: d.graceDay,
              itemStyle: {
                borderRadius: 3,
                borderColor,
                borderWidth,
                borderType,
                opacity,
              },
            }
          }),
          label: { show: false },
          emphasis: {
            itemStyle: {
              shadowBlur: 10,
              shadowColor: 'rgba(0,0,0,0.25)',
              borderWidth: 3,
            },
          },
        },
      ],
      visualMap: {
        type: 'continuous',
        orient: 'horizontal',
        left: 'center',
        bottom: 5,
        min: -maxAbs,
        max: maxAbs,
        inRange: {
          color: [
            '#15803d', '#86efac', '#f0fdf4', '#f8fafc',
            '#fef2f2', '#fca5a5', '#b91c1c',
          ],
        },
        text: ['涨', '跌'],
        textStyle: { fontSize: 11, color: '#475569' },
        itemHeight: 100,
      },
    }
  }, [trackResult, visibleDates, visibleEndDate])

  // 动态高度：每个板块 30px + 基础高度
  const chartHeight = trackResult
    ? Math.max(200, trackResult.trackedList.length * 30 + 140)
    : 200

  return (
    <section
      className="rounded-xl border border-slate-200 bg-white p-4"
      aria-label="板块轮动追踪热力图"
    >
      <header className="mb-3">
        <h3 className="text-sm font-semibold text-slate-700">
          板块轮动追踪 · {fmtDateShort(visibleStartDate)} ~{' '}
          {fmtDateShort(visibleEndDate)}
          {showSlider && (
            <span className="ml-2 text-xs font-normal text-slate-400">
              （共 {totalDays} 日可浏览）
            </span>
          )}
        </h3>
        <p className="mt-1 text-xs text-slate-500">
          涨幅前 {ENTER_RANK} 进入 · 跌出前 {STAY_RANK} 或倒数后{' '}
          {EXIT_BOTTOM_RANK} 触发 {GRACE_DAYS} 天观察期 · 观察期满未回前{' '}
          {STAY_RANK} 退出
        </p>
        {/* 当前活跃板块徽章 */}
        {activeSectors.length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <span className="text-xs text-slate-400">当前追踪：</span>
            {activeSectors.map(({ name, inGrace }) => (
              <span
                key={name}
                className={
                  'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ' +
                  (inGrace
                    ? 'border-amber-300 bg-amber-50 text-amber-700'
                    : 'border-blue-200 bg-blue-50 text-blue-700')
                }
              >
                <span
                  className={
                    'inline-block h-1.5 w-1.5 rounded-full ' +
                    (inGrace ? 'bg-amber-500' : 'bg-blue-500')
                  }
                  aria-hidden="true"
                />
                {name}
                {inGrace && (
                  <span className="text-amber-500">观察</span>
                )}
              </span>
            ))}
          </div>
        )}
        {/* 图例 */}
        <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-slate-400">
          <span className="inline-flex items-center gap-1">
            <span className="inline-block h-3 w-3 rounded-sm border-2 border-amber-500" />
            进入日
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="inline-block h-3 w-3 rounded-sm border-2 border-slate-500 opacity-60" />
            退出日
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="inline-block h-3 w-3 rounded-sm border-2 border-dashed border-amber-500 opacity-50" />
            观察期
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="inline-block h-3 w-3 rounded-sm border-2 border-blue-500" />
            当前活跃
          </span>
        </div>
      </header>
      {error ? (
        <div
          className="flex items-center justify-center rounded-lg border border-rose-200 bg-rose-50 px-4 py-20 text-center text-sm text-rose-700"
          role="alert"
        >
          {error}
        </div>
      ) : loading ? (
        <div
          className="flex items-center justify-center rounded-lg border border-slate-200 bg-slate-50 py-20 text-sm text-slate-500"
          role="status"
        >
          加载板块轮动…
        </div>
      ) : series.length === 0 ? (
        <div
          className="flex flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-slate-200 py-20 text-sm text-slate-400"
          role="status"
        >
          <div>暂无多日板块数据</div>
          <div className="text-xs">
            追踪规则：涨幅前 {ENTER_RANK} 进入，跌出前 {STAY_RANK} 触发{' '}
            {GRACE_DAYS} 天观察期
          </div>
        </div>
      ) : !trackResult ||
        trackResult.trackedList.length === 0 ||
        !option ? (
        <div
          className="flex flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-slate-200 py-20 text-sm text-slate-400"
          role="status"
        >
          <div>近期无板块进入涨幅前 {ENTER_RANK}</div>
          <div className="text-xs">尝试增大窗口天数或拖动时间轴换一个时间段</div>
        </div>
      ) : (
        <>
          <div
            aria-label="板块轮动追踪热力图"
            role="img"
            style={{ height: `${chartHeight}px` }}
            className="w-full"
          >
            <ReactECharts
              option={option}
              style={{ height: '100%', width: '100%' }}
              notMerge
              lazyUpdate
              opts={{ renderer: 'canvas' }}
            />
          </div>
          {/* 底部时间轴滑块 */}
          {showSlider && (
            <div className="mt-3 flex items-center gap-3 px-1">
              <span className="whitespace-nowrap text-xs text-slate-400">
                {fmtDateShort(allDates[0])}
              </span>
              <input
                type="range"
                min={0}
                max={maxWindowStart}
                value={clampedStart}
                onChange={(e) =>
                  setWindowStartIdx(Number(e.target.value))
                }
                className="h-1.5 flex-1 cursor-pointer appearance-none rounded-full bg-slate-200 accent-indigo-500"
                aria-label="板块轮动时间轴"
              />
              <span className="whitespace-nowrap text-xs text-slate-400">
                {fmtDateShort(allDates[totalDays - 1])}
              </span>
            </div>
          )}
        </>
      )}
    </section>
  )
}
