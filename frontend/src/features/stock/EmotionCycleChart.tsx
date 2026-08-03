/**
 * 情绪周期折线图组件（Task 5）。
 *
 * 设计要点（开发文档 §2 / §8.1）：
 * - 三条折线：全局情绪得分（粗，按阶段分段着色）/ 打板风格（橙细）/ 趋势风格（青细）
 * - 全局线分段着色：visualMap piecewise 按每日 emotion_phase 编码着色
 *   下跌用绿/蓝、上涨用红、高潮用紫（与 A 股红涨绿跌一致）
 * - connectNulls: true——任一风格某日得分为 null 时连线不断开（None 点跳过）
 * - smooth: false——保留真实转折点毛刺；symbol: 'none'——只留线条
 * - 底部时间轴滑块（与 SectorHeatmap 一致）：数据 > 可见天数时显示
 * - 右侧标注当前阶段 + 得分；顶部标题显示可见日期范围
 * - 空数据 / loading / error 状态兜底
 * - 老行 emotion_phase 为 null 时编码 -1，visualMap 不匹配任何 piece（该段不着色）
 *
 * 反包风格不单独画线，融入全局情绪周期（等权参与合成）。
 */
import { useEffect, useMemo, useState } from 'react'
import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'
import type { EmotionIndicators } from './types'

/** 阶段 → 数字编码（供 visualMap piecewise 分段着色）。 */
const PHASE_CODE: Record<string, number> = {
  冰点: 0,
  强分歧: 1,
  弱分歧: 2,
  弱修复: 3,
  强修复: 4,
  高潮: 5,
}

/** 全局线段配色：下跌绿/蓝、上涨红、高潮紫（与 A 股红涨绿跌一致）。 */
const PHASE_COLOR: Record<string, string> = {
  冰点: '#1e3a8a', // 深蓝：最深跌
  强分歧: '#15803d', // 深绿：急跌
  弱分歧: '#86efac', // 浅绿：缓跌
  弱修复: '#f87171', // 浅红：缓涨
  强修复: '#dc2626', // 深红：急涨
  高潮: '#9333ea', // 紫：过热峰
}

/** 阶段名称列表（用于图例 + Y 轴参考线）。 */
const PHASE_NAMES = ['冰点', '强分歧', '弱分歧', '弱修复', '强修复', '高潮'] as const

/** 打板参考线色（橙）。 */
const BOARD_COLOR = '#f97316'
/** 趋势参考线色（青）。 */
const TREND_COLOR = '#0891b2'

export interface EmotionCycleChartProps {
  /** 多日情绪指标（来自 /charts/emotion，建议传 60 天供滑块浏览）。 */
  series: EmotionIndicators[]
  /** 截止日期（初始窗口右端）。 */
  endDate: string
  /** 可见窗口天数（图表同时展示的天数）。 */
  days: number
  /** 加载中 → 渲染骨架态（与空数据区分）。 */
  loading?: boolean
  /** 错误信息 → 渲染错误占位。 */
  error?: string | null
}

/** YYYYMMDD → MM-DD。 */
function fmtDateShort(s: string): string {
  if (s.length !== 8) return s
  return `${s.slice(4, 6)}-${s.slice(6, 8)}`
}

/** 取阶段编码（null/未知阶段 → -1，visualMap 不匹配 piece，该段不着色）。 */
function phaseCode(phase: string | null | undefined): number {
  if (phase == null) return -1
  return PHASE_CODE[phase] ?? -1
}

