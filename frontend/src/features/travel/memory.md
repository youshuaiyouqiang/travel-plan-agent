# frontend/src/features/travel/ — 模块记忆

## 职责定位
旅行域前端 API：行程 CRUD、分享、地理编码、草稿与存档全流程。

## 关键文件
- `api.ts`：
  - 行程：create/list/get/update/deleteItinerary、deleteActivity。
  - 分享：createShareLink / getSharedItinerary。
  - 地理编码：geocodeAddress / batchGeocode / isInChina / buildOsmStaticMapUrl。
  - 草稿/存档：create/getTravelDraft、patchTravelActivity、confirmTravelDraft、getTravelArchive、startDraftFromArchive。
  - 类型：ActivityData / DayPlanData / ItineraryData / TravelDraftData / TravelArchiveData / GeocodeResult。

## 业务边界要点
- 地理编码：国内用高德（需 `VITE_AMAP_KEY`）；国际用内置坐标表（INTL_COORDS）+ Nominatim 代理；`isInternationalDestination` 按城市名或纯英文判定。
- `manual_edit_fields`、`is_read_only`、`source_archive_id` 由后端权威控制，前端只读展示。
- 统一响应 `{code, message, data}` 由 `parseUnified` 解包。
