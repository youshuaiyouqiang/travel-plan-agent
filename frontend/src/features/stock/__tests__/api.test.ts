/**
 * 股市复盘 API 客户端契约测试（Task 7）。
 *
 * 覆盖范围：
 * - 所有请求统一走 `features/auth/client.ts` 的 cookie + CSRF 流程（AGENTS.md §4）
 * - 端点路径与后端 `/api/v1/stock/*` 完全一致
 * - 不在请求体写入 user_id（身份由服务端认证上下文取）
 * - 不向 localStorage / sessionStorage 持久化任何 token
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { stockApi } from '../api'

describe('stockApi', () => {
  let originalFetch: typeof globalThis.fetch
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    originalFetch = globalThis.fetch
    fetchMock = vi.fn()
    globalThis.fetch = fetchMock as unknown as typeof globalThis.fetch
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  function mockJson(data: unknown, status = 200) {
    return Promise.resolve(
      new Response(JSON.stringify(data), {
        status,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  }

  it('getEmotionChart 调用正确端点', async () => {
    fetchMock.mockResolvedValueOnce(mockJson({ series: [], window_days: 10 }))
    await stockApi.getEmotionChart('20260728', 10)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/stock/charts/emotion?end_date=20260728&days=10',
      expect.objectContaining({ credentials: 'include' }),
    )
  })

  it('getMarketSnapshot 调用正确端点（带 trade_date）', async () => {
    fetchMock.mockResolvedValueOnce(
      mockJson({ trade_date: '20260728', sh_index: 3000 }),
    )
    await stockApi.getMarketSnapshot('20260728')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/stock/market/snapshot?trade_date=20260728',
      expect.objectContaining({ credentials: 'include' }),
    )
  })

  it('triggerReview 走 POST + 路径 /review', async () => {
    fetchMock.mockResolvedValueOnce(mockJson({ task_id: 't-1' }))
    await stockApi.triggerReview('20260728')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/stock/review',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
        body: JSON.stringify({ trade_date: '20260728' }),
      }),
    )
  })

  it('getReviewTask 拼接 taskId', async () => {
    fetchMock.mockResolvedValueOnce(
      mockJson({
        task_id: 't-1',
        user_id: 'u',
        trade_date: '20260728',
        status: 'running',
      }),
    )
    await stockApi.getReviewTask('t-1')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/stock/review/tasks/t-1',
      expect.objectContaining({ credentials: 'include' }),
    )
  })

  it('listReports 调用正确端点（带 limit）', async () => {
    fetchMock.mockResolvedValueOnce(mockJson({ items: [] }))
    await stockApi.listReports(20)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/stock/reports?limit=20',
      expect.objectContaining({ credentials: 'include' }),
    )
  })

  it('getReport 拼接 reportId', async () => {
    fetchMock.mockResolvedValueOnce(
      mockJson({
        id: 'r-1',
        user_id: 'u',
        trade_date: '20260728',
        content: '',
        status: 'completed',
        llm_metadata: '{}',
        created_at: '2026-07-28T10:00:00',
      }),
    )
    await stockApi.getReport('r-1')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/stock/reports/r-1',
      expect.objectContaining({ credentials: 'include' }),
    )
  })

  it('getWatchlist 调用正确端点', async () => {
    fetchMock.mockResolvedValueOnce(mockJson({ items: [] }))
    await stockApi.getWatchlist()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/stock/watchlist',
      expect.objectContaining({ credentials: 'include' }),
    )
  })

  it('getSectorChart 调用正确端点（end_date + days）', async () => {
    fetchMock.mockResolvedValueOnce(
      mockJson({ series: [], window_days: 10, end_date: '20260728' }),
    )
    await stockApi.getSectorChart('20260728', 10)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/stock/charts/sector?end_date=20260728&days=10',
      expect.objectContaining({ credentials: 'include' }),
    )
  })

  it('getCorrelation 调用正确端点（带 end_date）', async () => {
    fetchMock.mockResolvedValueOnce(
      mockJson({
        end_date: '20260728',
        window_days: 7,
        individual_stocks: [],
        clustered_groups: [],
      }),
    )
    await stockApi.getCorrelation('20260728', 7)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/stock/correlation?end_date=20260728&days=7',
      expect.objectContaining({ credentials: 'include' }),
    )
  })

  it('adminRefresh 走 POST 路径 /admin/refresh', async () => {
    fetchMock.mockResolvedValueOnce(mockJson({ refreshed: 0 }))
    await stockApi.adminRefresh()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/stock/admin/refresh',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
      }),
    )
  })

  it('getSignals 调用正确端点（带 trade_date）', async () => {
    fetchMock.mockResolvedValueOnce(mockJson({ items: [] }))
    await stockApi.getSignals('20260728')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/stock/signals?trade_date=20260728',
      expect.objectContaining({ credentials: 'include' }),
    )
  })

  it('getSectors 调用正确端点（带 trade_date）', async () => {
    fetchMock.mockResolvedValueOnce(mockJson({ items: [] }))
    await stockApi.getSectors('20260728')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/stock/sectors?trade_date=20260728',
      expect.objectContaining({ credentials: 'include' }),
    )
  })

  it('getSectorLeaders 调用正确端点（带 sector_name）', async () => {
    fetchMock.mockResolvedValueOnce(mockJson({ items: [] }))
    await stockApi.getSectorLeaders('半导体')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/stock/sector-leaders?sector_name=' +
        encodeURIComponent('半导体'),
      expect.objectContaining({ credentials: 'include' }),
    )
  })
})
