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

/** 来源评分模式：区分内置白名单与 AI 评分候选。 */
export type ScoringMode = 'builtin_whitelist' | 'ai_candidate'

/** 6 维度子分明细（仅 ai_candidate 模式有意义）。 */
export type SourceSubscores = {
  publisher_authority?: number
  domain_brand?: number
  topic_relevance?: number
  editorial_standard?: number
  accessibility?: number
  risk_signals?: number
}

export interface NewsSource {
  id: string
  name: string
  domain: string
  tier: string
  status: SourceStatus
  scoring_mode: ScoringMode
  ai_score: number | null
  ai_reason: string
  ai_subscores: SourceSubscores
  created_at: string
  updated_at: string
}

export interface NewsSourceAudit {
  id: string
  source_id: string
  /** 来源显示名（JOIN 来自 news_sources.name）。 */
  source_name: string
  /** 来源域名（JOIN 来自 news_sources.domain），审核项的"主键"信息。 */
  source_domain: string
  admin_id: string
  previous_status: string
  decision: SourceStatus
  reason: string
  created_at: string
}

/** 系统初始化事件（替代"初始化内置来源"占位审计行）。 */
export interface NewsSourceInit {
  id: string
  source_id: string
  domain: string
  tier: string
  scoring_mode: ScoringMode
  init_at: string
  init_reason: string
}

export type EvidenceCardStatus = 'verified' | 'conflicted'

export interface EvidenceCard {
  /** 来源记录 ID；用于跳转到该来源的人工审核页（/admin/news?source=xxx）。 */
  source_id: string
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

/** GET /admin/news/source-inits — 系统初始化事件列表。 */
export async function listNewsSourceInits(): Promise<NewsSourceInit[]> {
  const res = await authClient().request(`${ADMIN_BASE}/source-inits`)
  if (res.status === 403) throw new Error('FORBIDDEN')
  if (!res.ok) throw new Error('获取来源初始化事件失败')
  const data = await res.json()
  return (data?.items ?? []) as NewsSourceInit[]
}

/** POST /admin/news/sources/register-builtin — 管理员注册内置白名单。 */
export async function registerBuiltinSource(req: {
  domain: string
  name: string
  tier: 'mainstream' | 'aggregator' | 'official'
  init_reason?: string
}): Promise<NewsSource> {
  const res = await authClient().request(
    `${ADMIN_BASE}/sources/register-builtin`,
    {
      method: 'POST',
      headers: jsonHeaders(),
      body: JSON.stringify(req),
    },
  )
  if (res.status === 403) throw new Error('FORBIDDEN')
  if (!res.ok) throw new Error('注册内置白名单失败')
  return (await res.json()) as NewsSource
}
