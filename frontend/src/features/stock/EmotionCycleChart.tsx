/**
 * 情绪周期折线图组件（Task 5）。
 *
 * 视觉规范（v3.3 重绘）：线段形状本身表达阶段语义，不再按真实得分画线。
 * - 三条折线（全局 / 打板 / 趋势，线宽统一）各自按各自阶段绘制概念性曲线
 * - 每条线的阶段独立判定——全局用后端存储的 emotion_phase，
 *   打板/趋势在前端用 computePhase（与后端 compute_raw_phase 同算法）
 *   从各自 style_score + 3 日前得分算出
 * - 每段（连续相同阶段）按"固定每日增量 + 幅度上限"生成概念性 Y 值：
 *   段内每日增量只由阶段决定（与段长无关，同阶段恒定坡度），段总位移
 *   不超过该阶段幅度上限；Y 值不 clamp（截断会削平坡度），由 Y 轴按
 *   数据范围自适应——线段方向、陡峭程度、长度三级全部符合规范；
 *   tooltip 与徽章仍显示真实阶段 + 真实得分
 * - 分级规范（向下为亏钱效应、向上为赚钱效应，上下镜像对称）：
 *     冰点：最陡、最长、向下、蓝色（巨大亏钱效应）
 *     强分歧：较陡、较长、向下、深绿（仍有巨大亏钱效应）
 *     弱分歧：最缓、最短、向下、浅绿（最弱的分歧）
 *     高潮 = 冰点的镜像：最陡、最长、向上、紫色
 *     强修复 = 强分歧的镜像：较陡、较长、向上、深红
 *     弱修复 = 弱分歧的镜像：最缓、最短、向上、浅红
 * - 配色：冰点蓝 / 强分歧深绿 / 弱分歧浅绿 / 弱修复浅红 / 强修复深红 / 高潮紫
 *   下跌用蓝/绿、上涨用红、高潮用紫（与 A 股红涨绿跌一致）
 * - smooth: false——保留转折点；symbol: 'none'——只留线条
 * - 底部时间轴滑块（与 SectorHeatmap 一致）：数据 > 可见天数时显示
 * - 右侧标注当前阶段 + 得分（三条线各自）；顶部标题显示可见日期范围
 * - 空数据 / loading / error 状态兜底
 * - 老行 emotion_phase 为 null 时该段斜率 0（持平）、降级灰色
 *
 * 反包风格不单独画线，融入全局情绪周期（等权参与合成）。
 */
import { useEffect, useMemo, useState } from 'react'
import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'
import type { EmotionIndicators } from './types'

/**
 * 线段配色（用户 v3.3 定义）：冰点蓝 / 强分歧深绿 / 弱分歧浅绿，
 * 高潮紫 / 强修复深红 / 弱修复浅红。下跌用蓝/绿、上涨用红、高潮用紫。
 */
const PHASE_COLOR: Record<string, string> = {
  冰点: '#2563eb', // 蓝：巨大亏钱效应
  强分歧: '#15803d', // 深绿：仍有巨大亏钱效应
  弱分歧: '#86efac', // 浅绿：最弱的分歧
  弱修复: '#f87171', // 浅红：最弱的修复
  强修复: '#dc2626', // 深红：强修复（与强分歧镜像）
  高潮: '#9333ea', // 紫：高潮（与冰点镜像）
}

/**
 * 各阶段段幅度上限（一段连续相同阶段的总 Y 位移上限，绝对值）。
 *
 * 规范（用户 v3.3 定义）：长度三级 —— 冰点/高潮最长，强分歧/强修复次之，
 * 弱分歧/弱修复最短；上下镜像对称（高潮=冰点向上、强修复=强分歧向上、
 * 弱修复=弱分歧向上）。
 */
const PHASE_AMPLITUDE: Record<string, number> = {
  冰点: 50, // 最长
  强分歧: 34, // 较长
  弱分歧: 18, // 最短
  弱修复: 18, // 最短
  强修复: 34, // 较长
  高潮: 50, // 最长
}

/**
 * 各阶段每日 Y 增量（带符号，向下为负、向上为正），与段长无关——同一
 * 阶段在任何位置的陡峭程度完全一致。陡峭程度三级，差距足够大以保证
 * 视觉直观（用户 v3.3 定义）：
 * - 向下：冰点 -15（最陡）> 强分歧 -9 > 弱分歧 -4（最缓）
 * - 向上：高潮 +15（最陡）> 强修复 +9 > 弱修复 +4（最缓）
 * - 上下镜像对称（高潮=冰点向上、强修复=强分歧向上、弱修复=弱分歧向上）
 */
