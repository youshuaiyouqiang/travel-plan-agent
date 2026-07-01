import { useAuthStore } from '../hooks/useAuthStore'

const API_BASE = '/api'

export interface ChatRequest {
  session_id: string
  user_id?: string
  message: string
  agent_id?: string
}

export interface ChatResponse {
  status: string
  reply: string
}

export interface AuthResponse {
  user_id: string
  username: string
  token: string
}

export interface SessionInfo {
  session_id: string
  title: string
  created_at: string
  updated_at: string
  message_count: number
}

function getToken(): string | null {
  return useAuthStore.getState().token || null
}

function authHeaders(): HeadersInit {
  const token = getToken()
  const headers: HeadersInit = { 'Content-Type': 'application/json' }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  return headers
}

export async function sendMessage(req: ChatRequest, signal?: AbortSignal): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(req),
    signal,
  })
  if (!res.ok) {
    if (res.status === 429) {
      throw new Error('请求过于频繁，请稍后再试')
    }
    if (res.status === 401) {
      throw new Error('AUTH_EXPIRED')
    }
    throw new Error(`请求失败 (${res.status})`)
  }
  return res.json()
}

export interface StreamEvent {
  type: 'status' | 'chunk' | 'done' | 'error' | 'tool_status' | 'route' | 'actions'
  data: any
}

export async function* sendMessageStream(
  req: ChatRequest,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const res = await fetch(`${API_BASE}/chat/stream`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(req),
    signal,
  })
  if (!res.ok) {
    if (res.status === 401) {
      throw new Error('AUTH_EXPIRED')
    }
    throw new Error(`请求失败 (${res.status})`)
  }

  const reader = res.body?.getReader()
  if (!reader) throw new Error('无法读取流式响应')

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed || !trimmed.startsWith('data: ')) continue
      const jsonStr = trimmed.slice(6)
      try {
        const event: StreamEvent = JSON.parse(jsonStr)
        yield event
      } catch {
        // 忽略解析失败的行
      }
    }
  }

  // 处理剩余 buffer
  if (buffer.trim()) {
    const trimmed = buffer.trim()
    if (trimmed.startsWith('data: ')) {
      try {
        const event: StreamEvent = JSON.parse(trimmed.slice(6))
        yield event
      } catch {
        // 忽略
      }
    }
  }
}

export async function register(username: string, password: string): Promise<AuthResponse> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })
  } catch {
    throw new Error('无法连接到服务器，请检查网络')
  }
  const data = await res.json().catch(() => ({ detail: '服务器响应异常' }))
  if (!res.ok) {
    throw new Error(data.detail || '注册失败')
  }
  return data
}

export async function login(username: string, password: string): Promise<AuthResponse> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })
  } catch {
    throw new Error('无法连接到服务器，请检查网络')
  }
  const data = await res.json().catch(() => ({ detail: '服务器响应异常' }))
  if (!res.ok) {
    throw new Error(data.detail || '登录失败')
  }
  return data
}

export async function listSessions(): Promise<SessionInfo[]> {
  const res = await fetch(`${API_BASE}/sessions`, {
    headers: authHeaders(),
  })
  if (!res.ok) {
    throw new Error('获取会话列表失败')
  }
  const data = await res.json()
  return data.sessions || []
}

export async function createSession(): Promise<{ session_id: string; user_id: string }> {
  const res = await fetch(`${API_BASE}/sessions`, {
    method: 'POST',
    headers: authHeaders(),
  })
  if (!res.ok) {
    throw new Error('创建会话失败')
  }
  return res.json()
}

export async function deleteSession(sessionId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}`, {
    method: 'DELETE',
    headers: authHeaders(),
  })
  if (!res.ok) {
    throw new Error('删除会话失败')
  }
}

export interface TrendingItem {
  title: string
  tag: string
  summary: string
  content?: string
  img?: string
  hotScore?: string
  hotChange?: string
}

export async function getTrending(refresh: boolean = false): Promise<TrendingItem[]> {
  try {
    const url = refresh ? `${API_BASE}/trending?refresh=true` : `${API_BASE}/trending`
    const res = await fetch(url)
    if (!res.ok) return []
    const data = await res.json()
    return data.items || []
  } catch {
    return []
  }
}

export async function getSessionMessages(sessionId: string): Promise<any[]> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/messages`, {
    headers: authHeaders(),
  })
  if (!res.ok) {
    throw new Error('获取消息失败')
  }
  const data = await res.json()
  return data.messages || []
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
  actual_cost: number
  tips: string
  checked_in: boolean
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
  days?: any[]
}): Promise<ItineraryData> {
  const res = await fetch(`${API_BASE}/itineraries`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || '创建行程失败')
  }
  return res.json()
}