export function EmotionCycleChart({
  series,
  endDate,
  days,
  loading,
  error,
}: EmotionCycleChartProps) {
  // 按交易日升序排序（旧 → 新，左 → 右）
  const allSorted = useMemo(
    () => [...series].sort((a, b) => a.trade_date.localeCompare(b.trade_date)),
    [series],
  )

  const totalDays = allSorted.length
  const visibleDays = Math.min(days, totalDays)
  const maxWindowStart = Math.max(0, totalDays - visibleDays)

  // 窗口位置（默认：最新 = maxWindowStart）
  const [windowStartIdx, setWindowStartIdx] = useState(maxWindowStart)
  useEffect(() => {
    setWindowStartIdx(maxWindowStart)
  }, [maxWindowStart])

  const clampedStart = Math.min(windowStartIdx, maxWindowStart)
  const visible = allSorted.slice(clampedStart, clampedStart + visibleDays)
  const visibleStartDate = visible[0]?.trade_date ?? endDate
  const visibleEndDate = visible[visible.length - 1]?.trade_date ?? endDate
  const showSlider = totalDays > visibleDays

  // 最新一日（全量数据末尾，用于"当前阶段"标注）
  const latest = allSorted[allSorted.length - 1]
  const currentPhase = latest?.emotion_phase ?? null
  const currentScore = latest?.emotion_score ?? null

  // ECharts 配置
  const option = useMemo<EChartsOption | undefined>(() => {
    if (visible.length === 0) return undefined

    const tradeDates = visible.map((e) => e.trade_date)

    // 全局线数据：[x索引, 得分, 阶段编码]；得分 null 用 null（connectNulls 跳过）
    const globalData: [number, number | null, number][] = visible.map((e, i) => [
      i,
      e.emotion_score,
      phaseCode(e.emotion_phase),
    ])

    // 打板线数据
    const boardScores: [number, number | null][] = visible.map((e, i) => [
      i,
      e.board_style_score,
    ])

    // 趋势线数据
    const trendScores: [number, number | null][] = visible.map((e, i) => [
      i,
      e.trend_style_score,
    ])

    return {
      tooltip: {
        trigger: 'axis',
        formatter: (params: unknown) => {
          const arr = params as Array<{
            dataIndex: number
            seriesName: string
            value: number | [number, number | null, number] | [number, number | null]
          }>
          if (arr.length === 0) return ''
          const idx = arr[0].dataIndex
          const dt = tradeDates[idx] ?? ''
          const e = visible[idx]
          const phaseStr = e?.emotion_phase ?? '—'
          const lines = [`<b>${fmtDateShort(dt)}</b> · 阶段：${phaseStr}`]
          for (const p of arr) {
            let val: number | null = null
            if (Array.isArray(p.value)) {
              val = p.value[1]
            } else {
              val = p.value
            }
            const valStr = val == null ? '—' : val.toFixed(1)
            lines.push(`${p.seriesName}：${valStr}`)
          }
          return lines.join('<br/>')
        },
      },
      legend: {
        data: ['全局', '打板', '趋势'],
        top: 0,
        textStyle: { fontSize: 11, color: '#475569' },
      },
      grid: { left: 50, right: 50, top: 40, bottom: 50 },
      // 分段着色：仅作用于全局线（seriesIndex 0），按第 3 维（阶段编码）上色
      visualMap: {
        type: 'piecewise',
        dimension: 2,
        seriesIndex: 0,
        show: false,
        pieces: PHASE_NAMES.map((name) => ({
          value: PHASE_CODE[name],
          color: PHASE_COLOR[name],
        })),
      },
      xAxis: {
        type: 'category',
        data: tradeDates.map(fmtDateShort),
        boundaryGap: false,
        axisLine: { lineStyle: { color: '#cbd5e1' } },
        axisLabel: { fontSize: 11, color: '#475569' },
      },
      yAxis: {
        type: 'value',
        min: 0,
        max: 100,
        axisLine: { lineStyle: { color: '#cbd5e1' } },
        axisLabel: { fontSize: 11, color: '#475569' },
        splitLine: { lineStyle: { color: '#f1f5f9' } },
      },
      series: [
        {
          name: '全局',
          type: 'line',
          data: globalData,
          connectNulls: true,
          smooth: false,
          symbol: 'none',
          lineStyle: { width: 3.5 },
          // lineStyle.color 不设，由 visualMap 接管分段着色
        },
        {
          name: '打板',
          type: 'line',
          data: boardScores,
          connectNulls: true,
          smooth: false,
          symbol: 'none',
          lineStyle: { width: 1.5, color: BOARD_COLOR },
        },
        {
          name: '趋势',
          type: 'line',
          data: trendScores,
          connectNulls: true,
          smooth: false,
          symbol: 'none',
          lineStyle: { width: 1.5, color: TREND_COLOR },
        },
      ],
    }
  }, [visible])

  return (
    <section
      className="rounded-xl border border-slate-200 bg-white p-4"
      aria-label="情绪周期折线图"
    >
      <header className="mb-3">
        <h3 className="text-sm font-semibold text-slate-700">
          情绪周期 · {fmtDateShort(visibleStartDate)} ~{' '}
          {fmtDateShort(visibleEndDate)}
          {showSlider && (
            <span className="ml-2 text-xs font-normal text-slate-400">
              （共 {totalDays} 日可浏览）
            </span>
          )}
        </h3>
        <p className="mt-1 text-xs text-slate-500">
          全局线按阶段分段着色（红涨绿跌） · 打板/趋势作对照 · 三种赚钱风格的共生与竞争
        </p>
        {/* 当前阶段 + 得分标注 */}
        {currentPhase && (
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
            <span className="text-slate-400">当前阶段：</span>
            <span
              className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-medium"
              style={{
                borderColor: PHASE_COLOR[currentPhase] ?? '#94a3b8',
                color: PHASE_COLOR[currentPhase] ?? '#475569',
                backgroundColor: `${PHASE_COLOR[currentPhase] ?? '#94a3b8'}1a`,
              }}
            >
              <span
                className="inline-block h-1.5 w-1.5 rounded-full"
                style={{ backgroundColor: PHASE_COLOR[currentPhase] ?? '#94a3b8' }}
                aria-hidden="true"
              />
              {currentPhase}
            </span>
            {currentScore != null && (
              <span className="text-slate-500">
                全局得分：<span className="font-semibold text-slate-700">{currentScore.toFixed(1)}</span>
              </span>
            )}
          </div>
        )}
        {/* 阶段配色图例 */}
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-400">
          {PHASE_NAMES.map((name) => (
            <span key={name} className="inline-flex items-center gap-1">
              <span
                className="inline-block h-1.5 w-4 rounded-full"
                style={{ backgroundColor: PHASE_COLOR[name] }}
                aria-hidden="true"
              />
              {name}
            </span>
          ))}
          <span className="mx-1 text-slate-300">|</span>
          <span className="inline-flex items-center gap-1">
            <span
              className="inline-block h-1.5 w-4 rounded-full"
              style={{ backgroundColor: BOARD_COLOR }}
              aria-hidden="true"
            />
            打板
          </span>
          <span className="inline-flex items-center gap-1">
            <span
              className="inline-block h-1.5 w-4 rounded-full"
              style={{ backgroundColor: TREND_COLOR }}
              aria-hidden="true"
            />
            趋势
          </span>
        </div>
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
          加载情绪周期…
        </div>
      ) : visible.length === 0 || !option ? (
        <div
          className="flex h-64 items-center justify-center rounded-lg border border-dashed border-slate-200 text-sm text-slate-400"
          role="status"
        >
          暂无情绪周期数据
        </div>
      ) : (
        <>
          <div
            aria-label="情绪周期折线图"
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
          {/* 底部时间轴滑块 */}
          {showSlider && (
            <div className="mt-3 flex items-center gap-3 px-1">
              <span className="whitespace-nowrap text-xs text-slate-400">
                {fmtDateShort(allSorted[0].trade_date)}
              </span>
              <input
                type="range"
                min={0}
                max={maxWindowStart}
                value={clampedStart}
                onChange={(e) => setWindowStartIdx(Number(e.target.value))}
                className="h-1.5 flex-1 cursor-pointer appearance-none rounded-full bg-slate-200 accent-indigo-500"
                aria-label="情绪周期时间轴"
              />
              <span className="whitespace-nowrap text-xs text-slate-400">
                {fmtDateShort(allSorted[totalDays - 1].trade_date)}
              </span>
            </div>
          )}
        </>
      )}
    </section>
  )
}
