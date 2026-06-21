# Claw API 接口文档

基础地址：`http://localhost:8000`

## 鉴权说明

除标注为「公开」的接口外，所有接口均需在请求头中携带 Token：

```
Authorization: Bearer <token>
```

Token 通过注册或登录接口获取。未携带 Token 或 Token 无效返回 `401`。

---

## 1. 认证模块

### 1.1 用户注册

```
POST /api/auth/register
```

**公开接口，无需鉴权**

请求体：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| username | string | 是 | 用户名，2-32 字符 |
| password | string | 是 | 密码，至少 6 位 |

响应：

```json
{
  "user_id": "ee3d2c304e265393",
  "username": "maptest99",
  "token": "3a3c205da3b2aedd..."
}
```

错误码：

| 状态码 | 说明 |
|--------|------|
| 400 | 用户名长度不符 / 密码过短 / 用户名已存在 |

---

### 1.2 用户登录

```
POST /api/auth/login
```

**公开接口，无需鉴权**

请求体：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| username | string | 是 | 用户名 |
| password | string | 是 | 密码 |

响应：

```json
{
  "user_id": "ee3d2c304e265393",
  "username": "maptest99",
  "token": "3a3c205da3b2aedd..."
}
```

错误码：

| 状态码 | 说明 |
|--------|------|
| 401 | 用户名或密码错误 |

---

## 2. 对话模块

### 2.1 发送消息

```
POST /api/chat
```

请求体：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| session_id | string | 是 | 会话 ID |
| message | string | 是 | 用户消息 |
| user_id | string | 否 | 用户 ID（Token 鉴权时自动填充） |

响应：

```json
{
  "status": "completed",
  "reply": "为您推荐以下行程..."
}
```

错误码：

| 状态码 | 说明 |
|--------|------|
| 429 | 请求过于频繁 |

---

### 2.2 流式对话

```
POST /api/chat/stream
```

请求体与 `/api/chat` 相同。

响应：Server-Sent Events (SSE) 流，每行格式为 `data: {json}\n\n`

事件类型：

| type | data | 说明 |
|------|------|------|
| `status` | `"thinking"` | 正在思考/工具调用中 |
| `tool_status` | 状态文本 | 工具执行状态（搜索机票、搜索酒店等） |
| `chunk` | 文本片段 | 流式文本片段 |
| `done` | `"completed"` | 流式结束 |
| `error` | 错误信息 | 出错 |

示例：

```
data: {"type": "status", "data": "thinking"}

data: {"type": "tool_status", "data": "正在搜索机票..."}

data: {"type": "chunk", "data": "为您推荐"}

data: {"type": "chunk", "data": "以下行程"}

data: {"type": "done", "data": "completed"}
```

---

## 3. 会话模块

### 3.1 获取会话列表

```
GET /api/sessions
```

响应：

```json
{
  "sessions": [
    {
      "session_id": "abc123",
      "title": "东京5日游",
      "created_at": "2026-06-01T10:00:00",
      "updated_at": "2026-06-01T12:00:00",
      "message_count": 8
    }
  ]
}
```

---

### 3.2 创建会话

```
POST /api/sessions
```

响应：

```json
{
  "session_id": "a1b2c3d4e5f6",
  "user_id": "ee3d2c304e265393"
}
```

---

### 3.3 删除会话

```
DELETE /api/sessions/{session_id}
```

响应：

```json
{
  "detail": "已删除"
}
```

---

### 3.4 获取会话消息

```
GET /api/sessions/{session_id}/messages
```

响应：

```json
{
  "messages": [
    {
      "role": "user",
      "content": "帮我规划一个东京5日游",
      "timestamp": "2026-06-01T10:00:00"
    },
    {
      "role": "assistant",
      "content": "好的，为您规划东京5日游...",
      "timestamp": "2026-06-01T10:01:00"
    }
  ]
}
```

---

## 4. 行程模块

### 4.1 创建行程

```
POST /api/itineraries
```

