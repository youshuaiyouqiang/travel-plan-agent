/**
 * Task 3 travel 领域 API 客户端 — 与 ``/api/v1/itineraries/*``、``/api/v1/travel/*``、
 * ``/api/v1/share/*``、``/api/v1/geocode/*`` 端点交互。
 *
 * 设计要点（来源：plans/2026-07-17-academic-frontend-quality.md Task 3）：
 * - 使用 ``features/auth/client.ts`` 共享 cookie + CSRF 流程，不再向 localStorage 持久化 token
 * - 不接受/不发送客户端 ``user_id``：用户身份只能从服务端认证上下文取得
 * - 仅迁移原有 travel 相关函数；行为与原 ``utils/api.ts`` 保持一致
 * - 不修改 ``features/news/api.ts``；新闻相关 API 由新闻计划维护
 */
import { AuthClient } from '../auth/client'

const API_BASE = '/api/v1'

// 每次调用都构造 AuthClient，使其引用当前 ``globalThis.fetch``。
function authClient(): AuthClient {
  return new AuthClient()
}

function jsonHeaders(): HeadersInit {
  return { 'Content-Type': 'application/json' }
}

// ==================== 行程（itineraries） ====================

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

// ==================== 分享 ====================

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

// ==================== 地理编码 ====================

export interface GeocodeResult {
  address: string
  lng: number | null
  lat: number | null
  formatted: string
}

const AMAP_KEY = import.meta.env.VITE_AMAP_KEY || ''

const INTERNATIONAL_DESTINATIONS = new Set([
  '东京', '大阪', '京都', '名古屋', '札幌', '福冈', '冲绳', '那霸', '横滨', '神户',
  '首尔', '釜山', '济州', '仁川',
  '曼谷', '清迈', '普吉', '芭提雅',
  '新加坡',
  '吉隆坡', '槟城',
  '河内', '胡志明', '岘港', '芽庄',
  '巴厘岛', '雅加达', '泗水',
  '巴黎', '伦敦', '罗马', '柏林', '马德里', '巴塞罗那', '阿姆斯特丹', '布拉格',
  '维也纳', '威尼斯', '佛罗伦萨', '米兰', '慕尼黑', '苏黎世', '日内瓦',
  '纽约', '洛杉矶', '旧金山', '芝加哥', '华盛顿', '拉斯维加斯', '夏威夷', '西雅图',
  '波士顿', '迈阿密', '檀香山',
  '悉尼', '墨尔本', '奥克兰', '布里斯班',
  '迪拜', '开罗', '伊斯坦布尔',
  '莫斯科', '圣彼得堡',
  '多伦多', '温哥华', '蒙特利尔',
  '墨西哥城', '坎昆',
  '里约', '布宜诺斯艾利斯', '利马',
  '开普敦', '内罗毕',
])

function isInternationalDestination(city?: string): boolean {
  if (!city) return false
  const trimmed = city.trim()
  if (INTERNATIONAL_DESTINATIONS.has(trimmed)) return true
  if (/^[A-Za-z\s]+$/.test(trimmed)) return true
  return false
}

function cleanAddress(raw: string): string {
  let addr = raw.replace(/[/\\|、，,]/gu, ' ').replace(/\s+/g, ' ').trim()
  addr = addr.replace(/附近$/, '').trim()
  return addr
}

