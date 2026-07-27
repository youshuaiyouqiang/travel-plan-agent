/**
 * 旅行草稿与存档 API 客户端 — 与 ``/api/v1/travel/drafts/*`` 和
 * ``/api/v1/travel/archives/*`` 端点交互。
 *
 * P5.4 从 ``features/travel/api.ts`` 拆出。所有请求统一走
 * ``features/auth/client.ts`` 的 cookie + CSRF 流程。
 */
import { AuthClient } from '../auth/client'

const API_BASE = '/api/v1'

function authClient(): AuthClient {
  return new AuthClient()
}

function jsonHeaders(): HeadersInit {
  return { 'Content-Type': 'application/json' }
}

export interface TravelActivityData {
  id: string
  title: string
  time_slot?: string
  location?: string
  note?: string
}

export interface TravelDayData {
  day_index: number
  date?: string
  title?: string
  activities: TravelActivityData[]
}

export interface TravelPlanData {
  title?: string
  destination?: string
  days?: TravelDayData[]
}

export interface TravelDraftData {
  id: string
  user_id: string
  session_id: string
  plan: TravelPlanData
  manual_edit_fields: string[]
  is_read_only: boolean
  source_archive_id: string | null
  created_at?: string
  updated_at?: string
}

export interface TravelArchiveData {
  id: string
  user_id: string
  source_draft_id: string
  confirmed_at: string
  plan: TravelPlanData
}

interface UnifiedResponse<T> {
  code: number
  message: string
  data: T
}

async function parseUnified<T>(res: Response, fallbackMsg: string): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.message || fallbackMsg)
  }
  const payload = (await res.json()) as UnifiedResponse<T>
  return payload.data
}

export async function createTravelDraft(
  sessionId: string,
  plan: TravelPlanData,
): Promise<TravelDraftData> {
  const res = await authClient().request(`${API_BASE}/travel/drafts`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify({ session_id: sessionId, plan }),
  })
  return parseUnified<TravelDraftData>(res, '创建旅行草稿失败')
}

export async function getTravelDraft(draftId: string): Promise<TravelDraftData> {
  const res = await authClient().request(`${API_BASE}/travel/drafts/${draftId}`)
  return parseUnified<TravelDraftData>(res, '加载旅行草稿失败')
}

export async function patchTravelActivity(
  draftId: string,
  activityId: string,
  changes: { title?: string; time_slot?: string; location?: string; note?: string },
): Promise<TravelDraftData> {
  const res = await authClient().request(
    `${API_BASE}/travel/drafts/${draftId}/activities/${activityId}`,
    {
      method: 'PATCH',
      headers: jsonHeaders(),
      body: JSON.stringify(changes),
    },
  )
  return parseUnified<TravelDraftData>(res, '保存修改失败')
}

export async function confirmTravelDraft(draftId: string): Promise<TravelArchiveData> {
  const res = await authClient().request(`${API_BASE}/travel/drafts/${draftId}/confirm`, {
    method: 'POST',
  })
  return parseUnified<TravelArchiveData>(res, '确认行程失败')
}

export async function getTravelArchive(archiveId: string): Promise<TravelArchiveData> {
  const res = await authClient().request(`${API_BASE}/travel/archives/${archiveId}`)
  return parseUnified<TravelArchiveData>(res, '加载存档失败')
}

export async function startDraftFromArchive(archiveId: string): Promise<TravelDraftData> {
  const res = await authClient().request(`${API_BASE}/travel/archives/${archiveId}/new-draft`, {
    method: 'POST',
  })
  return parseUnified<TravelDraftData>(res, '基于存档创建草稿失败')
}
