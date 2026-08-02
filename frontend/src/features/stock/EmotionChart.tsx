/**
 * 情绪多日曲线组件（Task 7）。
 *
 * 设计要点：
 * - 主图使用 echarts-for-react 渲染柱状/折线混合（涨停数 + 有效涨停 + 炸板率）
 * - 最高板**单独**折线图（TopBoardChart）——独立组件，每点标注龙头股票代码
 * - 空 series → 显示"暂无数据"占位（不臆测）
 * - 窗口切换控件 5/10/20/60 日，键盘可达（aria-pressed）
 * - 图表容器带 aria-label，遵循可访问性
 */
import { useMemo, useState } from 'react'
import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'
import type { EmotionIndicators } from './types'

/** 窗口切换选项。 */
const WINDOW_OPTIONS = [5, 10, 20, 60] as const

export interface EmotionChartProps {
  series: EmotionIndicators[]
  windowDays: number
  endDate: string
  /** 窗口切换回调；缺省时控件只本地 state 切换。 */
  onWindowChange?: (days: number) => void
  /** 加载中 → 渲染骨架态（与空数据区分）。 */
  loading?: boolean
  /** 错误信息 → 渲染错误占位。 */
  error?: string | null
}

export function EmotionChart({
  series,
  windowDays,
  endDate,
  onWindowChange,
  loading,
  error,
}: EmotionChartProps) {
  const [localWindow, setLocalWindow] = useState<number>(windowDays)
  const activeWindow = onWindowChange ? windowDays : localWindow

  // 截取最近 N 条（series 已按后端倒序返回：最新在前）
  const trimmed = useMemo(
    () => series.slice(0, activeWindow),
    [series, activeWindow],
  )

  const option = useMemo<EChartsOption | undefined>(() => {
    if (trimmed.length === 0) return undefined
    // 倒序展示：x 轴从最旧到最新（人眼时间方向）
    const ordered = [...trimmed].reverse()
    return {
      tooltip: { trigger: 'axis' },
      legend: { data: ['涨停数', '有效涨停', '炸板率'] },
      grid: { left: 50, right: 50, top: 40, bottom: 50 },
      xAxis: {
        type: 'category',
        data: ordered.map((e) => e.trade_date),
      },
      yAxis: [
        { type: 'value', name: '数量', position: 'left' },
        { type: 'value', name: '炸板率', position: 'right', max: 1 },
      ],
      series: [
        {
          name: '涨停数',
          type: 'bar',
          data: ordered.map((e) => e.limit_up_count),
          itemStyle: { color: '#ef4444' },
        },
        {
          name: '有效涨停',
          type: 'bar',
          data: ordered.map((e) => e.valid_limit_up_count),
          itemStyle: { color: '#f97316' },
        },
        {
          name: '炸板率',
          type: 'line',
          yAxisIndex: 1,
          data: ordered.map((e) =>
            e.broken_limit_ratio == null ? null : Number(e.broken_limit_ratio.toFixed(3)),
          ),
          itemStyle: { color: '#a855f7' },
        },
      ],
    }
  }, [trimmed])

  const handleWindowClick = (days: number) => {
    if (onWindowChange) {
      onWindowChange(days)
    } else {
      setLocalWindow(days)
    }
  }

  return (
    <section
      className="rounded-xl border border-slate-200 bg-white p-4"
      aria-label="情绪多日趋势"
    >
      <header className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-700">
          情绪多日曲线（截止 {endDate}）
        </h3>
        <div
          className="flex gap-1"
          role="group"
          aria-label="窗口切换"
        >
          {WINDOW_OPTIONS.map((d) => {
            const active = activeWindow === d
            return (
              <button
                key={d}
                type="button"
                aria-pressed={active}
                onClick={() => handleWindowClick(d)}
                className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                  active
                    ? 'bg-indigo-600 text-white'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                {d}日
              </button>
            )
          })}
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
          加载情绪曲线…
        </div>
      ) : trimmed.length === 0 || !option ? (
        <div
          className="flex h-64 items-center justify-center rounded-lg border border-dashed border-slate-200 text-sm text-slate-400"
          role="status"
        >
          暂无数据
        </div>
      ) : (
        <>
          <div
            aria-label="情绪多日曲线图"
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
          {/* Bug⑤ 修复：最高板独立折线图，每个点标注龙头股票代码 */}
          <TopBoardChart items={trimmed} />
        </>
      )}
    </section>
  )
}

/**
 * 最高板独立折线图（Bug⑤ 修复）。
 *
 * 设计要点：
 * - 单独一个折线图，每个数据点对应一个交易日的"最高连板"高度
 * - 每个点 tooltip 显示该日龙头股票代码（从 top_board_leaders 取）
 * - x 轴下方另起一行 code chip，让"高度"和"龙头"视觉分离（之前混在
 *   多系列图里看不出来）
 */
