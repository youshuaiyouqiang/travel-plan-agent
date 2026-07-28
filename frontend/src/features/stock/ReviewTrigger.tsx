/**
 * 复盘触发组件（Task 7）。
 *
 * 设计要点：
 * - 点击"生成复盘" → POST /review 拿 task_id → 轮询 GET /review/tasks/{id}
 * - 轮询三分支：
 *   1. 完成态（completed / degraded / no_data）且 report_id 存在 → 跳转 /stock/reports/{id}
 *   2. failed → 展示错误文案 + 重试按钮（不自动重试）
 *   3. 轮询 404（任务过期/进程重启）→ 提示"任务已过期，请重新触发"
 * - 组件卸载时清理定时器（不泄漏）
 * - 轮询上限 60 次（3s × 60 = 3 分钟），避免无限循环
 */
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, AlertTriangle, RefreshCw, PlayCircle } from 'lucide-react'
import { stockApi } from './api'
import type { ReviewTaskStatus } from './types'

/** 视为"完成"的最终态（带 report_id 可跳转）。 */
const FINAL_STATES = new Set<ReviewTaskStatus['status']>([
  'completed',
  'degraded',
  'no_data',
])

/** 轮询间隔（毫秒）。 */
const POLL_INTERVAL_MS = 3000
/** 轮询上限次数（避免无限循环）。 */
const MAX_POLLS = 60

export interface ReviewTriggerProps {
  tradeDate: string
  /** 自定义按钮文案（默认"生成复盘"）。 */
  buttonLabel?: string
}

type TriggerState =
  | { kind: 'idle' }
  | { kind: 'polling'; pollCount: number }
  | { kind: 'done'; reportId: string }
  | { kind: 'failed'; errorCode?: string; errorMessage?: string }
  | { kind: 'expired' }

export function ReviewTrigger({
  tradeDate,
  buttonLabel = '生成复盘',
}: ReviewTriggerProps) {
  const navigate = useNavigate()
  const [state, setState] = useState<TriggerState>({ kind: 'idle' })
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const taskIdRef = useRef<string | null>(null)
  const pollCountRef = useRef(0)

  const clearTimer = () => {
    if (timerRef.current !== null) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
  }

  // 卸载清理
  useEffect(() => {
    return () => {
      clearTimer()
    }
  }, [])

  const startPolling = (taskId: string) => {
    taskIdRef.current = taskId
    pollCountRef.current = 0
    setState({ kind: 'polling', pollCount: 0 })

    const tick = async () => {
      pollCountRef.current += 1
      if (pollCountRef.current > MAX_POLLS) {
        clearTimer()
        setState({ kind: 'expired' })
        return
      }
      const res = await stockApi.getReviewTaskRaw(taskId)
      if (res.status === 404) {
        // 任务过期 / 进程重启
        clearTimer()
        setState({ kind: 'expired' })
        return
      }
      if (!res.ok) {
        clearTimer()
        setState({
          kind: 'failed',
          errorMessage: `查询任务失败 (HTTP ${res.status})`,
        })
        return
      }
      const data = (await res.json()) as ReviewTaskStatus
      setState((prev) =>
        prev.kind === 'polling'
          ? { kind: 'polling', pollCount: pollCountRef.current }
          : prev,
      )
      if (FINAL_STATES.has(data.status) && data.report_id) {
        clearTimer()
        setState({ kind: 'done', reportId: data.report_id })
        navigate(`/stock/reports/${data.report_id}`)
        return
      }
      if (data.status === 'failed') {
        clearTimer()
        setState({
          kind: 'failed',
          errorCode: undefined,
          errorMessage: data.error ?? '复盘生成失败',
        })
      }
    }

    void tick()
    timerRef.current = setInterval(() => {
      void tick()
    }, POLL_INTERVAL_MS)
  }

  const handleTrigger = async () => {
    setState({ kind: 'polling', pollCount: 0 })
    try {
      const resp = await stockApi.triggerReview(tradeDate)
      startPolling(resp.task_id)
    } catch (e) {
      setState({
        kind: 'failed',
        errorMessage: e instanceof Error ? e.message : '触发复盘失败',
      })
    }
  }

  const handleRetry = () => {
    setState({ kind: 'idle' })
  }

  // ── 渲染分支 ──

  if (state.kind === 'polling') {
    return (
      <div
        className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm text-slate-600"
        role="status"
        aria-live="polite"
      >
        <Loader2 size={16} className="animate-spin text-indigo-500" />
        复盘生成中…（第 {state.pollCount}/{MAX_POLLS} 次轮询）
      </div>
    )
  }

  if (state.kind === 'failed') {
    return (
      <div
        className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700"
        role="alert"
      >
        <div className="flex items-start gap-2">
          <AlertTriangle size={16} className="mt-0.5 flex-shrink-0" />
          <div className="flex-1">
            <p className="font-medium">复盘生成失败</p>
            {state.errorMessage && (
              <p className="mt-0.5 text-xs text-rose-600">
                {state.errorCode ? `[${state.errorCode}] ` : ''}
                {state.errorMessage}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={handleRetry}
            className="flex items-center gap-1 rounded-md bg-white px-2.5 py-1 text-xs font-medium text-rose-700 ring-1 ring-rose-200 hover:bg-rose-100"
          >
            <RefreshCw size={12} />
            重新触发
          </button>
        </div>
      </div>
    )
  }

  if (state.kind === 'expired') {
    return (
      <div
        className="flex items-center justify-between gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-700"
        role="alert"
      >
        <div className="flex items-center gap-2">
          <AlertTriangle size={16} />
          任务已过期，请重新触发
        </div>
        <button
          type="button"
          onClick={handleRetry}
          className="flex items-center gap-1 rounded-md bg-white px-2.5 py-1 text-xs font-medium text-amber-700 ring-1 ring-amber-200 hover:bg-amber-100"
        >
          <RefreshCw size={12} />
          重新触发
        </button>
      </div>
    )
  }

  // idle / done（done 极短：已触发 navigate，不显示）
  return (
    <button
      type="button"
      onClick={() => {
        void handleTrigger()
      }}
      className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-1"
    >
      <PlayCircle size={16} />
      {buttonLabel}
    </button>
  )
}