const PHASE_DAILY_DELTA: Record<string, number> = {
  冰点: -15, // 最陡向下
  强分歧: -9, // 次之向下
  弱分歧: -4, // 最缓向下
  弱修复: 4, // 最缓向上
  强修复: 9, // 次之向上
  高潮: 15, // 最陡向上
}

/** 未知阶段（null / 数据不足）的降级色。 */
const FALLBACK_COLOR = '#cbd5e1'

/** 统一线宽（用户 v3.3 定义：情绪周期内所有线条粗细一致）。 */
const LINE_WIDTH = 2.5

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
  if (score >= 60) {
    // 60-80 是"赚钱区间"：momentum>0 向高潮走=强修复(红)；
    // momentum<-5 急跌=赚钱效应收敛=弱分歧(浅绿)；平稳=强修复(红)。
    // 与后端 domain.stock.emotion_cycle.compute_raw_phase 保持一致
    if (momentum > 0) return '强修复'
    if (momentum < -5) return '弱分歧'
    return '强修复'
  }
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

/**
 * 按"固定每日增量 + 段幅度上限"生成概念性 Y 值曲线。
 *
 * 不再用真实得分画线（真实得分变化不符合阶段形状规范）。先把阶段序列切成
 * 若干"连续相同阶段"的段，每段独立绘制：
 * - 段内每日增量固定（PHASE_DAILY_DELTA），与段长无关 —— 同一阶段在任何
 *   位置的陡峭程度完全一致：向下冰点最陡 > 强分歧 > 弱分歧；向上高潮最陡
 *   > 强修复 > 弱修复；上下镜像对称
 * - 段总位移以 PHASE_AMPLITUDE 为上限：持续天数足够时走完上限后持平
 *   （段长度三级：冰点/高潮最长 > 强分歧/强修复 > 弱分歧/弱修复）；
 *   段更短时按固定坡度走，走不满上限（线段随持续天数自然变短）
 * - Y 值不做 clamp——截断会削平坡度造成"同阶段不同陡峭度"的假象；
 *   曲线自由累积，由 Y 轴按数据范围自适应缩放兜底
 * - null / 未知阶段视为增量 0（持平）、降级灰色
 *
 * @param phases - 每日阶段序列（可为 null）
 * @param startValue - 起点 Y 值（默认 50，居中便于上下展开）
 * @returns 概念性 Y 值数组（长度与 phases 相同，无 null）
 */
