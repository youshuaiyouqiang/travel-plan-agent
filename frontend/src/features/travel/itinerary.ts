/**
 * 行程 API 客户端 — 与 ``/api/v1/itineraries/*`` 端点交互。
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

export interface ActivityData {
  id: number
  day_id: number
  activity_index: number
  time_slot: string
  title: string
  location: string
  description: string
  image_url: string
  cost: number
  tips: string
}

export interface DayPlanData {
  id: number
  itinerary_id: string
  day_index: number
  date: string
  title: string
  summary: string
  activities: ActivityData[]
}

export interface ItineraryData {
  id: string
  user_id: string
  session_id: string
  title: string
  destination: string
  start_date: string
  end_date: string
  budget: string
  status: string
  created_at: string
  updated_at: string
  days?: DayPlanData[]
}

export interface ItineraryListItem {
  id: string
  user_id: string
  session_id: string
  title: string
  destination: string
  start_date: string
  end_date: string
  budget: string
  status: string
  created_at: string
  updated_at: string
}

export async function createItinerary(data: {
  title: string
  destination: string
  start_date?: string
  end_date?: string
  session_id?: string
  budget?: string
  raw_content?: string
  status?: string
  days?: unknown[]
}): Promise<ItineraryData> {
  const res = await authClient().request(`${API_BASE}/itineraries`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || '创建行程失败')
  }
  return res.json()
}

export async function listItineraries(): Promise<ItineraryListItem[]> {
  const res = await authClient().request(`${API_BASE}/itineraries`)
  if (!res.ok) {
    throw new Error('获取行程列表失败')
  }
  const data = await res.json()
  return data.itineraries || []
}

export async function getItinerary(itineraryId: string): Promise<ItineraryData> {
  const res = await authClient().request(`${API_BASE}/itineraries/${itineraryId}`)
  if (!res.ok) {
    throw new Error('获取行程详情失败')
  }
  return res.json()
}

export async function updateItinerary(
  itineraryId: string,
  data: Record<string, unknown>,
): Promise<ItineraryData> {
  const res = await authClient().request(`${API_BASE}/itineraries/${itineraryId}`, {
    method: 'PUT',
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    throw new Error('更新行程失败')
  }
  return res.json()
}

export async function deleteItinerary(itineraryId: string): Promise<void> {
  const res = await authClient().request(`${API_BASE}/itineraries/${itineraryId}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    throw new Error('删除行程失败')
  }
}

export async function deleteActivity(
  itineraryId: string,
  activityId: number,
): Promise<void> {
  const res = await authClient().request(
    `${API_BASE}/itineraries/${itineraryId}/activities/${activityId}`,
    { method: 'DELETE' },
  )
  if (!res.ok) {
    throw new Error('删除活动失败')
  }
}

export async function createShareLink(
  itineraryId: string,
): Promise<{ token: string; itinerary_id: string }> {
  const res = await authClient().request(`${API_BASE}/itineraries/${itineraryId}/share`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify({}),
  })
  if (!res.ok) {
    throw new Error('创建分享链接失败')
  }
  return res.json()
}

export async function getSharedItinerary(
  token: string,
): Promise<{ itinerary: ItineraryData; share_info: { view_count: number; created_at: string } }> {
  const res = await authClient().request(`${API_BASE}/shared/${token}`)
  if (!res.ok) {
    throw new Error('获取分享行程失败')
  }
  return res.json()
}