请求体：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| title | string | 是 | 行程标题 |
| destination | string | 是 | 目的地 |
| start_date | string | 否 | 开始日期 |
| end_date | string | 否 | 结束日期 |
| budget | string | 否 | 预算描述，如"约5000元/人" |
| session_id | string | 否 | 关联会话 ID |
| raw_content | string | 否 | 原始 AI 生成内容 |
| status | string | 否 | 状态，默认 `planning` |
| days | array | 否 | 天数列表（含活动详情） |

`days` 中每个元素的结构：

| 字段 | 类型 | 说明 |
|------|------|------|
| date | string | 日期 |
| title | string | 当天标题 |
| summary | string | 当天摘要 |
| activities | array | 活动列表 |

`activities` 中每个元素的结构：

| 字段 | 类型 | 说明 |
|------|------|------|
| time_slot | string | 时间段 |
| title | string | 活动标题 |
| location | string | 地点 |
| description | string | 描述 |
| cost | number | 预算花费 |
| tips | string | 小贴士 |
| image_url | string | 图片 URL |

响应：返回完整的行程对象。

---

### 4.2 获取行程列表

```
GET /api/itineraries
```

响应：

```json
{
  "itineraries": [
    {
      "id": 1,
      "title": "东京5日游",
      "destination": "东京",
      "start_date": "2026-07-01",
      "end_date": "2026-07-05",
      "budget": "约8000元/人",
      "status": "planning",
      "created_at": "2026-06-01T10:00:00",
      "updated_at": "2026-06-01T12:00:00"
    }
  ]
}
```

---

### 4.3 获取行程详情

```
GET /api/itineraries/{itinerary_id}
```

响应：返回完整行程对象，包含所有天数和活动详情。

---

### 4.4 更新行程

```
PUT /api/itineraries/{itinerary_id}
```

请求体：与创建行程相同，仅需传入要更新的字段。

响应：返回更新后的完整行程对象。

---

### 4.5 删除行程

```
DELETE /api/itineraries/{itinerary_id}
```

响应：

```json
{
  "detail": "已删除"
}
```

---

### 4.6 行程对比

```
POST /api/itineraries/compare
```

请求体：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| ids | array | 是 | 行程 ID 列表，2-4 个 |

响应：

```json
{
  "itineraries": [
    {
      "id": 1,
      "title": "东京5日游",
      "destination": "东京",
      "budget_total": 8000,
      "actual_total": 0,
      "days_count": 5,
      "activities_count": 20,
      "days": [
        {
          "day_index": 0,
          "title": "浅草·秋叶原",
          "budget": 1500,
          "actual": 0,
          "activities": [...]
        }
      ]
    }
  ]
}
```

---

### 4.7 花费统计

```
GET /api/itineraries/{itinerary_id}/expense-summary
```

响应：

```json
{
  "itinerary_id": "1",
  "title": "东京5日游",
  "budget_text": "约8000元/人",
  "budget_total": 8000,
  "actual_total": 3200,
  "remaining": 4800,
  "days": [
    {
      "day_index": 0,
      "title": "浅草·秋叶原",
      "budget": 1500,
      "actual": 800,
      "activities": [
        {
          "id": 1,
          "title": "浅草寺",
          "budget": 100,
          "actual": 80,
          "checked_in": true
        }
      ]
    }
  ]
}
```

---

### 4.8 活动打卡

```
PATCH /api/itineraries/{itinerary_id}/activities/{activity_id}/checkin
```

请求体：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| checked_in | boolean | 否 | 是否已打卡，默认 `true` |

响应：返回更新后的活动对象。

---

### 4.9 删除活动

```
DELETE /api/itineraries/{itinerary_id}/activities/{activity_id}
```

响应：

```json
{
  "detail": "已删除"
}
```

---

### 4.10 更新活动实际花费

```
PATCH /api/itineraries/{itinerary_id}/activities/{activity_id}/cost
```

请求体：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| actual_cost | number | 是 | 实际花费 |

响应：返回更新后的活动对象。

---

### 4.11 创建分享链接

```
POST /api/itineraries/{itinerary_id}/share
```

请求体（可选）：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| expires_at | string | 否 | 过期时间 |

响应：

```json
{
  "token": "abc123def456",
  "itinerary_id": "1"
}
```

---

### 4.12 获取分享链接列表