export async function listItineraries(): Promise<ItineraryListItem[]> {
  const res = await fetch(`${API_BASE}/itineraries`, {
    headers: authHeaders(),
  })
  if (!res.ok) {
    throw new Error('获取行程列表失败')
  }
  const data = await res.json()
  return data.itineraries || []
}

export async function getItinerary(itineraryId: string): Promise<ItineraryData> {
  const res = await fetch(`${API_BASE}/itineraries/${itineraryId}`, {
    headers: authHeaders(),
  })
  if (!res.ok) {
    throw new Error('获取行程详情失败')
  }
  return res.json()
}

export async function updateItinerary(itineraryId: string, data: Record<string, any>): Promise<ItineraryData> {
  const res = await fetch(`${API_BASE}/itineraries/${itineraryId}`, {
    method: 'PUT',
    headers: authHeaders(),
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    throw new Error('更新行程失败')
  }
  return res.json()
}

export async function deleteItinerary(itineraryId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/itineraries/${itineraryId}`, {
    method: 'DELETE',
    headers: authHeaders(),
  })
  if (!res.ok) {
    throw new Error('删除行程失败')
  }
}

export async function checkInActivity(
  itineraryId: string,
  activityId: number,
  checkedIn: boolean = true,
): Promise<ActivityData> {
  const res = await fetch(
    `${API_BASE}/itineraries/${itineraryId}/activities/${activityId}/checkin`,
    {
      method: 'PATCH',
      headers: authHeaders(),
      body: JSON.stringify({ checked_in: checkedIn }),
    },
  )
  if (!res.ok) {
    throw new Error('打卡操作失败')
  }
  return res.json()
}

export async function deleteActivity(
  itineraryId: string,
  activityId: number,
): Promise<void> {
  const res = await fetch(
    `${API_BASE}/itineraries/${itineraryId}/activities/${activityId}`,
    {
      method: 'DELETE',
      headers: authHeaders(),
    },
  )
  if (!res.ok) {
    throw new Error('删除活动失败')
  }
}

export interface MemoryItem {
  id: number
  category: string
  category_label: string
  content: string
  experience_tag?: string
  extraction_count: number
  last_accessed_at: string
  created_at: string
}

export interface MemorySummary {
  total_ltm: number
  total_stm: number
  preferences: number
  facts: number
  experiences: number
}

export interface MemoriesResponse {
  long_term: MemoryItem[]
  short_term: MemoryItem[]
  summary: MemorySummary
}

export async function getMemories(): Promise<MemoriesResponse> {
  const res = await fetch(`${API_BASE}/memories`, {
    headers: authHeaders(),
  })
  if (!res.ok) {
    throw new Error('获取记忆失败')
  }
  return res.json()
}

export async function deleteMemory(memoryType: string, memoryId: number): Promise<void> {
  const res = await fetch(`${API_BASE}/memories/${memoryType}/${memoryId}`, {
    method: 'DELETE',
    headers: authHeaders(),
  })
  if (!res.ok) {
    throw new Error('删除记忆失败')
  }
}

export async function updateActivityCost(
  itineraryId: string,
  activityId: number,
  actualCost: number,
): Promise<ActivityData> {
  const res = await fetch(
    `${API_BASE}/itineraries/${itineraryId}/activities/${activityId}/cost`,
    {
      method: 'PATCH',
      headers: authHeaders(),
      body: JSON.stringify({ actual_cost: actualCost }),
    },
  )
  if (!res.ok) {
    throw new Error('更新花费失败')
  }
  return res.json()
}

export interface ExpenseDaySummary {
  day_index: number
  date: string
  title: string
  budget: number
  actual: number
  activities: {
    id: number
    title: string
    budget: number
    actual: number
    checked_in: boolean
  }[]
}

export interface ExpenseSummary {
  itinerary_id: string
  title: string
  budget_text: string
  budget_total: number
  actual_total: number
  remaining: number
  days: ExpenseDaySummary[]
}

export async function getExpenseSummary(itineraryId: string): Promise<ExpenseSummary> {
  const res = await fetch(`${API_BASE}/itineraries/${itineraryId}/expense-summary`, {
    headers: authHeaders(),
  })
  if (!res.ok) {
    throw new Error('获取花费统计失败')
  }
  return res.json()
}

export async function createShareLink(itineraryId: string): Promise<{ token: string; itinerary_id: string }> {
  const res = await fetch(`${API_BASE}/itineraries/${itineraryId}/share`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({}),
  })
  if (!res.ok) {
    throw new Error('创建分享链接失败')
  }
  return res.json()
}

export async function listShareLinks(itineraryId: string): Promise<{ shares: { token: string; itinerary_id: string; view_count: number; created_at: string }[] }> {
  const res = await fetch(`${API_BASE}/itineraries/${itineraryId}/shares`, {
    headers: authHeaders(),
  })
  if (!res.ok) {
    throw new Error('获取分享列表失败')
  }
  return res.json()
}

export async function deleteShareLink(itineraryId: string, token: string): Promise<void> {
  const res = await fetch(`${API_BASE}/itineraries/${itineraryId}/shares/${token}`, {
    method: 'DELETE',
    headers: authHeaders(),
  })
  if (!res.ok) {
    throw new Error('删除分享链接失败')
  }
}

export async function getSharedItinerary(token: string): Promise<{ itinerary: ItineraryData; share_info: { view_count: number; created_at: string } }> {
  const res = await fetch(`${API_BASE}/shared/${token}`)
  if (!res.ok) {
    throw new Error('获取分享行程失败')
  }
  return res.json()
}

export interface CompareItineraryItem {
  id: string
  title: string
  destination: string
  start_date: string
  end_date: string
  budget_text: string
  budget_total: number
  actual_total: number
  days_count: number
  activities_count: number
  days: {
    day_index: number
    date: string
    title: string
    summary: string
    budget: number
    actual: number
    activities: {
      time_slot: string
      title: string
      location: string
      cost: number
      actual_cost: number
    }[]
  }[]
}

export async function compareItineraries(ids: string[]): Promise<{ itineraries: CompareItineraryItem[] }> {
  const res = await fetch(`${API_BASE}/itineraries/compare`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ ids }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || '对比行程失败')
  }
  return res.json()
}

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
  let addr = raw.replace(/[\/\\|、，,]/g, ' ').replace(/\s+/g, ' ').trim()
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
    const res = await fetch('/api/geocode/intl', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
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
      headers: { 'User-Agent': 'ClawTravelApp/1.0' },
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

// ==================== 相册管理 ====================

export interface PhotoData {
  id: number
  itinerary_id: string
  user_id: string
  file_name: string
  file_size: number
  mime_type: string
  description: string
  storage_path: string
  thumbnail_path: string
  day_index: number
  tags: string[]
  ai_description: string
  latitude: number | null
  longitude: number | null
  is_cover: boolean
  created_at: string
}

export interface PhotoListResponse {
  itinerary_id: string
  photos: PhotoData[]
  total: number
  tags: string[]
  cover: PhotoData | null
}

export interface PhotoMapMarker {
  photo_id: number
  latitude: number
  longitude: number
  description: string
  day_index: number
  thumbnail_path: string
}

export async function uploadPhotos(
  itineraryId: string,
  files: File[],
  description: string = '',
  dayIndex: number = 0,
): Promise<{ photos: PhotoData[] }> {
  const formData = new FormData()
  for (const f of files) {
    formData.append('files', f)
  }
  formData.append('description', description)
  formData.append('day_index', String(dayIndex))

  const token = getToken()
  const headers: HeadersInit = {}
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${API_BASE}/itineraries/${itineraryId}/photos`, {
    method: 'POST',
    headers,
    body: formData,
  })
  if (!res.ok) throw new Error(`上传失败 (${res.status})`)
  return res.json()
}

