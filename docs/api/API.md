# 云合 API 接口文档（前端开发参考）

> 本文档专为前端开发者编写，包含全部 **79 个**接口的请求 / 响应格式、TypeScript 类型定义、代码示例和错误处理。
>
> 业务基线：[docs/superpowers/specs/2026-07-16-product-and-news-agent-design.md](../superpowers/specs/2026-07-16-product-and-news-agent-design.md) ·
> 开发规范：[AGENTS.md](../../AGENTS.md) ·
> 模块实施计划：[docs/superpowers/plans/](../superpowers/plans/)

## 接口总览（79 个）

| 模块 | 前缀 | 端点数 | 鉴权 |
|------|------|--------|------|
| 认证 | `/api/v1/auth` | 3 | 注册 / 登录公开；`/me` Cookie |
| 对话（SSE） | `/api/v1/chat` | 2 | Cookie |
| 会话 | `/api/v1/sessions` | 5 | Cookie |
| 方案确认 | `/api/v1/session` | 3 | Cookie |
| 智能体 | `/api/v1/agents` | 6 | Cookie |
| 技能 | `/api/v1/skills` | 2 | Cookie |
| MCP | `/api/v1/mcp` | 3 | Cookie（`/` 与 `/servers` 同 handler）|
| 行程 | `/api/v1/itineraries` | 9 | Cookie |
| 旅行草稿 / 存档 | `/api/v1/travel` | 8 | Cookie |
| 记忆 | `/api/v1/memories` | 2 | Cookie |
| 新闻 | `/api/v1/news` | 6 | Cookie（`/trending` 公开）|
| 新闻来源治理 | `/api/v1/admin/news` | 5 | 管理员 Cookie |
| 股票复盘 | `/api/v1/stock` | 14 | Cookie |
| 地理编码 | `/api/v1/geocode` | 2 | Cookie |
| 分享 | `/api/v1/share` | 1 | 公开 |
| 反馈 | `/api/v1/feedback` | 1 | Cookie |
| 健康检查 / 指标 | `/api/v1/health` | 2 | 公开 |
| 调试（开发环境） | `/api/v1/debug` | 5 | Cookie |

> **接口前缀**：`/api/v1` 与 `/api` 双向挂载，等价；前端可任选其一。**推荐 `/api/v1`**。

---

## 基础信息