```
GET /api/itineraries/{itinerary_id}/shares
```

响应：

```json
{
  "shares": [
    {
      "token": "abc123def456",
      "created_at": "2026-06-01T10:00:00",
      "view_count": 5
    }
  ]
}
```

---

### 4.13 删除分享链接

```
DELETE /api/itineraries/{itinerary_id}/shares/{token}
```

响应：

```json
{
  "detail": "已删除"
}
```

---

### 4.14 查看分享行程

```
GET /api/shared/{token}
```

**公开接口，无需鉴权**

响应：

```json
{
  "itinerary": {
    "id": 1,
    "title": "东京5日游",
    "destination": "东京",
    "days": [...]
  },
  "share_info": {
    "view_count": 6,
    "created_at": "2026-06-01T10:00:00"
  }
}
```

---

## 5. 地理编码模块

### 5.1 国内地址批量编码

```
POST /api/geocode
```

请求体：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| addresses | array | 是 | 地址列表，最多 20 个 |

响应：

```json
{
  "results": [
    {
      "address": "北京市海淀区",
      "lng": 116.29845,
      "lat": 39.95989,
      "formatted": "北京市海淀区"
    }
  ]
}
```

---

### 5.2 国际地址编码

```
POST /api/geocode/intl
```

请求体：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| address | string | 是 | 地址名称 |
| city | string | 否 | 城市名称（辅助定位） |

查找策略：内置坐标库 → Nominatim（OpenStreetMap）

响应：

```json
{
  "address": "东京塔",
  "lng": 139.7454,
  "lat": 35.6586,
  "formatted": "东京塔"
}
```

---

## 6. 记忆模块

### 6.1 获取用户记忆

```
GET /api/memories
```

响应：

```json
{
  "long_term": [
    {
      "id": 1,
      "category": "preference",
      "category_label": "偏好",
      "content": "喜欢日式料理",
      "experience_tag": null,
      "extraction_count": 3,
      "last_accessed_at": "2026-06-01T10:00:00",
      "created_at": "2026-05-20T08:00:00"
    }
  ],
  "short_term": [...],
  "summary": {
    "total_ltm": 5,
    "total_stm": 3,
    "preferences": 3,
    "facts": 2,
    "experiences": 3
  }
}
```

---

### 6.2 删除记忆

```
DELETE /api/memories/{memory_type}/{memory_id}
```

路径参数：

| 参数 | 说明 |
|------|------|
| memory_type | `short_term` 或 `long_term` |
| memory_id | 记忆 ID |

---

## 7. 热门推荐

### 7.1 获取热门旅行话题

```
GET /api/trending
```

**公开接口，无需鉴权**

查询参数：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| refresh | boolean | 否 | 是否强制刷新，默认 `false` |

响应：

```json
{
  "items": [
    {
      "title": "暑期海岛游推荐",
      "tag": "热门",
      "summary": "三亚、马尔代夫、巴厘岛...",
      "content": "...",
      "img": "https://...",
      "hotScore": "1.2万",
      "hotChange": "上升"
    }
  ]
}
```

---

## 8. 系统监控

### 8.1 健康检查

```
GET /health
```

**公开接口，无需鉴权**

响应：

```json
{
  "status": "healthy",
  "details": {
    "database": "ok",
    "redis": "ok"
  }
}
```

---

### 8.2 Prometheus 指标

```
GET /metrics
```

**公开接口，无需鉴权**

返回 Prometheus 格式的监控指标。

---

## 9. 调试接口

以下接口仅在开发环境使用，生产环境应禁用。

### 9.1 获取会话追踪

```
GET /debug/trace/{session_id}
```

### 9.2 获取会话快照

```
GET /debug/session/{session_id}
```

### 9.3 获取记忆快照

```
GET /debug/memory?query=&limit=10&session_id=default
```

### 9.4 获取 MCP 服务器列表

```
GET /debug/mcp
```

### 9.5 MCP 工具选择

```
GET /debug/mcp/select?query=搜索&limit=4
```

### 9.6 获取任务快照

```
GET /debug/task/{session_id}
```

---

## 10. 相册模块

