/**
 * 股市复盘前端 API 客户端（Task 7）。
 *
 * 设计要点：
 * - 所有请求统一走 ``features/auth/client.ts`` 的 cookie + CSRF 流程；
 *   浏览器不持有长期认证令牌（AGENTS.md §4）。
 * - 不向 localStorage / sessionStorage 持久化任何 token。
 * - 端点路径与后端 ``/api/v1/stock/*`` 严格对齐（api/v1/stock.py）。
 * - 任务状态走轮询（GET /review/tasks/{task_id}），不引入 SSE。
 * - 错误响应形如 ``{"code": "...", "message": "..."}`` 或
 *   ``{"detail": {"code": "...", "message": "..."}}``。
 */
import { AuthClient } from '../auth/client'
import type {
  CorrelationResult,
  EmotionChartResponse,
  LimitStock,
  MarketSnapshot,
  ReviewReport,
  ReviewTaskStatus,
  SectorChartResponse,
  SectorLeader,
  SectorPerformance,
  SignalStock,
  TriggerReviewResponse,
  WatchlistChartResponse,
  WatchlistStock,
} from './types'

const API_BASE = '/api/v1/stock'

/** 抛出的错误类型。 */
export class StockApiError extends Error {
  /** HTTP 状态码（404 / 409 / 503 / ...）。 */
  public readonly status: number
  /** 业务错误码（如 CORRELATION_NOT_READY / CORRELATION_WEEKLY_ONLY）。 */
  public readonly code: string | undefined

  constructor(message: string, status: number, code?: string) {
    super(message)
    this.name = 'StockApiError'
    this.status = status
    this.code = code
  }
}

function authClient(): AuthClient {
  return new AuthClient()
}

function jsonHeaders(): HeadersInit {
  return { 'Content-Type': 'application/json' }
}

/** 从 fetch Response 提取业务错误码；非 OK 抛 StockApiError。 */
async function raiseOnError(res: Response, fallback: string): Promise<void> {
  if (res.ok) return
  let code: string | undefined
  let message: string | undefined
  try {
    const data = (await res.json()) as {
      code?: string
      message?: string
      detail?: { code?: string; message?: string } | string
    }
    if (typeof data.detail === 'object' && data.detail !== null) {
      code = data.detail.code
      message = data.detail.message
    } else if (typeof data.detail === 'string') {
      message = data.detail
    } else {
      code = data.code
      message = data.message
    }
  } catch {
    /* ignore parse errors */
  }
  throw new StockApiError(message ?? fallback, res.status, code)
}

async function getJson<T>(path: string, fallback: string): Promise<T> {
  const res = await authClient().request(path)
  await raiseOnError(res, fallback)
  return (await res.json()) as T
}

async function postJson<T>(
  path: string,
  body: unknown,
  fallback: string,
): Promise<T> {
  const res = await authClient().request(path, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(body ?? {}),
  })
  await raiseOnError(res, fallback)
  return (await res.json()) as T
}

/** 原始 fetch 调用——给 ReviewTrigger 轮询使用，让组件能识别 404。 */
async function getRaw(path: string): Promise<Response> {
  return authClient().request(path)
}

