/**
 * 股市复盘主页（Task 7）。
 *
 * 设计要点：
 * - 顶部：大盘快照 + 触发复盘按钮（日期选择）
 * - 中部：情绪多日曲线 + 板块轮动（窗口切换）
 * - 底部：观察池 + 历史复盘文列表
 * - 加载/错误态可访问；空数据"暂无数据"占位
 * - 通过 stockApi 走 cookie + CSRF 客户端（不走 localStorage token）
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, TrendingUp, RefreshCw, FileText } from 'lucide-react'
import { AppLayout } from '../../components/AppLayout'
import { stockApi, StockApiError } from './api'
import { EmotionChart } from './EmotionChart'
import { MarketOverview } from './MarketOverview'
import { ReviewTrigger } from './ReviewTrigger'
import { ReviewReportView } from './ReviewReport'
import { SectorHeatmap } from './SectorHeatmap'
import { Watchlist } from './Watchlist'
import type {
  MarketSnapshot,
  ReviewReport,
  SectorPerformance,
  WatchlistStock,
} from './types'

/** 当前日期 → YYYYMMDD。 */
function todayStr(): string {
  const d = new Date()
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}${m}${day}`
}

/** YYYYMMDD → 友好显示。 */
function fmtDate(s: string): string {
  if (s.length !== 8) return s
  return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`
}

export function StockPage() {
  const navigate = useNavigate()
  const { reportId: routeReportId } = useParams<{ reportId?: string }>()

  const today = useMemo(() => todayStr(), [])

  const [tradeDate, setTradeDate] = useState<string>(today)
  const [emotionWindow, setEmotionWindow] = useState<number>(10)

  // 详情视图（从 /stock/reports/:reportId 进来）
  if (routeReportId) {
    return <ReportDetail reportId={routeReportId} onBack={() => navigate('/stock')} />
  }

  return (
    <AppLayout>
      <StockIndexBody
        tradeDate={tradeDate}
        onTradeDateChange={setTradeDate}
        emotionWindow={emotionWindow}
        onEmotionWindowChange={setEmotionWindow}
      />
    </AppLayout>
  )
}

interface StockIndexBodyProps {
  tradeDate: string
  onTradeDateChange: (s: string) => void
  emotionWindow: number
  onEmotionWindowChange: (n: number) => void
}

function StockIndexBody({
  tradeDate,
  onTradeDateChange,
  emotionWindow,
  onEmotionWindowChange,
}: StockIndexBodyProps) {
  const navigate = useNavigate()
  // 大盘快照
  const [snapshot, setSnapshot] = useState<MarketSnapshot | null>(null)
  const [snapshotLoading, setSnapshotLoading] = useState(true)
  const [snapshotError, setSnapshotError] = useState<string | null>(null)

  // 情绪曲线
  const [emotion, setEmotion] = useState<{
    series: import('./types').EmotionIndicators[]
  } | null>(null)
  const [emotionLoading, setEmotionLoading] = useState(true)
  const [emotionError, setEmotionError] = useState<string | null>(null)

  // 板块轮动（多日热力图）
  const [sectorChart, setSectorChart] = useState<{
    series: SectorPerformance[]
    window_days: number
  } | null>(null)
  const [sectorsLoading, setSectorsLoading] = useState(true)
  const [sectorsError, setSectorsError] = useState<string | null>(null)

  // 观察池
  const [watchlist, setWatchlist] = useState<WatchlistStock[]>([])
  const [watchlistLoading, setWatchlistLoading] = useState(true)
  const [watchlistError, setWatchlistError] = useState<string | null>(null)

  // 历史复盘文
  const [reports, setReports] = useState<ReviewReport[]>([])
  const [reportsLoading, setReportsLoading] = useState(true)
  const [reportsError, setReportsError] = useState<string | null>(null)

  const loadAll = useCallback(async () => {
    setSnapshotLoading(true)
    setEmotionLoading(true)
    setSectorsLoading(true)
    setWatchlistLoading(true)
    setReportsLoading(true)
    setSnapshotError(null)
    setEmotionError(null)
    setSectorsError(null)
    setWatchlistError(null)
    setReportsError(null)

    const [snap, emo, sec, wl, rep] = await Promise.allSettled([
      stockApi.getMarketSnapshot(tradeDate),
      stockApi.getEmotionChart(tradeDate, 60),
      stockApi.getSectorChart(tradeDate, 60),
      stockApi.getWatchlist(),
      stockApi.listReports(20),
    ])

    if (snap.status === 'fulfilled') {
      setSnapshot(snap.value)
    } else {
      setSnapshot(null)
      setSnapshotError(
        snap.reason instanceof StockApiError
          ? snap.reason.message
          : '获取大盘快照失败',
      )
    }
    if (emo.status === 'fulfilled') {
      setEmotion({ series: emo.value.series })
    } else {
      setEmotion(null)
      setEmotionError(
        emo.reason instanceof StockApiError
          ? emo.reason.message
          : '获取情绪曲线失败',
      )
    }
    if (sec.status === 'fulfilled') {
      setSectorChart({
        series: sec.value.series,
        window_days: sec.value.window_days,
      })
    } else {
      setSectorChart(null)
      setSectorsError(
        sec.reason instanceof StockApiError
          ? sec.reason.message
          : '获取板块轮动失败',
      )
    }
    if (wl.status === 'fulfilled') {
      setWatchlist(wl.value.items)
    } else {
      setWatchlist([])
      setWatchlistError(
        wl.reason instanceof StockApiError
          ? wl.reason.message
          : '获取观察池失败',
      )
    }
    if (rep.status === 'fulfilled') {
      setReports(rep.value.items)
    } else {
      setReports([])
      setReportsError(
        rep.reason instanceof StockApiError
          ? rep.reason.message
          : '获取复盘文列表失败',
      )
    }

    setSnapshotLoading(false)
    setEmotionLoading(false)
    setSectorsLoading(false)
    setWatchlistLoading(false)
    setReportsLoading(false)
  }, [tradeDate])

  useEffect(() => {
    void loadAll()
  }, [loadAll])

  const handleRemove = useCallback(
    async (stockCode: string) => {
      try {
        await stockApi.postWatchlistAction({
          action: 'remove',
          stock_code: stockCode,
        })
        setWatchlist((prev) => prev.filter((s) => s.stock_code !== stockCode))
      } catch (e) {
        // 静默：让 loadAll 自然重新拉取
        void e
      }
    },
    [],
  )

  return (
    <div className="min-h-full p-6">
      {/* 顶部条 */}
      <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => navigate('/')}
            className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100"
            aria-label="返回主页"
          >
            <ArrowLeft size={18} />
          </button>
          <div>
            <h1 className="flex items-center gap-2 text-xl font-semibold text-slate-800">
              <TrendingUp size={20} className="text-indigo-500" />
              股市复盘
            </h1>
            <p className="mt-0.5 text-xs text-slate-500">
              A 股每日复盘 · 情绪周期方法论
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-1.5 text-sm text-slate-600">
            交易日
            <input
              type="date"
              value={
                tradeDate.length === 8 ? fmtDate(tradeDate) : tradeDate
              }
              onChange={(e) => {
                const v = e.target.value.replace(/-/g, '')
                if (/^\d{8}$/.test(v)) onTradeDateChange(v)
              }}
              className="rounded-md border border-slate-200 px-2 py-1 text-sm"
              aria-label="选择交易日"
            />
          </label>
          <button
            type="button"
            onClick={() => {
              void loadAll()
            }}
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-600 hover:bg-slate-50"
            aria-label="刷新数据"
          >
            <RefreshCw size={12} />
            刷新
          </button>
          <ReviewTrigger tradeDate={tradeDate} />
        </div>
      </header>

      {/* 主体栅格 */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-4">
          <MarketOverview
            snapshot={snapshot}
            loading={snapshotLoading}
            error={snapshotError}
          />
          <EmotionChart
            series={emotion?.series ?? []}
            windowDays={emotionWindow}
            endDate={tradeDate}
            onWindowChange={onEmotionWindowChange}
            loading={emotionLoading}
            error={emotionError}
          />
          <SectorHeatmap
            series={sectorChart?.series ?? []}
            endDate={tradeDate}
            days={10}
            loading={sectorsLoading}
            error={sectorsError}
          />
        </div>
        <div className="space-y-4">
          <Watchlist
            items={watchlist}
            onRemove={handleRemove}
            loading={watchlistLoading}
            error={watchlistError}
          />
          <ReportsListCard
            reports={reports}
            loading={reportsLoading}
            error={reportsError}
          />
        </div>
      </div>
    </div>
  )
}