### 10.1 上传照片

```
POST /api/itineraries/{itinerary_id}/photos
```

Content-Type: `multipart/form-data`

请求参数：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| files | file[] | 是 | 照片文件列表（支持多文件） |
| description | string | 否 | 照片描述 |
| day_index | int | 否 | 关联的天数索引，默认 0 |

响应：

```json
{
  "photos": [
    {
      "id": 1,
      "file_name": "IMG_001.jpg",
      "file_size": 2048000,
      "mime_type": "image/jpeg",
      "description": "东京塔夜景",
      "day_index": 1,
      "storage_path": "album/20260621/abc123.jpg",
      "thumbnail_path": "album/20260621/abc123_thumb.jpg",
      "latitude": 35.6586,
      "longitude": 139.7454,
      "ai_description": "东京塔夜景，灯光璀璨",
      "tags": ["景点", "夜景"],
      "is_cover": false,
      "created_at": "2026-06-21T10:00:00"
    }
  ]
}
```

---

### 10.2 获取照片列表

```
GET /api/itineraries/{itinerary_id}/photos
```

查询参数：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| day_index | int | 否 | 按天数筛选 |
| tag | string | 否 | 按标签筛选 |

响应：

```json
{
  "itinerary_id": "1",
  "photos": [
    {
      "id": 1,
      "file_name": "IMG_001.jpg",
      "description": "东京塔夜景",
      "day_index": 1,
      "thumbnail_path": "album/20260621/abc123_thumb.jpg",
      "tags": ["景点", "夜景"],
      "is_cover": false
    }
  ],
  "total": 10,
  "tags": ["景点", "美食", "夜景"],
  "cover": {
    "id": 1,
    "file_name": "IMG_001.jpg",
    "thumbnail_path": "album/20260621/abc123_thumb.jpg"
  }
}
```

---

### 10.3 删除照片

```
DELETE /api/itineraries/{itinerary_id}/photos/{photo_id}
```

响应：

```json
{
  "detail": "已删除"
}
```

错误码：

| 状态码 | 说明 |
|--------|------|
| 403 | 无权删除此照片 |
| 404 | 照片不存在 |

---

### 10.4 更新照片信息

```
PATCH /api/itineraries/{itinerary_id}/photos/{photo_id}
```

请求体：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| description | string | 否 | 照片描述 |
| day_index | int | 否 | 关联的天数索引 |
| tags | array | 否 | 标签列表 |

响应：返回更新后的照片对象。

---

### 10.5 设置封面照片

```
POST /api/itineraries/{itinerary_id}/photos/{photo_id}/cover
```

响应：返回设置为封面的照片对象。

---

### 10.6 获取照片地理位置

```
GET /api/itineraries/{itinerary_id}/photos/map
```

响应：

```json
{
  "itinerary_id": "1",
  "markers": [
    {
      "photo_id": 1,
      "latitude": 35.6586,
      "longitude": 139.7454,
      "description": "东京塔",
      "day_index": 1,
      "thumbnail_path": "album/20260621/abc123_thumb.jpg"
    }
  ]
}
```

---

### 10.7 生成游记

```
POST /api/itineraries/{itinerary_id}/travelogue
```

基于行程和照片自动生成游记内容。

响应：

```json
{
  "itinerary_id": "1",
  "content": "# 东京之旅\n\n第一天，我们来到了东京塔..."
}
```

---

### 10.8 获取相册图片文件

```
GET /api/album/{file_path}
```

用于前端 `<img>` 标签直接访问图片文件。支持通过 query param 传递 token。

查询参数：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| token | string | 否 | 用户 token（因 `<img>` 标签无法携带 Authorization header） |

响应：图片文件二进制数据。

---

## 通用错误格式

所有接口在出错时返回统一格式：

```json
{
  "detail": "错误描述信息"
}
```

常见 HTTP 状态码：

| 状态码 | 说明 |
|--------|------|
| 400 | 请求参数错误 |
| 401 | 未登录或 Token 过期 |
| 404 | 资源不存在 |
| 429 | 请求频率超限 |
| 500 | 服务器内部错误 |
| 503 | 外部服务不可用 |
