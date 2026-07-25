# frontend/src/components/itinerary/ — 模块记忆

## 职责定位
行程概览/存档/分享页的地图与日程可视化组件，依赖 `features/travel/api.ts` 的地理编码。

## 关键文件
- `AmapView.tsx`：Leaflet 通用地图视图（高德 autonavi 瓦片），自定义标点、路径连线、点击回调。
- `MiniMap.tsx`：活动详情抽屉内的单点小地图。
- `ItineraryMap.tsx`：按天批量地理编码并渲染当日地图（折叠、定位计数、错误提示）。
- `SharedMap.tsx`：分享页全行程多日地图（按天不同颜色，无需登录）。
- `DayBlinds.tsx`：按天时间轴日程列表，含分类图标猜测与预算展示。
- `ActivityDetail.tsx`：活动详情底部抽屉——仅展示预算/时间/地点/详情/贴士。

## 业务边界要点
- 地理编码策略：国内走高德，国际走内置坐标表 + Nominatim（见 features/travel/api.ts）。
- 业务红线：不展示打卡、实际花费（actual_cost/checked_in）、相册等已删除功能字段。