function TopBoardChart({ items }: { items: EmotionIndicators[] }) {
  const option = useMemo<EChartsOption | undefined>(() => {
    if (items.length === 0) return undefined
    // series 倒序展示
    const ordered = [...items].reverse()
    // 计算"断板位置"（连板高度下降的数据点）→ 视觉强调
    const downPoints = ordered
      .map((e, idx) => {
        if (idx === 0) return null
        const prev = ordered[idx - 1]?.max_consecutive_boards ?? 0
        if (e.max_consecutive_boards < prev) {
          return {
            name: '断板',
            xAxis: e.trade_date,
            yAxis: e.max_consecutive_boards,
            value: `${e.top_board_leaders[0] ?? '—'}`,
          }
        }
        return null
      })
      .filter((p): p is { name: string; xAxis: string; yAxis: number; value: string } => p !== null)

    // 最新一日的最高板龙头——加 markPoint 醒目显示
    const latest = ordered[ordered.length - 1]
    const latestLeaders = latest?.top_board_leaders ?? []
    const latestPoint = latest
      ? {
          name: '最新龙头',
          xAxis: latest.trade_date,
          yAxis: latest.max_consecutive_boards,
          value: `${latestLeaders[0] ?? '—'}`,
        }
      : null

    return {
      tooltip: {
        trigger: 'axis',
        formatter: (params: unknown) => {
          const arr = params as Array<{
            axisValue: string
            data: number
            marker: string
          }>
          const p = arr[0]
          if (!p) return ''
          const idx = ordered.findIndex((e) => e.trade_date === p.axisValue)
          const leaders =
            idx >= 0 ? ordered[idx]?.top_board_leaders ?? [] : []
          const leadersStr =
            leaders.length > 0 ? leaders.join(', ') : '暂无龙头'
          return [
            `${p.axisValue}`,
            `${p.marker}最高板：${p.data} 板`,
            `龙头：${leadersStr}`,
          ].join('<br/>')
        },
      },
      legend: { data: ['最高板（连板高度）', '断板', '最新龙头'] },
      grid: { left: 50, right: 30, top: 60, bottom: 70 },
      xAxis: {
        type: 'category',
        data: ordered.map((e) => e.trade_date),
        axisLabel: {
          interval: 0,
          formatter: (val: string, idx: number) => {
            const leaders = ordered[idx]?.top_board_leaders ?? []
            const firstLeader = leaders[0] ?? '—'
            return `{date|${val}}\n{leader|${firstLeader}${leaders.length > 1 ? ` 等${leaders.length}只` : ''}}`
          },
          rich: {
            date: { color: '#475569', fontSize: 11 },
            leader: { color: '#0ea5e9', fontSize: 10, fontFamily: 'monospace' },
          },
        },
      },
      yAxis: {
        type: 'value',
        name: '板数',
        minInterval: 1,
      },
      series: [
        {
          name: '最高板（连板高度）',
          type: 'line',
          data: ordered.map((e) => e.max_consecutive_boards),
          itemStyle: { color: '#0ea5e9' },
          symbol: 'circle',
          symbolSize: 10,
          label: {
            show: true,
            position: 'top',
            // 每点 label 显示"X 板\n龙头代码"
            formatter: (params: unknown) => {
              const p = params as { value: number; dataIndex: number }
              const idx = p.dataIndex
              const leaders = ordered[idx]?.top_board_leaders ?? []
              const code = leaders[0] ?? '—'
              return `${p.value} 板\n${code}`
            },
            color: '#0ea5e9',
            fontSize: 10,
            lineHeight: 12,
          },
          emphasis: {
            focus: 'series',
            itemStyle: { color: '#0369a1' },
          },
          lineStyle: { width: 2 },
          areaStyle: { color: 'rgba(14,165,233,0.1)' },
          // 断板处 + 最新龙头 → markPoint 强化
          markPoint: {
            symbol: 'pin',
            symbolSize: [50, 28],
            data: [
              ...(latestPoint ? [latestPoint] : []),
              ...downPoints,
            ],
            label: {
              show: true,
              color: '#ffffff',
              fontSize: 9,
              fontFamily: 'monospace',
              formatter: (params: unknown) => {
                const p = params as { name: string; value: string }
                return p.value
              },
            },
            // 颜色用 data[i].itemStyle 区分：最新龙头红、断板橙
            itemStyle: {
              color: '#dc2626',
            },
          },
        },
      ],
    }
  }, [items])

  if (!option) {
    return null
  }

  return (
    <div
      className="mt-4 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2"
      aria-label="最高板独立折线图"
    >
      <h4 className="mb-2 text-xs font-semibold text-slate-700">
        最高板折线（每个点显示该日龙头）
      </h4>
      <div
        aria-label="最高板折线图"
        role="img"
        className="h-56 w-full"
      >
        <ReactECharts
          option={option}
          style={{ height: '100%', width: '100%' }}
          notMerge
          lazyUpdate
          opts={{ renderer: 'canvas' }}
        />
      </div>
    </div>
  )
}