function buildConceptualScores(
  phases: Array<string | null>,
  startValue = 50,
): number[] {
  const scores: number[] = []
  let y = startValue
  let i = 0
  while (i < phases.length) {
    // 切出一段连续相同阶段 [i, j)
    let j = i + 1
    while (j < phases.length && phases[j] === phases[i]) j++
    const runLen = j - i
    const phase = phases[i]
    // 每日增量固定（带符号，向下为负）：只由阶段决定，与段长无关，
    // 保证同一阶段在任何位置的陡峭程度完全一致
    const dailyDelta = phase != null ? (PHASE_DAILY_DELTA[phase] ?? 0) : 0
    let remaining = phase != null ? (PHASE_AMPLITUDE[phase] ?? 0) : 0
    for (let k = 0; k < runLen; k++) {
      const step = Math.sign(dailyDelta) * Math.min(Math.abs(dailyDelta), remaining)
      y += step // 不 clamp：截断会削平坡度，Y 轴自适应缩放兜底
      remaining -= Math.abs(step)
      scores.push(y)
    }
    i = j
  }
  return scores
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
        endLabel?: {
          show: boolean
          formatter: string
          color: string
          fontSize: number
          distance: number
        }
      }> = []
      if (scores.length === 0) return result
      // 拆分逻辑：扫描 [0, n)，每当 phase 在 i 处变化时，在 i-1 处关闭当前段。
      // 关键：当前段数据范围 [segStart, i-1]，下一段从 **i-1** 开始（含转折点），
      // 让段 A 末点 = 段 B 首点（同一 X 索引 i-1），视觉上仍是连续折线。
      // 这样每个区间 k→k+1 都由"第 k+1 天所属的新段"绘制、用第 k+1 天的阶段
      // 着色——与 buildConceptualScores 中"第 k+1 天的阶段决定 k→k+1 步进"
      // 的规则一致，颜色与坡度不再错位。
      const points: Array<[number, number | null, string | null]> = scores.map(
        (s, idx) => [idx, s, phases[idx] ?? null],
      )
      let segStart = 0
      let segPhase: string | null = points[0]?.[2] ?? null
      for (let i = 1; i <= points.length; i++) {
        const p = i < points.length ? points[i]?.[2] : null
        const isBoundary = i === points.length || p !== segPhase
        if (!isBoundary) continue
        // 段数据点 [segStart, i-1]：末段（i === n）自然含到 n-1；
        // 非末段在转折点前一天 i-1 关闭，新段从 i-1 起绘（含 i-1→i 区间）
        const data: Array<[number, number | null]> = []
        for (let j = segStart; j <= i - 1; j++) {
          const pt = points[j]
          if (pt) data.push([pt[0], pt[1]])
        }
        const phaseName = segPhase ?? '—'
        const color = segPhase != null ? PHASE_COLOR[segPhase] : FALLBACK_COLOR
        result.push({
          name: `${baseName}·${phaseName}`,
          type: 'line',
          data,
          connectNulls: false,
          smooth: false,
          symbol: 'none',
          lineStyle: { width: lineWidth, color },
          showSymbol: false,
          legendHoverLink: false,
          z: baseName === '全局' ? 3 : baseName === '打板' ? 2 : 1,
          silent: true,
          tooltip: { show: false },
        })
        // 下一段从 i-1 开始（i-1 是共享的转折点，i-1→i 区间用新阶段着色）
        segStart = i - 1
        segPhase = p
      }
      // 线名尾标：只挂在该线最后一个非空段上（即整条线的右端末点），
      // 用于区分三条线宽一致的线（用户 v3.3 定义）。颜色固定深灰，
      // 避免与阶段配色混淆。
      for (let k = result.length - 1; k >= 0; k--) {
        const seg = result[k]
        if (seg && seg.data.length > 0) {
          seg.endLabel = {
            show: true,
            formatter: baseName,
            color: '#334155',
            fontSize: 11,
            distance: 6,
          }
          break
        }
      }
      return result
    }

    // 三条线各自用各自 phase（全局/打板/趋势独立判定），按"固定每日增量
    // + 段幅度上限"生成概念性 Y 值曲线——线段方向、陡峭程度、长度三级全部
    // 符合用户 v3.3 视觉规范。tooltip 与徽章仍显示真实阶段 + 真实得分。
    const globalPhases = visiblePhases.map((p) => p?.globalPhase ?? null)
    const boardPhases = visiblePhases.map((p) => p?.boardPhase ?? null)
    const trendPhases = visiblePhases.map((p) => p?.trendPhase ?? null)

    const globalScores = buildConceptualScores(globalPhases)
    const boardScores = buildConceptualScores(boardPhases)
    const trendScores = buildConceptualScores(trendPhases)

    // 三条线线宽统一（用户 v3.3 定义：情绪周期内所有线条粗细一致）
    const seriesArr = [
      ...buildSegments('全局', globalScores, globalPhases, LINE_WIDTH),
      ...buildSegments('打板', boardScores, boardPhases, LINE_WIDTH),
      ...buildSegments('趋势', trendScores, trendPhases, LINE_WIDTH),
    ]

    // Y 轴按数据范围自适应：概念曲线不做 clamp（截断会削平坡度），
    // 改为取三条线的极值向上下各留 10 余量、对齐到 10 的整数倍
    const allScores = [...globalScores, ...boardScores, ...trendScores]
    const dataMin = Math.min(...allScores)
    const dataMax = Math.max(...allScores)
    const yMin = Math.floor((dataMin - 10) / 10) * 10
    const yMax = Math.ceil((dataMax + 10) / 10) * 10

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
          const e = visible[idx]
          // 三条线各自 phase 独立 → tooltip 显示各自阶段 + 真实得分
          // （图上 Y 值是概念性斜率曲线，不等于真实得分，故同时展示真实得分）
          const lines = [`<b>${fmtDateShort(dt)}</b>`]
          const entries: Array<{
            label: string
            phase: string | null
            score: number | null
          }> = [
            { label: '全局', phase: ph?.globalPhase ?? null, score: e?.emotion_score ?? null },
            { label: '打板', phase: ph?.boardPhase ?? null, score: e?.board_style_score ?? null },
            { label: '趋势', phase: ph?.trendPhase ?? null, score: e?.trend_style_score ?? null },
          ]
          for (const it of entries) {
            const phaseStr = it.phase ?? '—'
            const valStr = it.score == null ? '—' : it.score.toFixed(1)
            lines.push(`${it.label}：${phaseStr}（实际 ${valStr}）`)
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
        // 自适应范围（概念曲线不 clamp，截断会削平坡度造成同阶段不同
        // 陡峭度的假象）；刻度无业务含义，tooltip 展示真实得分
        min: yMin,
        max: yMax,
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
          线段形状表达阶段语义：冰点最陡最长向下（蓝）/ 高潮最陡最长向上（紫），
          强分歧（深绿）·强修复（深红）次之，弱分歧（浅绿）·弱修复（浅红）最缓最短
          · 三条线线宽一致，线尾标注线名 · 悬停查看真实得分
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
