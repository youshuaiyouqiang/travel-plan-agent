/**
 * 情绪多日曲线组件（Task 7）。
 *
 * 设计要点：
 * - 使用 echarts-for-react 渲染折线/柱状混合图（涨停数 + 炸板率 + 连板高度）
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
      legend: { data: ['涨停数', '有效涨停', '炸板率', '最高连板'] },
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
        {
          name: '最高连板',
          type: 'line',
          data: ordered.map((e) => e.max_consecutive_boards),
          itemStyle: { color: '#0ea5e9' },
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
          {/* 最高板龙头：单独表格，仅展示当前窗口最后一日（最新日）的龙头
              与 max_consecutive_boards，避免与折线图挤在一起看不清。 */}
          <TopBoardLeaders latest={trimmed[0]} />
        </>
      )}
    </section>
  )
}

/**
 * 最高板龙头小表格。
 *
 * 修复：原 emotion 曲线把 "最高连板" 画成单数字折线，混在多指标中看不出"是哪只股票"。
 * 现在拆成单独表格，明示龙头代码，连板数。
 */
function TopBoardLeaders({ latest }: { latest: EmotionIndicators }) {
  const maxBoards = latest.max_consecutive_boards
  const leaders = latest.top_board_leaders ?? []
  const hasData = leaders.length > 0 && maxBoards > 0

  return (
    <div
      className="mt-4 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700"
      aria-label={`${latest.trade_date} 最高板龙头`}
    >
      <div className="mb-1 flex items-center gap-2">
        <span className="font-semibold text-slate-800">{latest.trade_date}</span>
        <span>最高板</span>
        <span className="rounded bg-sky-100 px-1.5 py-0.5 font-mono text-sky-800">
          {maxBoards} 板
        </span>
      </div>
      {hasData ? (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-slate-500">龙头：</span>
          {leaders.map((code) => (
            <span
              key={code}
              className="rounded bg-white px-2 py-0.5 font-mono text-slate-800 shadow-sm"
            >
              {code}
            </span>
          ))}
        </div>
      ) : (
        <div className="text-slate-400">当日暂无龙头数据</div>
      )}
    </div>
  )
}