const INTL_COORDS: Record<string, [number, number]> = {
  '东京': [139.6917, 35.6895], '大阪': [135.5022, 34.6937], '京都': [135.7681, 35.0116],
  '名古屋': [136.9066, 35.1815], '札幌': [141.3469, 43.0621], '福冈': [130.4017, 33.5904],
  '冲绳': [127.6792, 26.3344], '那霸': [127.6792, 26.3344], '横滨': [139.6380, 35.4437],
  '神户': [135.1955, 34.6901], '奈良': [135.8048, 34.6851], '箱根': [139.1071, 35.2323],
  '富士山': [138.7274, 35.3606], '东京塔': [139.7454, 35.6586], '浅草寺': [139.7968, 35.7148],
  '银座': [139.7639, 35.6717], '涩谷': [139.7016, 35.6580], '新宿': [139.7005, 35.6897],
  '秋叶原': [139.7733, 35.7023], '台场': [139.7751, 35.6267], '上野': [139.7753, 35.7146],
  '池袋': [139.7110, 35.7295], '六本木': [139.7292, 35.6628], '原宿': [139.7021, 35.6702],
  '大阪城': [135.5258, 34.6873], '道顿堀': [135.5012, 34.6686], '心斋桥': [135.5010, 34.6719],
  '清水寺': [135.7850, 34.9949], '金阁寺': [135.7292, 35.0394], '伏见稻荷': [135.7732, 34.9671],
  '首尔': [126.9780, 37.5665], '釜山': [129.0756, 35.1796], '济州': [126.5313, 33.4996],
  '仁川': [126.7052, 37.4563], '明洞': [126.9840, 37.5636], '景福宫': [126.9769, 37.5796],
  '曼谷': [100.5018, 13.7563], '清迈': [98.9853, 18.7883], '普吉': [98.3923, 7.8804],
  '芭提雅': [100.8825, 12.9236], '新加坡': [103.8198, 1.3521], '圣淘沙': [103.8303, 1.2494],
  '滨海湾': [103.8598, 1.2816], '吉隆坡': [101.6869, 3.1390], '槟城': [100.3319, 5.4164],
  '双子塔': [101.6841, 3.1579], '河内': [105.8342, 21.0278], '胡志明': [106.6297, 10.8231],
  '岘港': [108.2208, 16.0544], '芽庄': [109.1943, 12.2388], '巴厘岛': [115.1889, -8.4095],
  '雅加达': [106.8456, -6.2088], '库塔': [115.1664, -8.7180], '乌布': [115.2588, -8.5069],
  '巴黎': [2.3522, 48.8566], '伦敦': [-0.1276, 51.5074], '罗马': [12.4964, 41.9028],
  '柏林': [13.4050, 52.5200], '马德里': [-3.7038, 40.4168], '巴塞罗那': [2.1734, 41.3851],
  '阿姆斯特丹': [4.9041, 52.3676], '布拉格': [14.4378, 50.0755], '维也纳': [16.3738, 48.2082],
  '威尼斯': [12.3155, 45.4408], '佛罗伦萨': [11.2558, 43.7696], '米兰': [9.1900, 45.4642],
  '慕尼黑': [11.5820, 48.1351], '苏黎世': [8.5417, 47.3769], '日内瓦': [6.1457, 46.2022],
  '埃菲尔铁塔': [2.2945, 48.8584], '卢浮宫': [2.3376, 48.8606], '凯旋门': [2.2950, 48.8738],
  '大本钟': [-0.1246, 51.5007], '白金汉宫': [-0.1416, 51.5015], '大英博物馆': [-0.1270, 51.5194],
  '伦敦眼': [-0.1195, 51.5033], '罗马斗兽场': [12.4922, 41.8902], '圣彼得大教堂': [12.4534, 41.9022],
  '纽约': [-74.0060, 40.7128], '洛杉矶': [-118.2437, 34.0522], '旧金山': [-122.4194, 37.7749],
  '芝加哥': [-87.6298, 41.8781], '华盛顿': [-77.0369, 38.9072], '拉斯维加斯': [-115.1398, 36.1699],
  '夏威夷': [-157.8583, 21.3069], '西雅图': [-122.3321, 47.6062], '波士顿': [-71.0589, 42.3601],
  '迈阿密': [-80.1918, 25.7617], '檀香山': [-157.8583, 21.3069],
  '时代广场': [-73.9857, 40.7580], '自由女神像': [-74.0445, 40.6892],
  '中央公园': [-73.9654, 40.7829], '帝国大厦': [-73.9857, 40.7484],
  '金门大桥': [-122.4782, 37.8199], '好莱坞': [-118.3267, 34.0980],
  '悉尼': [151.2093, -33.8688], '墨尔本': [144.9631, -37.8136], '奥克兰': [174.7633, -36.8485],
  '布里斯班': [153.0251, -27.4698], '悉尼歌剧院': [151.2153, -33.8568],
  '迪拜': [55.2708, 25.2048], '开罗': [31.2357, 30.0444], '伊斯坦布尔': [28.9784, 41.0082],
  '哈利法塔': [55.2744, 25.1972], '金字塔': [31.1325, 29.9761],
  '蓝色清真寺': [28.9767, 41.0054], '圣索菲亚': [28.9805, 41.0086],
  '莫斯科': [37.6173, 55.7558], '圣彼得堡': [30.3351, 59.9343],
  '红场': [37.6213, 55.7539], '克里姆林宫': [37.6175, 55.7520],
  '多伦多': [-79.3832, 43.6532], '温哥华': [-123.1207, 49.2827], '蒙特利尔': [-73.5673, 45.5017],
  '墨西哥城': [-99.1332, 19.4326], '坎昆': [-86.8515, 21.1619],
  '里约': [-43.1729, -22.9068], '布宜诺斯艾利斯': [-58.3816, -34.6037],
  '开普敦': [18.4241, -33.9249], '内罗毕': [36.8219, -1.2921],
}