| 项目 | 说明 |
|------|------|
| 基础地址 | `http://localhost:8000`（开发环境） |
| Content-Type | `application/json`（除文件上传外） |
| 字符编码 | UTF-8 |
| 项目启动 | 见 [README.md](../../README.md#快速开始) |

---

## 鉴权机制（两套模式）

### 模式 A：浏览器（Cookie + CSRF，**主路径**）

> 详见 [AGENTS.md](../../AGENTS.md) §4。**所有浏览器端代码必须走此模式**。

登录 / 注册成功后，服务器同时下发两个 cookie：

| Cookie | HttpOnly | 用途 |
|--------|----------|------|
| `auth_token` | ✅ | 长期认证凭据，浏览器自动随请求发送；JS 不可读 |
| `csrf_token` | ❌ | 独立随机值，JS 可读；与 `auth_token` **不同值** |

不安全方法（POST/PUT/PATCH/DELETE）必须额外携带 `X-CSRF-Token` header，值等于 `csrf_token` cookie（double-submit 模式）。

**统一客户端**（`frontend/src/features/auth/client.ts`）：

```typescript
import { AuthClient } from '@/features/auth/client'

const http = new AuthClient()

// GET：自动 credentials: 'include'
const res = await http.request('/api/v1/sessions')

// POST/PUT/PATCH/DELETE：自动从 csrf_token cookie 读取并注入 X-CSRF-Token
const res = await http.request('/api/v1/itineraries', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ title: '东京5日游', destination: '东京' }),
})

// 统一 401 处理
if (res.status === 401) {
  // 调用方自行决定：清除本地状态 / 跳转登录
  await fetch('/api/v1/auth/logout', { method: 'POST', credentials: 'include' })
  window.location.href = '/login'
}
```

**禁止**：

- ❌ 持久化 `auth_token` 到 localStorage / sessionStorage
- ❌ 自建 axios / fetch 实例直接调 API（绕过 CSRF）
- ❌ 尝试读取 `auth_token` cookie（HttpOnly，JS 拿不到）

### 模式 B：非浏览器（Bearer Token，**仅脚本 / CLI 场景**）

> 出于向后兼容，非浏览器客户端（脚本 / CLI / 服务端）仍可使用 Bearer Token。
> **浏览器主路径已移除 Bearer**（[AGENTS.md](../../AGENTS.md) §4）。

```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/sessions
```

> ⚠ 新增非浏览器 Bearer 凭据时，必须有专用签发 / 撤销 / 审计 / 测试方案，**不能复用登录响应**。

### 公开接口（无需鉴权）

| 路径 | 说明 |
|------|------|
| `POST /api/v1/auth/register` | 用户注册 |
| `POST /api/v1/auth/login` | 用户登录 |
| `GET /api/v1/news/trending` | 旅行热门 |
| `GET /api/v1/share/{token}` | 查看分享行程 |
| `GET /api/v1/health` | 健康检查 |
| `GET /api/v1/health/metrics` | Prometheus 指标 |
| `GET /metrics` | Prometheus 指标（兼容路径） |

---

## 通用 TypeScript 类型

```typescript
// ===== 通用响应 =====
interface ApiError {
  detail: string;
  code?: string;       // 业务错误码（如 CORRELATION_WEEKLY_ONLY）
  trace_id?: string;   // 错误追踪
}

interface PaginationParams {
  limit?: number;      // 默认 10
  offset?: number;     // 默认 0
}

// ===== 通用 SSE 事件 =====
type SSEEventType =
  | 'thinking'
  | 'tool_status'
  | 'chunk'
  | 'actions'
  | 'evidence'         // 新闻研判：证据卡片（chat.py:168-178）
  | 'done'
  | 'error';

interface SSEEvent {
  type: SSEEventType;
  data: string | object;
  trace_id?: string;
}
```

---

## 1. 认证模块

### 1.1 用户注册

```
POST /api/v1/auth/register
```

**公开接口**

```typescript
interface RegisterRequest {
  username: string;   // 必填，2-32 字符，只允许字母数字下划线
  password: string;   // 必填，至少 6 位
}

// 调用
const res = await http.request('/api/v1/auth/register', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username: 'zhangsan', password: '123456' }),
})
// → Set-Cookie: auth_token=...; csrf_token=...; HttpOnly; SameSite=Lax

// 响应（响应体不再含 token，token 只能从 cookie 取得）
interface AuthResponse {
  user_id: string;
  username: string;
}
```

| 状态码 | 说明 |
|--------|------|
| 200 | 注册成功，cookie 已下发 |
| 400 | 用户名长度不符 / 密码过短 / 用户名已存在 |

### 1.2 用户登录

```
POST /api/v1/auth/login
```

**公开接口**

请求体同注册；响应同注册。失败返回 401。

### 1.3 当前用户

```
GET /api/v1/auth/me
```

**Cookie 鉴权**；返回 `{ user_id, username }`。未登录返回 401。

---

## 2. 对话模块（SSE）

> 推荐使用流式接口。`/api/v1/chat` 同步接口在响应体结构上与 SSE 的 `done` 事件对齐。

### 2.1 同步对话

```
POST /api/v1/chat
```

```typescript
interface ChatRequest {
  session_id: string;       // 必填
  message: string;          // 必填，1-8000 字符
  user_id?: string;         // 可选，Cookie 鉴权时由后端自动填充
  agent_id?: string;        // 可选；news_analysis_locked 会话下无效
}

interface ChatResponse {
  status: 'completed';
  reply: string;
}
```

### 2.2 流式对话（SSE — **推荐**）

```
POST /api/v1/chat/stream
```

**请求体**与 `/api/v1/chat` 完全相同。响应为 `text/event-stream`。

#### SSE 事件类型

| `type` | `data` | 触发时机 | 前端处理 |
|--------|--------|----------|----------|
| `thinking` | `"thinking"` | Agent 开始推理 | 显示"思考中..." |
| `tool_status` | 文本（`"正在搜索机票..."`）| 工具开始执行 | 显示工具状态指示器 |
| `chunk` | 文本片段 | AI 逐词输出 | **追加**到消息末尾 |
| `actions` | JSON 对象数组 | 操作卡片 | 渲染按钮 |
| `evidence` | JSON 对象数组 | **新闻研判**：证据卡片（`chat.py:168`）| 渲染证据列表 |
| `done` | `"completed"` + `trace_id` | 正常结束 | 停止流式，保存完整回复 |
| `error` | 错误信息 + `trace_id` | 异常 | 显示错误 |

#### `evidence` 事件（新闻研判专用）

仅 `news_analysis_locked` 会话触发；在 `chunk` 之前推送。`data` 是 `EvidenceCard[]`：

```typescript
interface EvidenceCard {
  source_id: string;
  source_name: string;
  url: string;
  claim: string;
  status: 'verified' | 'conflicted' | 'unverified_leads';
}
```

> 空数组也推送——前端应明确"无证据"而非误读为"事件丢失"。

#### `actions` 事件

```typescript
interface AgentActionCard {
  type: string;             // 'generate_itinerary' / 'confirm_draft' / ...
  label: string;
  itinerary_id?: number;
  session_id?: string;
  plan_type?: 'sightseeing' | 'budget';
}
```

**多方案锚点协议**：旅行 Agent 在 LLM 回复末尾注入 HTML 注释 `<!--MULTI_PLAN:plan1=sightseeing,plan2=budget-->`；前端解析后渲染"景点打卡型 / 经济实惠型"双按钮。

#### 前端实现示例

```typescript
async function chatStream(
  sessionId: string,
  message: string,
  onEvent: (event: SSEEvent) => void,
  signal?: AbortSignal,
): Promise<string> {
  const res = await http.request('/api/v1/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, message }),
    signal,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || '请求失败')
  }
  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let full = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const jsonStr = line.slice(6).trim()
      if (!jsonStr) continue
      try {
        const event = JSON.parse(jsonStr) as SSEEvent
        if (event.type === 'chunk') full += event.data as string
        onEvent(event)
      } catch { /* 非 JSON 行忽略 */ }
    }
  }
  return full
}
```

> **新闻研判工作流**（前端封装在 `features/news/analysis.ts`）：
>
> 1. `POST /api/v1/news/hotspots/{news_id}/analysis-sessions` 创建锚定会话
> 2. 后端自动发出一条分析 prompt 触发新闻 Agent
> 3. 前端在 SSE 流中接收 `evidence` + `chunk` 事件
> 4. **新闻 Agent 永不向用户反问**（[AGENTS.md](../../AGENTS.md) §3）

---

## 3. 会话模块

### 3.1 会话列表

```
GET /api/v1/sessions
```

```typescript
interface SessionItem {
  session_id: string;
  user_id: string;
  mode: 'yunhe_default' | 'agent_locked' | 'news_analysis_locked';
  locked_agent_id: string | null;
  news_id: string | null;          // 仅 news_analysis_locked
}
```

### 3.2 创建会话

```
POST /api/v1/sessions
```

```typescript
interface CreateSessionRequest {
  mode?: 'yunhe_default' | 'agent_locked';   // 默认 yunhe_default
  locked_agent_id?: string;                  // agent_locked 必填
}

// 响应
{
  code: 0,
  message: 'success',
  data: { session_id, user_id, mode, locked_agent_id, news_id }
}
```

> ⚠ 用户 API **不接受** `mode=news_analysis_locked`——该模式仅由新闻服务内部创建。

### 3.3 切换会话模式

```
PATCH /api/v1/sessions/{session_id}/mode
```

```typescript
interface UpdateSessionModeRequest {
  mode: 'yunhe_default' | 'agent_locked';
  locked_agent_id?: string;
}
```

### 3.4 删除会话

```
DELETE /api/v1/sessions/{session_id}
```

### 3.5 获取会话消息历史

```
GET /api/v1/sessions/{session_id}/messages
```

```typescript
interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
}
```

---

## 4. 方案确认模块（多方案对比）

> 旅行 Agent 生成多方案后，前端双按钮 / 确认 / 撤销状态机。**仅锁定 sightseeing / budget 两套方案**。

### 4.1 确认方案

```
POST /api/v1/session/{session_id}/confirm-plan
```

```typescript
interface ConfirmPlanRequest {
  plan_type: 'sightseeing' | 'budget';
  itinerary_id: string;            // 必填
}

interface ConfirmPlanResponse {
  confirmed_plan: 'sightseeing' | 'budget';
  itinerary_id: string;
  confirmed_at: string;
}
```

| 状态码 | 说明 |
|--------|------|
| 200 | 首次确认 / 重复确认同一方案（**幂等**）|
| 409 | 已确认其他方案（需先撤销）|
| 404 | 会话不属于当前用户（**不暴露存在性**）|

### 4.2 撤销方案

```
POST /api/v1/session/{session_id}/revoke-confirm
```

请求体：`{ itinerary_id: string }`；响应：`{ code: 0, message: 'success', data: {...} }`。

### 4.3 查询确认状态

```
GET /api/v1/session/{session_id}/confirm-status
```

```typescript
interface ConfirmStatusResponse {
  confirmed_plan: 'sightseeing' | 'budget' | null;
  confirmed_at: string | null;
  itinerary_id?: number;
}
```

---

## 5. 智能体模块

### 5.1 智能体列表

```
GET /api/v1/agents
```

```typescript
interface AgentConfig {
  id: string;
  name: string;
  description: string;
  icon: string;
  skills: string[];
  mcp_servers: string[];
  system_prompt: string;     // 仅自定义 Agent
  welcome_message: string;
  temperature: number;
  is_public: boolean;
  source: 'builtin' | 'custom';
  status?: string;            // 'draft' | 'published'
}

// 响应
{ builtin: AgentConfig[], custom: AgentConfig[], public: AgentConfig[] }
```

**内置 Agent**（`application/builtin_agents/*.yaml`）：

| id | 名称 | 触发关键词示例 |
|----|------|----------------|
| `yunhe` | 云合 | 默认调度；日常问答 / 知识 / 写作 / 委派 |
| `travel` | 旅行规划助手 | 旅行 / 行程 / 景点 / 机票 / 自驾 |
| `academic` | 学术搜索助手 | 论文 / arXiv / 引用 / 创新点 |
| `news` | 新闻助手 | 热点 / 研判 / 多源验证（**仅锁定会话**）|
| `stock` | 股市复盘助手 | 复盘 / 大盘 / 板块轮动 / 涨停 / 龙头 |

### 5.2-5.6 自定义 Agent CRUD

```
POST   /api/v1/agents/custom                      // 创建
GET    /api/v1/agents/custom/{agent_id}            // 详情
PUT    /api/v1/agents/custom/{agent_id}            // 更新（仅创建者）
DELETE /api/v1/agents/custom/{agent_id}            // 删除（仅创建者）
POST   /api/v1/agents/custom/{agent_id}/clone      // 克隆到工作区
```

请求 / 响应字段同 `AgentConfig`；权限失败返回 403 / 404（不暴露存在性）。

---

## 6. 技能模块

```
GET /api/v1/skills                       // 列表
GET /api/v1/skills/{skill_name}          // 详情
```

```typescript
interface SkillInfo {
  name: string;          // 'amap-maps' / 'q-weather' / 'stock-review' / ...
  display_name: string;
  description: string;
  version: string;
}
```

**内置 Skill**（`infrastructure/skills/builtin/`）：

| 名称 | 用途 |
|------|------|
| `amap-maps` | 高德地图 POI / 路线 / 静态图 |
| `q-weather` | 和风天气实况 / 预报 |
| `stock-review` | 股票复盘工具集（akshare + SQLite 缓存）|

> 飞猪旅行 Skill（`fliggy-travel`）代码骨架仍存在但**不再推荐**用于下单；仅保留信息查询。

---

## 7. MCP 服务器模块

```
GET /api/v1/mcp                          // 列表（等价 /mcp/servers）
GET /api/v1/mcp/{server_id}              // 详情
GET /api/v1/mcp/{server_id}/tools        // 工具列表
```

```typescript
interface MCPServerInfo {
  identifier: string;
  name: string;
  description: string;
  instructions: string;
  tools: MCPToolInfo[];
}

interface MCPToolInfo {
  name: string;
  description: string;
  proxy_name: string;
  input_schema: object;
  adapter_available: boolean;
}
```

---

## 8. 行程模块

> 行程是规划快照（**非报销凭证**）。无相册 / 实际花费 / 打卡 / 行程比较。

### 8.1 行程数据结构

```typescript
interface Itinerary {
  id: string;
  user_id: string;
  title: string;
  destination: string;
  start_date?: string;
  end_date?: string;
  budget?: string;             // 描述文本
  status: 'planning' | 'in_progress' | 'completed';
  session_id: string;
  raw_content: string;         // AI 生成的 Markdown
  plans_json?: string;         // 多方案（sightseeing / budget）
  confirmed_plan?: 'sightseeing' | 'budget' | null;
  confirmed_at?: string | null;
  recommended_plan?: string | null;
  days: DayPlan[];
}

interface DayPlan {
  day_index: number;
  date: string;
  title: string;
  summary: string;
  activities: Activity[];       // ⚠ 不含 checked_in / actual_cost
}

interface Activity {
  id: number;
  time_slot: string;
  title: string;
  location: string;
  description: string;
  image_url: string;
  cost: number;                // 预算花费
  tips: string;
}
```

### 8.2 端点

```
POST   /api/v1/itineraries                                // 创建
GET    /api/v1/itineraries                                // 列表
GET    /api/v1/itineraries/{itinerary_id}                 // 详情
PUT    /api/v1/itineraries/{itinerary_id}                 // 更新
DELETE /api/v1/itineraries/{itinerary_id}                 // 删除
DELETE /api/v1/itineraries/{itinerary_id}/activities/{id} // 删除活动
POST   /api/v1/itineraries/{itinerary_id}/share           // 创建分享
GET    /api/v1/itineraries/{itinerary_id}/shares          // 分享列表
DELETE /api/v1/itineraries/{itinerary_id}/shares/{token}  // 删除分享
```

> 已移除：`/compare`、`/checkin`、`/cost`、`/photos/*`、`/travelogue`、`/album/*`（见 [AGENTS.md](../../AGENTS.md) §3）。

---

## 9. 旅行草稿 / 存档（travel）

> 用户在对话中编辑的字段 → 草稿；点击"更新信息" → 唯一外部查询入口；点击"确认行程" → 不可变存档。
> 详见 [docs/superpowers/plans/2026-07-17-travel-planning.md](../superpowers/plans/2026-07-17-travel-planning.md)。

### 9.1 草稿生命周期

```
POST   /api/v1/travel/drafts                                              // 创建
GET    /api/v1/travel/drafts/{draft_id}                                   // 读取
PATCH  /api/v1/travel/drafts/{draft_id}/activities/{activity_id}          // 手工编辑（记入 manual_edit_fields）
POST   /api/v1/travel/drafts/{draft_id}/refresh-preview                   // ⚠ 唯一外部数据入口
POST   /api/v1/travel/drafts/{draft_id}/refresh-apply                     // 应用用户勾选的变更
POST   /api/v1/travel/drafts/{draft_id}/confirm                           // 确认（创建不可变存档）
```

### 9.2 存档

```
GET    /api/v1/travel/archives/{archive_id}                               // 读取
POST   /api/v1/travel/archives/{archive_id}/new-draft                     // 基于存档创建新草稿
```

### 9.3 数据结构

```typescript
interface TravelDraft {
  id: string;
  user_id: string;
  session_id: string;
  plan: object;                            // 完整 plan（含 days / activities）
  manual_edit_fields: string[];            // 手工编辑字段（Agent 不得覆盖）
  is_read_only: boolean;                   // 已确认后为 true
  source_archive_id: string | null;
  created_at: string;
  updated_at: string;
}

interface TravelArchive {
  id: string;
  user_id: string;
  source_draft_id: string;
  confirmed_at: string;
  plan: object;                            // 不可变 plan 快照
}
```

---

## 10. 记忆模块

```
GET    /api/v1/memories                              // 列表（短期 + 长期 + summary）
DELETE /api/v1/memories/{memory_type}/{memory_id}    // memory_type: short_term | long_term
```

```typescript
interface MemoryItem {
  id: number;
  category: 'preference' | 'fact' | 'experience';
  category_label: string;             // 中文：偏好 / 事实 / 经验
  content: string;
  experience_tag: string | null;
  extraction_count: number;
  last_accessed_at: string;
  created_at: string;
}

interface MemoryResponse {
  long_term: MemoryItem[];
  short_term: MemoryItem[];
  summary: {
    total_ltm: number;
    total_stm: number;
    preferences: number;
    facts: number;
    experiences: number;
  };
}
```

---

## 11. 新闻模块

> 热点池 / 研判 / 收藏三部分。锚点仅含元数据，**不存新闻全文**（[AGENTS.md](../../AGENTS.md) §3）。

### 11.1 旅行热门（公开）

```
GET /api/v1/news/trending?refresh=false
```

### 11.2 热点池

```
GET /api/v1/news/hotspots
```

```typescript
interface Hotspot {
  id: string;
  title: string;
  source: string;
  url: string;
  summary: string;
  published_at: string;
}
```

> **只读缓存**（`HotspotService.list_current`）。外部抓取由定时器 + `HotspotService.refresh` 负责；`GET /hotspots` 不得触发外部调用（[AGENTS.md](../../AGENTS.md) §3）。

### 11.3 创建新闻锚定会话（深度研判入口）

```
POST /api/v1/news/hotspots/{news_id}/analysis-sessions
```

**前端调用此端点后，后端自动**：

1. 创建 `news_analysis_locked` 会话
2. **`locked_agent_id` 固定为 `news`**，不接受客户端传入
3. 注入锚点元数据（标题 / 来源 / URL / 摘要 / 发布时间）
4. 触发一次新闻 Agent 推研（**Agent 永不向用户反问**）

```typescript
interface AnalysisSessionResponse {
  session_id: string;
  mode: 'news_analysis_locked';
  locked_agent_id: 'news';
  news_id: string;
  anchor: Hotspot;            // 锚点元数据
}
```

### 11.4 新闻收藏

```
GET    /api/v1/news/favorites                // 列表
POST   /api/v1/news/favorites                // 收藏（仅元数据；不存全文；不注入短期记忆）
DELETE /api/v1/news/favorites/{favorite_id}  // 取消
```

```typescript
interface NewsFavorite {
  id: number;
  title: string;
  summary: string;
  url: string;
  source: string;
  tag: string;
  created_at: string;
}
```

> 当前收藏不注入短期记忆（v1.2 行为变更；纯元数据存档）。

---

## 12. 新闻来源治理（管理员）

> 单一系统管理员（启动期从 `YUNHE_ADMIN_USERNAME` 解析）。**所有端点要求当前用户 === admin_user_id**，否则 403。

### 12.1 端点

```
GET    /api/v1/admin/news/sources                              // 列表（含全部状态）
POST   /api/v1/admin/news/sources/register-builtin             // 注册内置白名单
POST   /api/v1/admin/news/sources/{source_id}/review           // 审核（更新状态 + 写审计）
GET    /api/v1/admin/news/source-audits                        // 审计记录
GET    /api/v1/admin/news/source-inits                         // 初始化事件
```

### 12.2 审核请求

```typescript
interface SourceReviewRequest {
  decision: 'pending' | 'enabled' | 'lead_only' | 'rejected' | 'blocked' | 'needs_review';
  reason: string;                  // 1-500 字符
}
```

### 12.3 数据结构

```typescript
interface NewsSource {
  id: string;
  name: string;
  domain: string;
  tier: 'mainstream' | 'aggregator' | 'official';
  status: 'pending' | 'enabled' | 'lead_only' | 'rejected' | 'blocked' | 'needs_review';
  scoring_mode: 'builtin_whitelist' | 'ai' | 'heuristic';
  ai_score: number | null;          // 0-1
  ai_reason: string | null;
  ai_subscores: {                   // 六维评分（0-上限）
    publisher_authority: number;    // 上限 0.30
    domain_brand: number;           // 上限 0.20
    topic_relevance: number;        // 上限 0.15
    editorial_standard: number;     // 上限 0.15
    accessibility: number;          // 上限 0.10
    risk_signals: number;           // 上限 0.10
  };
  created_at: string;
  updated_at: string;
}
```

> 内置白名单 `scoring_mode=builtin_whitelist`，`ai_score=null`，`ai_reason='产品内置白名单'`。
> 证据卡片规则：仅 `enabled` 来源产出 `verified` / `conflicted` 证据；其他仅作 `unverified_leads`。
> 前端审核页 `/admin/news?source={source_id}` 自动滚动并高亮该来源。

---

## 13. 股票复盘模块

> A 股五表缓存（`limit_stocks_daily` / `market_index_daily` / `emotion_daily` / `sector_daily` / `stock_daily`）。
> 详见 [docs/superpowers/plans/2026-07-26-stock-review-agent.md](../superpowers/plans/2026-07-26-stock-review-agent.md)。

### 13.1 端点（14 个）

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 1 | GET | `/api/v1/stock/market/snapshot` | 大盘快照（上证 / 深证 / 创业板 / 成交额 / MA20）|
| 2 | GET | `/api/v1/stock/charts/emotion` | 情绪多日曲线（默认 10 日，1-60）|
| 3 | GET | `/api/v1/stock/charts/sector` | 板块轮动多日曲线 |
| 4 | GET | `/api/v1/stock/charts/watchlist` | 观察池多日趋势 |
| 5 | GET | `/api/v1/stock/watchlist` | 观察池当前 |
| 6 | POST | `/api/v1/stock/watchlist` | 增 / 删观察池 |
| 7 | GET | `/api/v1/stock/signals` | 新信号股 |
| 8 | GET | `/api/v1/stock/sectors` | 板块表现 |
| 9 | GET | `/api/v1/stock/sector-leaders` | 板块龙头 |
| 10 | POST | `/api/v1/stock/review` | **触发复盘**（异步；同 user+trade_date 幂等）|
| 11 | GET | `/api/v1/stock/review/tasks/{task_id}` | 任务状态（轮询）|
| 12 | GET | `/api/v1/stock/reports` | 复盘文列表（仅本人）|
| 13 | GET | `/api/v1/stock/reports/{report_id}` | 复盘文详情（跨用户 404）|
| 14 | GET | `/api/v1/stock/correlation` | 庄股 / 抱团（**仅周复盘模式**）|

### 13.2 通用查询参数

```typescript
interface DateParams {
  trade_date?: string;       // 8 位 YYYYMMDD
  end_date?: string;         // charts 区间结束日
  days?: number;             // 默认 10（emotion/sector/watchlist），7（correlation）
  mode?: 'daily' | 'weekly'; // 仅 correlation
}
```

### 13.3 关键响应

```typescript
interface MarketSnapshot {
  trade_date: string;
  sh_index: number;
  sz_index: number;
  cyb_index: number;
  total_volume: number;
  volume_change_pct: number;
  consecutive_down_days: number;
  ma20_status: 'above' | 'below' | 'near';
}

interface EmotionIndicators {
  trade_date: string;
  limit_up_count: number;
  limit_down_count: number;
  valid_limit_up_count: number;
  broken_limit_ratio: number;
  max_consecutive_boards: number;
  yesterday_limit_up_today_premium: number;
  total_volume: number;
  volume_change_pct: number;
  phase: string;                  // 情绪阶段
  phase_confidence: number;
  phase_reason: string;
}

interface WatchlistStock {
  stock_code: string;
  stock_name: string;
  category: number;               // 1-5
  entry_date: string;
  entry_price: number | null;
  status: 'active' | 'closed';
  market_index_snapshot: object | null;
  notes: string;
}

interface SignalStock {
  trade_date: string;
  stock_code: string;
  stock_name: string;
  signal_type: string;
  pct_chg: number;
  market_index_pct_chg: number;
  entry_price: number;
}
```

### 13.4 触发复盘

```typescript
// POST /api/v1/stock/review
interface TriggerReviewRequest {
  trade_date: string;             // 8 位 YYYYMMDD
}

// 响应（202 Accepted）
{
  task_id: string;
  trade_date: string;
  status: 'pending' | 'running';
}

// 轮询 GET /api/v1/stock/review/tasks/{task_id}
interface ReviewTask {
  task_id: string;
  user_id: string;                 // ⚠ 跨用户访问 → 404
  trade_date: string;
  status: 'pending' | 'running' | 'completed' | 'degraded' | 'no_data' | 'failed';
  report_id: string | null;        // completed 时填充
  error: string | null;
  created_at: string;
  updated_at: string;
}
```

> 幂等：同 user + trade_date 在 `pending` / `running` 状态下返回**同一 `task_id`**。
> 业务红线：身份来自 `request.state.user_id`；跨用户访问 `/reports/{id}` → 404（不暴露存在性）。

### 13.5 庄股 / 抱团

```typescript
// GET /api/v1/stock/correlation?end_date=...&days=7&mode=weekly
interface CorrelationResult {
  end_date: string;
  window_days: number;
  individual_stocks: {
    stock_code: string;
    stock_name: string;
    market_correlation: number;
    sector_correlation: number;
    is_independent: boolean;
  }[];
  clustered_groups: {
    members: { stock_code: string; stock_name: string }[];
    intra_correlation: number;
  }[];
}
```

| 状态码 | code | 说明 |
|--------|------|------|
| 409 | `CORRELATION_WEEKLY_ONLY` | `mode=daily` 时调用 |
| 409 | `CORRELATION_NOT_READY` | 缓存未就绪 |

### 13.6 观察池增 / 删

```typescript
// POST /api/v1/stock/watchlist
interface WatchlistActionRequest {
  action: 'add' | 'remove';
  stock_code: string;              // 1-16 字符
  stock_name?: string;
  category?: number;              // 1-5
  entry_date?: string;
  entry_price?: number;
  notes?: string;
}
```

---

## 14. 地理编码模块

```
POST /api/v1/geocode           // 国内批量（高德）
POST /api/v1/geocode/intl      // 国际（Nominatim + 内置坐标库）
```

```typescript
interface GeocodeRequest { addresses: string[]; }  // ≤ 20
interface GeocodeResult {
  address: string;
  lng: number | null;
  lat: number | null;
  formatted: string;
}

interface IntlGeocodeRequest {
  address: string;     // 必填
  city?: string;       // 辅助定位
}
```

> 国内走高德 `restapi.amap.com`；国际先查内置 `api/intl_coords.py`，未命中走 Nominatim（在线程池执行，避免阻塞事件循环）。

---

## 15. 分享模块（公开）

```
GET /api/v1/share/{token}
```

```typescript
interface SharedItinerary {
  itinerary: Itinerary;
  share_info: { view_count: number; created_at: string };
}
```

---

## 16. 反馈模块

```
POST /api/v1/feedback
```

```typescript
interface FeedbackRequest {
  session_id: string;
  rating: 'good' | 'bad';
  issue_type?: 'inaccurate' | 'tool_error' | 'delegation_error' | 'other';
  comment?: string;                  // ≤ 1000
  agent_id?: string;
  message_snippet?: string;          // ≤ 500
}
```

---

## 17. 健康检查 / 指标（公开）

```
GET /api/v1/health             // { status, details: { database, ... } }
GET /api/v1/health/metrics     // Prometheus text format（兼容 /metrics）
```

> `status: healthy | degraded`；数据库异常时返回 `degraded`。

---

## 18. 调试接口（开发环境）

> **生产环境应禁用**。鉴权：需登录 + 会话所有者（除 `/mcp` 系列）。

```
GET /api/v1/debug/trace/{session_id}       // 最近一次 LLM trace
GET /api/v1/debug/session/{session_id}     // 会话快照
GET /api/v1/debug/mcp                       // MCP 服务器列表
GET /api/v1/debug/mcp/select?query=...      // MCP 工具检索
GET /api/v1/debug/task/{session_id}        // 任务快照
```

---

## 通用错误格式

```json
{
  "detail": "错误描述信息",
  "code": "CORRELATION_WEEKLY_ONLY",
  "trace_id": "abc123"
}
```

| 状态码 | 含义 | 前端处理 |
|--------|------|----------|
| 400 | 请求参数错误 | 检查表单 |
| 401 | 未登录 / Cookie 失效 | 跳转登录页 |
| 403 | 无权限 | 提示"无权操作" |
| 404 | 资源不存在 | 提示"资源不存在"（不暴露存在性）|
| 409 | 业务冲突 | 提示具体原因（如"已确认其他方案"）|
| 422 | 参数校验失败 | 显示字段错误 |
| 429 | 限流 | Toast"操作太频繁"，不自动重试 |
| 500 | 服务器内部错误 | Toast"服务繁忙，请稍后再试" |
| 503 | 外部服务不可用 | Toast"外部服务暂不可用" |

> **业务错误码**（`code` 字段）存放在 `YunheException.details.code`（dict），由 handler 翻译到响应。

---

## 限流规则

全局：**每用户 + IP 每 60 秒 60 个请求**（按 API 前缀聚合）。

收到 429：建议显示 Toast"操作太频繁，请稍后再试"，**不自动重试**。

---

## 前端开发注意事项

### Vite 代理（已配置）

```typescript
// vite.config.ts —— 已配置
server: { proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true } } }
```

### 前端路由建议

| 路由 | 页面 | 主要接口 |
|------|------|----------|
| `/` | 首页 / 对话 | `chat/stream` + `agents` + `session/{id}/confirm-status` |
| `/login` `/register` | 登录 / 注册 | `auth/*` |
| `/news/admin` | 新闻来源治理 | `admin/news/*`（**管理员**）|
| `/itineraries` | 行程列表 | `itineraries` + `travel/archives` |
| `/itineraries/:id` | 行程详情 | `itineraries/:id` + `session/:id/confirm-status` |
| `/itineraries/:id/edit` | 草稿编辑 | `travel/drafts/*` |
| `/stock` | 股票复盘 | `stock/*`（含 `review` + `tasks/{id}` 轮询）|
| `/shared/:token` | 分享页 | `share/:token` |
| `/agents` | 智能体管理 | `agents` CRUD |
| `/memories` | 记忆面板 | `memories` |

### 错误处理模板

```typescript
async function apiCall<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await http.request(path, init)
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as ApiError
    if (res.status === 401) {
      window.location.href = '/login'
    } else if (res.status === 429) {
      // Toast
    }
    throw new Error(err.detail || '请求失败')
  }
  return res.json() as Promise<T>
}
```

---

## 变更记录

| 版本 | 日期 | 主要变更 |
|------|------|----------|
| v1.0 | 2026-06 | 初版：60 个接口，Bearer Token，行程 / 相册 / 游记 |
| v1.1 | 2026-07-05 | 新增学术智能体、自驾费用 / 天气工具、LLM 降级链；多方案 `sightseeing` / `budget` |
| **v1.2** | **2026-08-01** | **全量重写**：79 端点；移除相册 / 游记 / 行程比较 / 打卡 / 实际花费 / 飞猪 / 情感 / 旧 Bearer 主路径；新增股票复盘（14 端点）+ 新闻来源治理（5 端点）+ 旅行草稿 / 存档（8 端点）+ Cookie + CSRF 主路径 / Bearer 非浏览器场景说明 + 组合根 / 架构守卫引用；`/auth/me` + `PATCH /sessions/{id}/mode` + `POST /news/hotspots/{id}/analysis-sessions`；SSE 新增 `evidence` 事件 |