interface ReportsListCardProps {
  reports: ReviewReport[]
  loading: boolean
  error: string | null
}

function ReportsListCard({ reports, loading, error }: ReportsListCardProps) {
  const navigate = useNavigate()
  if (loading) {
    return (
      <div
        className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-500"
        role="status"
      >
        加载历史复盘…
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
  if (reports.length === 0) {
    return (
      <div
        className="rounded-xl border border-dashed border-slate-200 bg-white p-4 text-center text-sm text-slate-400"
        role="status"
      >
        暂无历史复盘
      </div>
    )
  }
  return (
    <section
      className="rounded-xl border border-slate-200 bg-white p-4"
      aria-label="历史复盘文"
    >
      <header className="mb-3">
        <h3 className="text-sm font-semibold text-slate-700">
          历史复盘（{reports.length} 篇）
        </h3>
      </header>
      <ul className="divide-y divide-slate-100">
        {reports.map((r) => (
          <li key={r.id}>
            <button
              type="button"
              onClick={() => navigate(`/stock/reports/${r.id}`)}
              className="flex w-full items-center justify-between py-2 text-left hover:bg-slate-50"
            >
              <div className="flex items-center gap-2">
                <FileText size={14} className="text-slate-400" />
                <div>
                  <p className="text-sm font-medium text-slate-700">
                    复盘 · {r.trade_date}
                  </p>
                  <p className="text-xs text-slate-500">
                    {new Date(r.created_at).toLocaleString('zh-CN')}
                  </p>
                </div>
              </div>
              <span className="text-xs text-slate-400">{r.status}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}

interface ReportDetailProps {
  reportId: string
  onBack: () => void
}

function ReportDetail({ reportId, onBack }: ReportDetailProps) {
  const [report, setReport] = useState<ReviewReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    stockApi
      .getReport(reportId)
      .then((r) => {
        if (cancelled) return
        setReport(r)
        setLoading(false)
      })
      .catch((e: unknown) => {
        if (cancelled) return
        setError(e instanceof Error ? e.message : '加载复盘文失败')
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [reportId])

  return (
    <AppLayout>
      <div className="min-h-full p-6">
        <header className="mb-4 flex items-center gap-3">
          <button
            type="button"
            onClick={onBack}
            className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100"
            aria-label="返回列表"
          >
            <ArrowLeft size={18} />
          </button>
          <h1 className="text-lg font-semibold text-slate-800">复盘文详情</h1>
        </header>
        <ReviewReportView
          report={report}
          loading={loading}
          error={error}
        />
      </div>
    </AppLayout>
  )
}
