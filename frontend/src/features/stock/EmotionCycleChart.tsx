/**
 * 情绪周期折线图组件（Task 5）。
 *
 * 设计要点（开发文档 §2 / §8.1）：
 * - 三条折线均按各自阶段分段着色：
 *   全局（粗）/ 打板（中细）/ 趋势（细）
 * - 每条线的阶段独立判定——全局用后端存储的 emotion_phase，
 *   打板/趋势在前端用 computePhase（与后端 compute_raw_phase 同算法）
 *   从各自 style_score + 3 日前得分算出，visualMap piecewise 分段着色
 * - 配色：冰点深蓝 / 强分歧深绿 / 弱分歧浅绿 / 弱修复浅红 / 强修复深红 / 高潮紫
 *   下跌用绿/蓝、上涨用红、高潮用紫（与 A 股红涨绿跌一致）
 * - connectNulls: true——任一风格某日得分为 null 时连线不断开（None 点跳过）
 * - smooth: false——保留真实转折点毛刺；symbol: 'none'——只留线条
 * - 底部时间轴滑块（与 SectorHeatmap 一致）：数据 > 可见天数时显示
 * - 右侧标注当前阶段 + 得分（三条线各自）；顶部标题显示可见日期范围
 * - 空数据 / loading / error 状态兜底
 * - 老行 emotion_phase 为 null 时编码 -1，visualMap 映射灰色（该段不着色）
 *
 * 反包风格不单独画线，融入全局情绪周期（等权参与合成）。
 */
import { useEffect, useMemo, useState } from 'react'
import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'
import type { EmotionIndicators } from './types'

/** 线段配色：下跌绿/蓝、上涨红、高潮紫（与 A 股红涨绿跌一致）。 */
const PHASE_COLOR: Record<string, string> = {
  冰点: '#1e3a8a', // 深蓝：最深跌
  强分歧: '#15803d', // 深绿：急跌
  弱分歧: '#86efac', // 浅绿：缓跌
  弱修复: '#f87171', // 浅红：缓涨
  强修复: '#dc2626', // 深红：急涨
  高潮: '#9333ea', // 紫：过热峰
}

/** 未知阶段（null / 数据不足）的降级色。 */
const FALLBACK_COLOR = '#cbd5e1'

/** 阶段名称列表（用于图例）。 */
const PHASE_NAMES = ['冰点', '强分歧', '弱分歧', '弱修复', '强修复', '高潮'] as const

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

/**
 * 前端阶段判定——与后端 domain.stock.emotion_cycle.compute_raw_phase 同算法。
 *
 * 一阶（得分）判断赚不赚，二阶（动量 = 今日 − 3 日前）判断跟风增减，
 * 组合确定 6 阶段之一。score3dAgo 为 null 时动量视为 0。
 *
 * 用于打板/趋势线的分段着色（全局线直接用后端存储的 emotion_phase）。
 */
function computePhase(score: number, score3dAgo: number | null): string {
  const momentum = score3dAgo != null ? score - score3dAgo : 0

  if (score >= 80) return '高潮'
  if (score >= 60) return momentum > 0 ? '强修复' : '高潮'
  if (score >= 40) {
    if (momentum > 5) return '强修复'
    if (momentum < -5) return '弱分歧'
    return '弱修复'
  }
  if (score >= 20) {
    if (momentum < -5) return '强分歧'
    return '弱修复'
  }
  return momentum > 0 ? '弱修复' : '冰点'
}

/** 三条线各自的阶段信息。 */
interface LinePhases {
  globalPhase: string | null
  boardPhase: string | null
  trendPhase: string | null
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

  // ── 预计算所有数据点的三条线阶段（用全量数组做 3 日前回溯） ──
  const allPhases = useMemo<LinePhases[]>(
    () =>
      allSorted.map((e, i) => {
        const idx3dAgo = i - 3
        const board3dAgo =
          idx3dAgo >= 0 ? allSorted[idx3dAgo].board_style_score : null
        const trend3dAgo =
          idx3dAgo >= 0 ? allSorted[idx3dAgo].trend_style_score : null
        return {
          globalPhase: e.emotion_phase,
          boardPhase:
            e.board_style_score != null
              ? computePhase(e.board_style_score, board3dAgo)
              : null,
          trendPhase:
            e.trend_style_score != null
              ? computePhase(e.trend_style_score, trend3dAgo)
              : null,
        }
      }),
    [allSorted],
  )

  const visiblePhases = useMemo(
    () => allPhases.slice(clampedStart, clampedStart + visibleDays),
    [allPhases, clampedStart, visibleDays],
  )

  // 最新一日（全量数据末尾，用于"当前阶段"标注）
  const latest = allSorted[allSorted.length - 1]
  const latestPhases = allPhases[allPhases.length - 1]