export async function listPhotos(
  itineraryId: string,
  dayIndex?: number,
  tag?: string,
): Promise<PhotoListResponse> {
  const params = new URLSearchParams()
  if (dayIndex && dayIndex > 0) params.set('day_index', String(dayIndex))
  if (tag) params.set('tag', tag)
  const qs = params.toString() ? `?${params.toString()}` : ''
  const res = await fetch(`${API_BASE}/itineraries/${itineraryId}/photos${qs}`, {
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`获取照片失败 (${res.status})`)
  return res.json()
}

export async function deletePhoto(itineraryId: string, photoId: number): Promise<void> {
  const res = await fetch(`${API_BASE}/itineraries/${itineraryId}/photos/${photoId}`, {
    method: 'DELETE',
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`删除失败 (${res.status})`)
}

export async function updatePhoto(
  itineraryId: string,
  photoId: number,
  data: { description?: string; day_index?: number; tags?: string[] },
): Promise<PhotoData> {
  const res = await fetch(`${API_BASE}/itineraries/${itineraryId}/photos/${photoId}`, {
    method: 'PATCH',
    headers: authHeaders(),
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(`更新失败 (${res.status})`)
  return res.json()
}

export async function setPhotoCover(itineraryId: string, photoId: number): Promise<PhotoData> {
  const res = await fetch(`${API_BASE}/itineraries/${itineraryId}/photos/${photoId}/cover`, {
    method: 'POST',
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`设置封面失败 (${res.status})`)
  return res.json()
}

export async function getPhotoMapMarkers(itineraryId: string): Promise<{ itinerary_id: string; markers: PhotoMapMarker[] }> {
  const res = await fetch(`${API_BASE}/itineraries/${itineraryId}/photos/map`, {
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`获取地图标记失败 (${res.status})`)
  return res.json()
}

export async function generateTravelogue(itineraryId: string): Promise<{ itinerary_id: string; content: string }> {
  const res = await fetch(`${API_BASE}/itineraries/${itineraryId}/travelogue`, {
    method: 'POST',
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`生成游记失败 (${res.status})`)
  return res.json()
}

export function getAlbumImageUrl(path: string): string {
  const token = getToken()
  // 兼容旧数据：如果 path 以 album/ 开头，去掉前缀（路由已包含 /album/）
  const cleanPath = path.startsWith('album/') ? path.slice(6) : path
  const base = `${API_BASE}/album/${cleanPath}`
  return token ? `${base}?token=${encodeURIComponent(token)}` : base
}

// ===== Agent 中心 API =====

// 类型定义（字段与后端 AgentConfig 完全对齐）
export interface SkillInfo {
  name: string
  display_name: string
  description: string
  default_prompt: string
  requires_env: string[]
  env_configured: boolean
  icon: string
}

export interface AgentInfo {
  id: string
  name: string
  description: string
  icon: string
  source: 'builtin' | 'custom'    // 与后端 AgentConfig.source 对齐
  skills?: string[]
  is_public?: boolean
  created_at?: string
  system_prompt?: string
  welcome_message?: string
  temperature?: number
  user_id?: string
}

// 获取 skill 列表
export async function fetchSkills(): Promise<SkillInfo[]> {
  const res = await fetch(`${API_BASE}/skills`, { headers: authHeaders() })
  if (!res.ok) throw new Error('获取 Skill 列表失败')
  const data = await res.json()
  return data.skills
}

// 获取智能体列表
export async function fetchAgents(): Promise<{
  builtin: AgentInfo[]
  custom: AgentInfo[]
  public: AgentInfo[]
}> {
  const res = await fetch(`${API_BASE}/agents`, { headers: authHeaders() })
  if (!res.ok) throw new Error('获取智能体列表失败')
  return res.json()
}

// 创建自定义智能体
export async function createCustomAgent(data: Partial<AgentInfo>): Promise<AgentInfo> {
  const res = await fetch(`${API_BASE}/agents/custom`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || '创建智能体失败')
  }
  return res.json()
}

// 更新自定义智能体
export async function updateCustomAgent(agentId: string, data: Partial<AgentInfo>): Promise<AgentInfo> {
  const res = await fetch(`${API_BASE}/agents/custom/${agentId}`, {
    method: 'PUT',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || '更新智能体失败')
  }
  return res.json()
}

// 删除自定义智能体
export async function deleteCustomAgent(agentId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/agents/custom/${agentId}`, {
    method: 'DELETE',
    headers: authHeaders(),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || '删除智能体失败')
  }
}
