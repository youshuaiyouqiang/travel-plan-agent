/**
 * 新闻功能前端 API 客户端（Task 3）。
 *
 * 设计要点：
 * - P0-1 修复：所有请求统一走 ``features/auth/client.ts`` 的 cookie + CSRF 流程，
 *   不再使用 Bearer token；浏览器不持有长期认证令牌。
 * - 不向 localStorage / sessionStorage 持久化任何 token。
 * - 不接收/不传递新闻全文：HotspotItem / AnalysisSessionResult 仅含标题、来源、URL、摘要、发布时间。
 * - 管理员 API 的授权边界由后端 403 强制；前端不在此处判断角色。
 */
import { AuthClient } from '../auth/client'

const API_BASE = '/api/v1/news'
const ADMIN_BASE = '/api/v1/admin/news'

/** 热点项（后端 NewsItem 序列化结构；不含全文）。 */
export interface HotspotItem {
  id: string
  title: string
  source: string
  url: string
  summary: string
  published_at: string
}

/** 创建研判会话返回的锚点信息；与 HotspotItem 结构一致。 */
export type NewsAnchor = HotspotItem

/** POST /hotspots/{news_id}/analysis-sessions 响应。 */
export interface AnalysisSessionResult {
  session_id: string
  mode: 'news_analysis_locked'
  locked_agent_id: 'news'
  news_id: string
  anchor: NewsAnchor
}

export type SourceStatus =
  | 'pending'
  | 'enabled'
  | 'lead_only'
  | 'rejected'
  | 'blocked'
  | 'needs_review'

export interface NewsSource {
  id: string
  name: string
  domain: string
  tier: string
  status: SourceStatus
  ai_score: number | null
  ai_reason: string
  created_at: string
  updated_at: string
}

export interface NewsSourceAudit {
  id: string
  source_id: string
  admin_id: string
  previous_status: string
  decision: SourceStatus
  reason: string
  created_at: string
}

export type EvidenceCardStatus = 'verified' | 'conflicted'

export interface EvidenceCard {
  source_name: string
  url: string
  claim: string
  status: EvidenceCardStatus
}

export interface UnverifiedLead {
  source_name: string
  url: string
  claim: string
}

function authClient(): AuthClient {
  return new AuthClient()
}

function jsonHeaders(): HeadersInit {
  return { 'Content-Type': 'application/json' }
}

/** GET /hotspots — 只读缓存；不触发外部抓取。 */
export async function getHotspots(): Promise<HotspotItem[]> {
  const res = await authClient().request(`${API_BASE}/hotspots`)
  if (!res.ok) throw new Error('获取热点失败')
  const data = await res.json()
  return (data?.items ?? []) as HotspotItem[]
}

/**
 * POST /hotspots/{news_id}/analysis-sessions — 创建 news_analysis_locked 会话。
 * 锁定 Agent 由后端固定为 "news"，不接受客户端传入。
 */
export async function createAnalysisSession(
  newsId: string,
): Promise<AnalysisSessionResult> {
  const res = await authClient().request(
    `${API_BASE}/hotspots/${encodeURIComponent(newsId)}/analysis-sessions`,
    { method: 'POST' },
  )
  if (res.status === 404) throw new Error('热点不存在或已过期')
  if (!res.ok) throw new Error('创建研判会话失败')
  return (await res.json()) as AnalysisSessionResult
}

/** GET /admin/news/sources — 仅管理员；非管理员返回 403。 */
export async function listNewsSources(): Promise<NewsSource[]> {
  const res = await authClient().request(`${ADMIN_BASE}/sources`)
  if (res.status === 403) throw new Error('FORBIDDEN')
  if (!res.ok) throw new Error('获取新闻来源失败')
  const data = await res.json()
  return (data?.items ?? []) as NewsSource[]
}

/** POST /admin/news/sources/{source_id}/review — 管理员审核来源。 */
export async function reviewNewsSource(
  sourceId: string,
  decision: SourceStatus,
  reason: string,
): Promise<NewsSource> {
  const res = await authClient().request(
    `${ADMIN_BASE}/sources/${encodeURIComponent(sourceId)}/review`,
    {
      method: 'POST',
      headers: jsonHeaders(),
      body: JSON.stringify({ decision, reason }),
    },
  )
  if (res.status === 403) throw new Error('FORBIDDEN')
  if (!res.ok) throw new Error('审核失败')
  return (await res.json()) as NewsSource
}

/** GET /admin/news/source-audits — 审核审计记录列表。 */
export async function listNewsSourceAudits(): Promise<NewsSourceAudit[]> {
  const res = await authClient().request(`${ADMIN_BASE}/source-audits`)
  if (res.status === 403) throw new Error('FORBIDDEN')
  if (!res.ok) throw new Error('获取审计记录失败')
  const data = await res.json()
  return (data?.items ?? []) as NewsSourceAudit[]
}