  // ECharts 配置
  const option = useMemo<EChartsOption | undefined>(() => {
    if (visible.length === 0) return undefined

    const tradeDates = visible.map((e) => e.trade_date)

    // 拆分策略（确保颜色生效）：
    // 把每条"风格线"按阶段拆成 6 段 series（每个阶段一段），每段设固定
    // lineStyle.color 即可。相邻段端点重合 → 视觉上是连续折线，但每段
    // 颜色由 visualMap palette 直接控制，不会被 legend 默认配色覆盖。
    //
    // 输入：scores=[v0,v1,...]、phases=[p0,p1,...]
    // 输出：6 个 segment series（每段含连续相同阶段的点）
    function buildSegments(
      baseName: string,
      scores: Array<number | null>,
      phases: Array<string | null>,
      lineWidth: number,
    ) {
      const result: Array<{
        name: string
        type: 'line'
        data: Array<[number, number | null]>
        connectNulls: boolean
        smooth: boolean
        symbol: 'none'
        lineStyle: { width: number; color: string }
        showSymbol: false
        legendHoverLink: false
        z: number
        silent: boolean
        tooltip: { show: boolean }
      }> = []
      let segStart = 0
      let segPhase: string | null = phases[0] ?? null
      for (let i = 1; i <= scores.length; i++) {
        const p = i < scores.length ? phases[i] : null
        if (p !== segPhase) {
          const data: Array<[number, number | null]> = []
          for (let j = segStart; j < i; j++) {
            data.push([j, scores[j]])
          }
          const phaseName = segPhase ?? '—'
          const color = segPhase != null ? PHASE_COLOR[segPhase] : FALLBACK_COLOR
          result.push({
            name: `${baseName}·${phaseName}`,
            type: 'line',
            data,
            connectNulls: false,  // 段内强制连续，跨段不连
            smooth: false,
            symbol: 'none',
            lineStyle: { width: lineWidth, color },
            showSymbol: false,
            legendHoverLink: false,
            z: baseName === '全局' ? 3 : baseName === '打板' ? 2 : 1,
            silent: true,  // 段不响应 hover/tooltip，由主 series 显示
            tooltip: { show: false },
          })
          segStart = i
          segPhase = p
        }
      }
      return result
    }

    const globalScores = visible.map((e) => e.emotion_score)
    const boardScores = visible.map((e) => e.board_style_score)
    const trendScores = visible.map((e) => e.trend_style_score)
    const globalPhases = visiblePhases.map((p) => p?.globalPhase ?? null)
    const boardPhases = visiblePhases.map((p) => p?.boardPhase ?? null)
    const trendPhases = visiblePhases.map((p) => p?.trendPhase ?? null)

    const seriesArr = [
      ...buildSegments('全局', globalScores, globalPhases, 3.5),
      ...buildSegments('打板', boardScores, boardPhases, 2.0),
      ...buildSegments('趋势', trendScores, trendPhases, 1.5),
    ]

    return {
      tooltip: {
        trigger: 'axis',
        formatter: (params: unknown) => {
          const arr = params as Array<{
            dataIndex: number
            seriesName: string
            value: number | [number, number | null]
          }>
          if (arr.length === 0) return ''
          const idx = arr[0].dataIndex
          const dt = tradeDates[idx] ?? ''
          const ph = visiblePhases[idx]
          const globalPhaseStr = ph?.globalPhase ?? '—'
          const lines = [`<b>${fmtDateShort(dt)}</b> · 全局阶段：${globalPhaseStr}`]
          // 段 series（name 含 "·"）被 silent，只显示主 series 风格的信息
          const seen = new Set<string>()
          for (const p of arr) {
            const baseName = p.seriesName.split('·')[0] ?? p.seriesName
            if (seen.has(baseName)) continue
            seen.add(baseName)
            const e = visible[idx]
            let score: number | null = null
            let phaseStr = '—'
            if (baseName === '全局') {
              score = e?.emotion_score ?? null
              phaseStr = ph?.globalPhase ?? '—'
            } else if (baseName === '打板') {
              score = e?.board_style_score ?? null
              phaseStr = ph?.boardPhase ?? '—'
            } else if (baseName === '趋势') {
              score = e?.trend_style_score ?? null
              phaseStr = ph?.trendPhase ?? '—'
            }
            const valStr = score == null ? '—' : score.toFixed(1)
            lines.push(`${baseName}：${valStr}（${phaseStr}）`)
          }
          return lines.join('<br/>')
        },
      },
      legend: {
        // 不显示 legend——避免 legend 默认配色视觉上覆盖分段着色
        show: false,
      },
      grid: { left: 50, right: 50, top: 40, bottom: 50 },
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
      series: seriesArr,
    }
  }, [visible, visiblePhases])

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
          三线均按各自阶段分段着色（红涨绿跌） · 直观展现三种赚钱风格的共生与竞争
          · 线宽：全局 3.5 / 打板 2.0 / 趋势 1.5
        </p>
        {/* 当前阶段标注：三条线各自 */}
        {latest && latestPhases && (
          <div className="mt-2 flex flex-wrap items-center gap-3 text-xs">
            <CurrentPhaseBadge
              label="全局"
              phase={latestPhases.globalPhase}
              score={latest.emotion_score}
            />
            <CurrentPhaseBadge
              label="打板"
              phase={latestPhases.boardPhase}
              score={latest.board_style_score}
            />
            <CurrentPhaseBadge
              label="趋势"
              phase={latestPhases.trendPhase}
              score={latest.trend_style_score}
            />
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

/** 当前阶段徽章（label + 阶段色圆点 + 阶段名 + 得分）。 */
function CurrentPhaseBadge({
  label,
  phase,
  score,
}: {
  label: string
  phase: string | null
  score: number | null
}) {
  const color = phase != null ? (PHASE_COLOR[phase] ?? '#94a3b8') : '#94a3b8'
  return (
    <span className="inline-flex items-center gap-1">
      <span className="text-slate-400">{label}</span>
      <span
        className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-medium"
        style={{
          borderColor: color,
          color,
          backgroundColor: `${color}1a`,
        }}
      >
        <span
          className="inline-block h-1.5 w-1.5 rounded-full"
          style={{ backgroundColor: color }}
          aria-hidden="true"
        />
        {phase ?? '—'}
      </span>
      {score != null && (
        <span className="font-semibold text-slate-700">{score.toFixed(1)}</span>
      )}
    </span>
  )
}
