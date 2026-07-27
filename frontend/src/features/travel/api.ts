/**
 * travel 领域统一导出入口。
 *
 * P5.4 将原 ``features/travel/api.ts``（541 行）按职责拆分为三个子模块：
 * - ``./itinerary`` — 行程 CRUD 与分享（``/api/v1/itineraries/*``）
 * - ``./geocode`` — 地理编码与静态地图 URL（高德 / Nominatim / 内置坐标表）
 * - ``./draft-archive`` — 旅行草稿与存档（``/api/v1/travel/drafts|archives``）
 *
 * 本文件仅做重新导出，保持现有调用方的导入路径不变。新增代码应直接从
 * 具体子模块导入，避免过度集中。
 *
 * 设计要点：
 * - 所有请求统一走 ``features/auth/client.ts`` 的 cookie + CSRF 流程
 * - 不接受/不发送客户端 ``user_id``：用户身份只能从服务端认证上下文取得
 * - 不修改 ``features/news/api.ts``；新闻相关 API 由新闻计划维护
 */

// ==================== 行程（itineraries） ====================
export type {
  ActivityData,
  DayPlanData,
  ItineraryData,
  ItineraryListItem,
} from './itinerary'
export {
  createItinerary,
  listItineraries,
  getItinerary,
  updateItinerary,
  deleteItinerary,
  deleteActivity,
  createShareLink,
  getSharedItinerary,
} from './itinerary'

// ==================== 地理编码（geocode） ====================
export type { GeocodeResult } from './geocode'
export {
  geocodeAddress,
  isInChina,
  buildOsmStaticMapUrl,
  batchGeocode,
} from './geocode'

// ==================== 旅行草稿与存档（draft-archive） ====================
export type {
  TravelActivityData,
  TravelDayData,
  TravelPlanData,
  TravelDraftData,
  TravelArchiveData,
} from './draft-archive'
export {
  createTravelDraft,
  getTravelDraft,
  patchTravelActivity,
  confirmTravelDraft,
  getTravelArchive,
  startDraftFromArchive,
} from './draft-archive'