export const stockApi = {
  /** 大盘快照（带 trade_date 查询参数）。 */
  getMarketSnapshot: (tradeDate: string): Promise<MarketSnapshot> =>
    getJson<MarketSnapshot>(
      `${API_BASE}/market/snapshot?trade_date=${tradeDate}`,
      '获取大盘快照失败',
    ),

  /** 情绪多日曲线（end_date + days）。 */
  getEmotionChart: (endDate: string, days: number): Promise<EmotionChartResponse> =>
    getJson<EmotionChartResponse>(
      `${API_BASE}/charts/emotion?end_date=${endDate}&days=${days}`,
      '获取情绪曲线失败',
    ),

  /** 板块多日曲线（end_date + days）。 */
  getSectorChart: (endDate: string, days: number): Promise<SectorChartResponse> =>
    getJson<SectorChartResponse>(
      `${API_BASE}/charts/sector?end_date=${endDate}&days=${days}`,
      '获取板块轮动失败',
    ),

  /** 观察池多日趋势。 */
  getWatchlistChart: (endDate: string, days: number): Promise<WatchlistChartResponse> =>
    getJson<WatchlistChartResponse>(
      `${API_BASE}/charts/watchlist?end_date=${endDate}&days=${days}`,
      '获取观察池趋势失败',
    ),

  /** 当前观察池。 */
  getWatchlist: (): Promise<{ items: WatchlistStock[] }> =>
    getJson<{ items: WatchlistStock[] }>(`${API_BASE}/watchlist`, '获取观察池失败'),

  /** 入池/出池观察池。 */
  postWatchlistAction: (req: {
    action: 'add' | 'remove'
    stock_code: string
    stock_name?: string
    category?: number
    notes?: string
  }): Promise<{ status: string; stock_code: string }> =>
    postJson(`${API_BASE}/watchlist`, req, '操作观察池失败'),

  /** 新信号股（按交易日）。 */
  getSignals: (tradeDate: string): Promise<{ items: SignalStock[] }> =>
    getJson<{ items: SignalStock[] }>(
      `${API_BASE}/signals?trade_date=${tradeDate}`,
      '获取新信号失败',
    ),

  /** 板块表现（按交易日）。 */
  getSectors: (tradeDate: string): Promise<{ items: SectorPerformance[] }> =>
    getJson<{ items: SectorPerformance[] }>(
      `${API_BASE}/sectors?trade_date=${tradeDate}`,
      '获取板块表现失败',
    ),

  /** 板块龙头（按板块名）。 */
  getSectorLeaders: (sectorName: string): Promise<{ items: SectorLeader[] }> =>
    getJson<{ items: SectorLeader[] }>(
      `${API_BASE}/sector-leaders?sector_name=${encodeURIComponent(sectorName)}`,
      '获取板块龙头失败',
    ),

  /** 涨停股池（按交易日）。 */
  getLimitStocks: (tradeDate: string): Promise<{ items: LimitStock[] }> =>
    getJson<{ items: LimitStock[] }>(
      `${API_BASE}/limit-stocks?trade_date=${tradeDate}`,
      '获取涨停股池失败',
    ),

  /** 触发复盘（异步任务）。 */
  triggerReview: (tradeDate: string): Promise<TriggerReviewResponse> =>
    postJson<TriggerReviewResponse>(
      `${API_BASE}/review`,
      { trade_date: tradeDate },
      '触发复盘失败',
    ),

  /** 查询复盘任务状态——返回原始 Response 让调用方识别 404。 */
  getReviewTaskRaw: (taskId: string): Promise<Response> =>
    getRaw(`${API_BASE}/review/tasks/${taskId}`),

  /** 查询复盘任务状态（标准化）。 */
  getReviewTask: async (taskId: string): Promise<ReviewTaskStatus> => {
    const res = await getRaw(`${API_BASE}/review/tasks/${taskId}`)
    await raiseOnError(res, '查询复盘任务失败')
    return (await res.json()) as ReviewTaskStatus
  },

  /** 复盘文列表（仅本人）。 */
  listReports: (limit = 20): Promise<{ items: ReviewReport[] }> =>
    getJson<{ items: ReviewReport[] }>(
      `${API_BASE}/reports?limit=${limit}`,
      '获取复盘文列表失败',
    ),

  /** 复盘文详情。 */
  getReport: (reportId: string): Promise<ReviewReport> =>
    getJson<ReviewReport>(`${API_BASE}/reports/${reportId}`, '获取复盘文失败'),

  /** 庄股/抱团股识别（周复盘）。 */
  getCorrelation: (
    endDate: string,
    days = 7,
  ): Promise<CorrelationResult> =>
    getJson<CorrelationResult>(
      `${API_BASE}/correlation?end_date=${endDate}&days=${days}`,
      '获取庄股/抱团识别失败',
    ),

  /** 管理员手动触发抓取/历史回填。 */
  adminRefresh: (range?: {
    start_date?: string
    end_date?: string
  }): Promise<{ refreshed: number }> =>
    postJson<{ refreshed: number }>(
      `${API_BASE}/admin/refresh`,
      range ?? {},
      '管理员刷新失败',
    ),
}