function lookupIntlCoords(address: string, city?: string): GeocodeResult | null {
  const addr = address.trim()
  const c = city?.trim()
  if (c) {
    const key = `${c}${addr}`
    if (INTL_COORDS[key]) return { address: addr, lng: INTL_COORDS[key][0], lat: INTL_COORDS[key][1], formatted: addr }
  }
  if (INTL_COORDS[addr]) return { address: addr, lng: INTL_COORDS[addr][0], lat: INTL_COORDS[addr][1], formatted: addr }
  for (const [name, coords] of Object.entries(INTL_COORDS)) {
    if (addr.includes(name) || name.includes(addr)) {
      return { address: addr, lng: coords[0], lat: coords[1], formatted: name }
    }
  }
  if (c) {
    for (const [name, coords] of Object.entries(INTL_COORDS)) {
      if (c.includes(name) || name.includes(c)) {
        return { address: addr, lng: coords[0], lat: coords[1], formatted: name }
      }
    }
  }
  return null
}

async function nominatimGeocode(address: string, city?: string): Promise<GeocodeResult | null> {
  try {
    const res = await authClient().request(`${API_BASE}/geocode/intl`, {
      method: 'POST',
      headers: jsonHeaders(),
      body: JSON.stringify({ address, city }),
    })
    if (!res.ok) return null
    const data = await res.json()
    if (data?.lng != null && data?.lat != null) {
      return {
        address,
        lng: data.lng,
        lat: data.lat,
        formatted: data.formatted || '',
      }
    }
  } catch {
    /* nominatim proxy failed */
  }
  try {
    const query = city && !address.includes(city) ? `${city} ${address}` : address
    const params: Record<string, string> = {
      q: query,
      format: 'json',
      limit: '1',
      'accept-language': 'zh',
    }
    const qs = new URLSearchParams(params).toString()
    const res = await fetch(`https://nominatim.openstreetmap.org/search?${qs}`, {
      headers: { 'User-Agent': 'YunheTravelApp/1.0' },
    })
    if (!res.ok) return null
    const data = await res.json()
    if (data?.length > 0) {
      const lat = parseFloat(data[0].lat)
      const lon = parseFloat(data[0].lon)
      if (!isNaN(lat) && !isNaN(lon)) {
        return {
          address,
          lng: lon,
          lat: lat,
          formatted: data[0].display_name || '',
        }
      }
    }
  } catch {
    /* nominatim direct failed */
  }
  return null
}

export async function geocodeAddress(address: string, city?: string): Promise<GeocodeResult | null> {
  if (!address) return null

  const cleaned = cleanAddress(address)
  if (!cleaned) return null

  if (isInternationalDestination(city)) {
    const builtin = lookupIntlCoords(cleaned, city)
    if (builtin) return builtin
    const result = await nominatimGeocode(cleaned, city)
    if (result) return result
  }

  if (!AMAP_KEY) {
    const builtin = lookupIntlCoords(cleaned, city)
    if (builtin) return builtin
    return nominatimGeocode(cleaned, city)
  }

  const tryAmapGeocode = async (addr: string): Promise<GeocodeResult | null> => {
    try {
      const params: Record<string, string> = { address: addr, key: AMAP_KEY, output: 'JSON' }
      if (city) params.city = city
      const qs = new URLSearchParams(params).toString()
      const res = await fetch(`https://restapi.amap.com/v3/geocode/geo?${qs}`)
      if (!res.ok) return null
      const data = await res.json()
      if (data.status === '1' && data.geocodes?.length > 0) {
        const loc = data.geocodes[0].location || ''
        const parts = loc.split(',')
        if (parts.length === 2) {
          return {
            address,
            lng: parseFloat(parts[0]),
            lat: parseFloat(parts[1]),
            formatted: data.geocodes[0].formatted_address || '',
          }
        }
      }
    } catch {
      /* geocode failed */
    }
    return null
  }

  const result = await tryAmapGeocode(cleaned)
  if (result) return result

  if (city && !cleaned.includes(city)) {
    const result2 = await tryAmapGeocode(`${city}${cleaned}`)
    if (result2) return result2
  }

  return nominatimGeocode(cleaned, city)
}

export function isInChina(lng: number, lat: number): boolean {
  return lng >= 73 && lng <= 136 && lat >= 3 && lat <= 54
}

export function buildOsmStaticMapUrl(
  center: { lng: number; lat: number },
  markers: { lng: number; lat: number; label?: string }[],
  size: { w: number; h: number },
  zoom: number = 13
): string {
  const markerParams = markers.map((m, i) => {
    const color = '%236366f1'
    const label = m.label || `${i + 1}`
    return `${m.lat},${m.lng},pushpin${color}${label}`
  }).join('|')
  return `https://staticmap.openstreetmap.de/staticmap.php?center=${center.lat},${center.lng}&zoom=${zoom}&size=${size.w}x${size.h}&markers=${markerParams}`
}

export async function batchGeocode(addresses: string[]): Promise<GeocodeResult[]> {
  const results = await Promise.all(
    addresses.map(async (addr) => {
      const geo = await geocodeAddress(addr)
      return geo || { address: addr, lng: null, lat: null, formatted: '' }
    })
  )
  return results
}

// ==================== 旅行草稿与存档 ====================

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
