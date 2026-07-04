# 云合 API 接口文档（前端开发参考）

> 本文档专为前端开发者编写，包含所有 60 个接口的请求/响应格式、TypeScript 类型定义、代码示例和常见错误处理。

---

## 基础信息

| 项目 | 说明 |
|------|------|
| 基础地址 | `http://localhost:8000`（开发环境） |
| Content-Type | `application/json`（除文件上传外） |
| 字符编码 | UTF-8 |
| 单文件上传 | `multipart/form-data` |

### 项目启动

```bash
# 后端（端口 8000）
uvicorn api.server:app --reload --host 0.0.0.0 --port 8000

# 前端（端口 5173，Vite 自动代理 /api → localhost:8000）
cd frontend && npm run dev
```

---

## 鉴权机制

### Token 获取

用户注册或登录成功后，响应中返回 `token` 字段。前端应将其存入 `localStorage`：

```typescript
// 登录成功后
const { token, user_id, username } = await login(username, password);
localStorage.setItem('claw_token', token);
localStorage.setItem('claw_user_id', user_id);
```

### Token 使用

**除了标注"公开"的接口外，所有请求必须在 Header 中携带 Token：**

```typescript
// 方式一：axios 全局拦截器（推荐）
axios.interceptors.request.use(config => {
  const token = localStorage.getItem('claw_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 方式二：fetch 手动携带
fetch('/api/sessions', {
  headers: {
    'Authorization': `Bearer ${localStorage.getItem('claw_token')}`,
    'Content-Type': 'application/json',
  },
});
```

### Token 过期处理

401 响应表示 Token 无效或过期，前端应统一处理跳转登录页：

```typescript
axios.interceptors.response.use(
  response => response,
  error => {
    if (error.response?.status === 401) {
      localStorage.removeItem('claw_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);
```

### 公开接口（无需 Token）

以下路径无需携带 Token：

| 路径 | 说明 |
|------|------|
| `POST /api/auth/register` | 用户注册 |
| `POST /api/auth/login` | 用户登录 |
| `GET /api/trending` | 热门推荐 |
| `GET /api/shared/{token}` | 查看分享行程 |
| `GET /health` | 健康检查 |
| `GET /metrics` | Prometheus 指标 |
| `/debug/*` | 调试接口（开发环境） |

---

## 通用 TypeScript 类型

```typescript
// ===== 通用类型 =====

/** 用户信息 */
interface UserInfo {
  user_id: string;
  username: string;
  token: string;
}

/** 错误响应（所有 4xx/5xx 统一格式） */
interface ErrorResponse {
  detail: string;
}

/** 分页查询参数 */
interface PaginationParams {
  limit?: number;   // 默认 10
  offset?: number;  // 默认 0
}
```

---

## 1. 认证模块

### 1.1 用户注册

```
POST /api/auth/register
```

**公开接口**

```typescript
interface RegisterRequest {
  username: string;   // 必填，2-32 字符，只允许字母数字下划线
  password: string;   // 必填，至少 6 位
}

// 请求
const res = await axios.post<UserInfo>('/api/auth/register', {
  username: 'zhangsan',
  password: '123456',
});

// 成功响应
{
  "user_id": "ee3d2c304e265393",
  "username": "zhangsan",
  "token": "3a3c205da3b2aedd..."
}
```

| 状态码 | 说明 |
|--------|------|
| 200 | 注册成功，返回用户信息和 Token |
| 400 | 用户名长度不符（需要 2-32 位）/ 密码过短（需 ≥6 位）/ 用户名已存在 |

---

### 1.2 用户登录

```
POST /api/auth/login
```

**公开接口**

```typescript
// 请求
const res = await axios.post<UserInfo>('/api/auth/login', {
  username: 'zhangsan',
  password: '123456',
});

// 成功响应（格式同注册）
{
  "user_id": "ee3d2c304e265393",
  "username": "zhangsan",
  "token": "3a3c205da3b2aedd..."
}
```

| 状态码 | 说明 |
|--------|------|
| 200 | 登录成功 |
| 401 | 用户名或密码错误 |

---

## 2. 对话模块

> **这是前端最主要使用的模块**。支持同步和 SSE 流式两种模式。推荐使用流式接口以获得更好的用户体验。

### 2.1 发送消息（同步）

```
POST /api/chat
```

```typescript
interface ChatRequest {
  session_id: string;         // 必填，会话 ID
  message: string;            // 必填，用户消息，1-8000 字符
  user_id?: string;           // 可选，Token 鉴权时后端自动填充，无需手动传入
  agent_id?: string;          // 可选，指定使用的智能体 ID（travel / yunhe / 自定义 ID）
}

interface ChatResponse {
  status: string;             // "completed"
  reply: string;              // AI 回复内容
}

// 请求
const res = await axios.post<ChatResponse>('/api/chat', {
  session_id: 'current-session-id',
  message: '帮我规划一个北京3日游',
  agent_id: 'travel',         // 可选，不传则使用默认智能体（yunhe）
});

// 成功响应
{
  "status": "completed",
  "reply": "为您规划北京3日游行程如下..."
}
```

| 状态码 | 说明 |
|--------|------|
| 200 | 对话完成 |
| 429 | 请求过于频繁（全局限流：60次/分钟/用户） |

---

### 2.2 流式对话（SSE — 推荐）

```
POST /api/chat/stream
```

**请求体与 `/api/chat` 完全相同。**

**这是核心对话接口，响应为 Server-Sent Events (SSE) 流。**

#### SSE 事件类型

| 事件 type | data 内容 | 触发时机 | 前端处理建议 |
|-----------|-----------|----------|-------------|
| `thinking` | `"thinking"` | Agent 开始推理 | 显示"思考中..."动画 |
| `tool_status` | 文本，如 `"正在搜索机票..."`、`"正在查询天气..."`、`"正在估算自驾费用..."` | 工具开始执行 | 显示工具调用状态指示器 |
| `chunk` | 文本片段 | AI 逐词输出 | **追加**到消息内容末尾 |
| `actions` | JSON 对象数组 | Agent 输出操作卡片 | 渲染操作按钮（见下方说明） |
| `done` | `"completed"` + `trace_id` | 对话正常结束 | 停止流式渲染，保存完整回复 |
| `error` | 错误信息 + `trace_id` | 发生错误 | 显示错误提示 |

#### `actions` 事件详解（v1.1 更新）

旅行智能体在生成行程后，会推送 `actions` 事件，前端据此渲染操作按钮：

```typescript
interface AgentActionCard {
  type: string;             // 操作类型，如 'generate_itinerary'
  label: string;            // 按钮显示文本
  itinerary_id?: number;    // 关联行程 ID
  session_id?: string;      // 关联会话 ID
  plan_type?: string;       // 方案类型：'sightseeing' | 'budget'（v1.1 新增）
}

// actions 事件 data 格式
// data: [{"type":"generate_itinerary","label":"查看行程","itinerary_id":42,"plan_type":"sightseeing"}]
```

**多方案锚点协议**：LLM 回复末尾会注入 HTML 注释锚点 `<!--MULTI_PLAN:plan1=sightseeing,plan2=budget-->`，前端解析锚点后渲染"景点打卡型/经济实惠型"双按钮；若已确认方案，则显示确认状态卡片 + 撤销按钮。

#### 前端实现示例

```typescript
/**
 * 流式对话 — 推荐实现
 * 使用 fetch + ReadableStream 处理 SSE
 */
async function chatStream(
  sessionId: string,
  message: string,
  agentId?: string,
  onChunk?: (text: string) => void,        // 收到文本片段回调
  onThinking?: () => void,                   // 开始思考回调
  onToolStatus?: (status: string) => void,   // 工具状态回调
  onDone?: () => void,                       // 完成回调
  onError?: (error: string) => void,         // 出错回调
): Promise<string> {
  const token = localStorage.getItem('claw_token');
  let fullReply = '';

  const response = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify({
      session_id: sessionId,
      message: message,
      agent_id: agentId,
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || '请求失败');
  }

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';  // 保留不完整的行

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const jsonStr = line.slice(6).trim();
      if (!jsonStr) continue;

      try {
        const event: SSEEvent = JSON.parse(jsonStr);
        switch (event.type) {
          case 'thinking':
            onThinking?.();
            break;
          case 'tool_status':
            onToolStatus?.(event.data);
            break;
          case 'chunk':
            fullReply += event.data;
            onChunk?.(event.data);
            break;
          case 'done':
            onDone?.();
            break;
          case 'error':
            onError?.(event.data);
            break;
        }
      } catch (e) {
        // 非 JSON 行忽略
      }
    }
  }

  return fullReply;
}

// 在 React 组件中使用
const [reply, setReply] = useState('');
const [status, setStatus] = useState<'idle' | 'thinking' | 'tool' | 'streaming'>('idle');
const [toolStatus, setToolStatus] = useState('');

const handleSend = async (message: string) => {
  setStatus('thinking');
  setReply('');
  try {
    await chatStream(
      sessionId, message, 'travel',
      (chunk) => {
        setStatus('streaming');
        setReply(prev => prev + chunk);
      },
      () => setStatus('thinking'),
      (status) => { setStatus('tool'); setToolStatus(status); },
      () => setStatus('idle'),
      (error) => { setStatus('idle'); alert(error); },
    );
  } catch (err) {
    setStatus('idle');
  }
};
```

#### TypeScript 类型定义

```typescript
interface SSEEvent {
  type: 'thinking' | 'tool_status' | 'chunk' | 'actions' | 'done' | 'error';
  data: string;
  trace_id?: string;  // done 和 error 事件携带
}
```

#### 注意事项

- **流式连接默认不超时**，如果用户切换页面应及时 `reader.cancel()` 或 `AbortController.abort()`
- `done` 事件后流会自动关闭
- 如果 LLM 响应很快（如命中缓存），可能直接收到 `done` 而没有 `chunk`，前端应兼容此情况

---

## 3. 会话模块

> 会话（Session）是对话的容器。用户在左侧栏选择一个会话，对话消息绑定在该会话下。

### 3.1 获取会话列表

```
GET /api/sessions
```

```typescript
interface SessionItem {
  session_id: string;
  title: string;           // 会话标题（通常是第一条用户消息的摘要）
  created_at: string;      // ISO 8601
  updated_at: string;      // ISO 8601
  message_count: number;   // 消息数量
}

// 请求
const res = await axios.get<{ sessions: SessionItem[] }>('/api/sessions');

// 响应
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

列表按 `updated_at` 降序排列，最近活跃的会话在前。

---

### 3.2 创建会话

```
POST /api/sessions
```

```typescript
// 请求（无请求体）
const res = await axios.post<{ session_id: string; user_id: string }>('/api/sessions');

// 响应
{
  "session_id": "a1b2c3d4e5f6",
  "user_id": "ee3d2c304e265393"
}
```

**使用流程**：页面加载时自动创建一个新会话，获得 `session_id` 后用于后续对话请求。

---

### 3.3 删除会话

```
DELETE /api/sessions/{session_id}
```

```typescript
const res = await axios.delete(`/api/sessions/${sessionId}`);

// 响应
{ "detail": "已删除" }
```

**注意**：删除会话会同时删除该会话下的所有消息，不可恢复。

---

### 3.4 获取会话消息历史

```
GET /api/sessions/{session_id}/messages
```

```typescript
interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
}

// 请求
const res = await axios.get<{ messages: ChatMessage[] }>(
  `/api/sessions/${sessionId}/messages`
);

// 响应
{
  "messages": [
    { "role": "user", "content": "帮我规划一个东京5日游", "timestamp": "2026-06-01T10:00:00" },
    { "role": "assistant", "content": "好的，为您规划东京5日游...", "timestamp": "2026-06-01T10:01:00" }
  ]
}
```

**用途**：用户点击某个历史会话时，加载该会话的完整对话记录。

---

### 3.5 确认方案

```
POST /api/session/{session_id}/confirm-plan
```

> 多方案对比功能：当旅行智能体生成两套行程方案（景点打卡型 + 经济实惠型）后，用户选择确认其中一套。

**幂等**：重复确认同一方案返回 200，确认不同方案返回 409。

```typescript
interface ConfirmPlanRequest {
  plan_type: 'sightseeing' | 'budget';  // 必填，确认哪套方案
  itinerary_id?: string;               // 可选，关联行程 ID（同步更新行程确认状态）
}

interface ConfirmPlanResponse {
  confirmed_plan: string;         // 'sightseeing' 或 'budget'
  itinerary_id: string;
  confirmed_at: string;           // ISO 8601
}

// 请求
const res = await axios.post<ConfirmPlanResponse>(
  `/api/session/${sessionId}/confirm-plan`,
  { plan_type: 'sightseeing', itinerary_id: '42' }
);

// 成功响应
{
  "confirmed_plan": "sightseeing",
  "itinerary_id": "42",
  "confirmed_at": "2026-07-04T10:30:00"
}
```

| 状态码 | 说明 |
|--------|------|
| 200 | 确认成功（首次确认或重复确认同一方案） |
| 409 | 已确认其他方案（需先撤销再确认新方案） |

**前端处理**：确认成功后，方案按钮区从"双按钮"切换为"已确认状态卡片 + 撤销按钮"。

---

### 3.6 撤销方案确认

```
POST /api/session/{session_id}/revoke-confirm
```

```typescript
interface RevokeConfirmResponse {
  message: string;  // "确认已撤销，可重新选择方案"
}

// 请求
const res = await axios.post<RevokeConfirmResponse>(
  `/api/session/${sessionId}/revoke-confirm`,
  { itinerary_id: '42' }  // 可选，同步清除行程确认状态
);

// 成功响应
{
  "message": "确认已撤销，可重新选择方案"
}
```

| 状态码 | 说明 |
|--------|------|
| 200 | 撤销成功 |
| 404 | 当前无确认方案可撤销 |

**前端处理**：撤销后恢复双按钮选择界面。

---

### 3.7 查询方案确认状态

```
GET /api/session/{session_id}/confirm-status
```

```typescript
interface ConfirmStatusResponse {
  confirmed_plan: string | null;   // 'sightseeing' / 'budget' / null（未确认）
  confirmed_at: string | null;     // ISO 8601 或 null
  itinerary_id?: number;           // 关联行程 ID
}

// 请求
const res = await axios.get<ConfirmStatusResponse>(
  `/api/session/${sessionId}/confirm-status`
);

// 未确认
{
  "confirmed_plan": null,
  "confirmed_at": null
}

// 已确认景点打卡型
{
  "confirmed_plan": "sightseeing",
  "confirmed_at": "2026-07-04T10:30:00",
  "itinerary_id": 42
}
```

**前端使用**：切换会话时调用此接口，恢复确认状态的 UI 展示。

---

## 4. 智能体模块

> 智能体（Agent）是对话背后的"大脑"。系统内置 `travel`（旅行助手）和 `yunhe`（通用助手），用户可创建自定义智能体。

### 4.1 获取智能体列表

```
GET /api/agents
```

```typescript
interface AgentConfig {
  id: string;              // 智能体唯一标识
  name: string;            // 显示名称
  description: string;     // 描述
  icon: string;            // emoji 图标，如 "✈️"
  skills: string[];        // 关联技能列表，如 ["amap-maps"]
  mcp_servers: string[];   // 关联 MCP 服务器列表
  system_prompt: string;   // 系统提示词（仅自定义智能体）
  welcome_message: string; // 开场欢迎语
  temperature: number;     // 温度参数 0.0-2.0
  is_public: boolean;      // 是否公开
  source: 'builtin' | 'custom'; // 来源
}

// 请求
const res = await axios.get<{
  builtin: AgentConfig[];
  custom: AgentConfig[];
  public: AgentConfig[];
}>('/api/agents');

// 响应示例
{
  "builtin": [
    {
      "id": "travel",
      "name": "旅行规划助手",
      "description": "处理行程规划、景点推荐、机票酒店搜索等",
      "icon": "✈️",
      "skills": ["amap-maps", "fliggy-travel", "q-weather"],
      "mcp_servers": [],
      "system_prompt": "",
      "welcome_message": "你好！我是旅行规划助手，告诉我你想去哪里？",
      "temperature": 0.7,
      "is_public": true,
      "source": "builtin"
    },
    {
      "id": "yunhe",
      "name": "云合",
      "description": "通用智能体，日常问答/知识查询/写作/委派任务",
      "icon": "☁️",
      "skills": [],
      "mcp_servers": [],
      "system_prompt": "",
      "welcome_message": "你好！我是云合，有什么可以帮你的？",
      "temperature": 0.7,
      "is_public": true,
      "source": "builtin"
    },
    {
      "id": "academic",
      "name": "学术搜索助手",
      "description": "论文搜索、引用分析、创新点挖掘、可行性评估",
      "icon": "📚",
      "skills": [],
      "mcp_servers": ["arxiv-search", "web-search"],
      "system_prompt": "",
      "welcome_message": "你好！我是学术搜索助手，帮你搜索论文、分析引用。告诉我你的研究主题？",
      "temperature": 0.7,
      "is_public": true,
      "source": "builtin"
    }
  ],
  "custom": [
    /* 当前用户自定义的智能体 */
  ],
  "public": [
    /* 社区公开的智能体（可克隆） */
  ]
}
```

**前端使用**：
- `builtin`：在对话界面顶部显示智能体选择器，切换不同智能体
- `custom`：在"我的智能体"页面展示，支持编辑
- `public`：在"智能体市场"页面展示，支持克隆到自己的工作区

---

### 4.2 创建自定义智能体

```
POST /api/agents/custom
```

```typescript
interface CreateAgentRequest {
  name: string;              // 必填，1-64 字符
  system_prompt: string;     // 必填，1-8000 字符，定义智能体行为
  description?: string;      // 选填，最多 500 字符
  icon?: string;             // 选填，emoji，默认 "🤖"
  skills?: string[];         // 选填，最多 20 个技能名
  mcp_servers?: string[];    // 选填，最多 20 个 MCP 服务名
  welcome_message?: string;  // 选填，最多 500 字符
  temperature?: number;      // 选填，0.0-2.0，默认 0.7
  is_public?: boolean;       // 选填，默认 false
}

// 请求
const res = await axios.post<AgentConfig>('/api/agents/custom', {
  name: '美食推荐师',
  description: '专门推荐各地美食和餐厅',
  icon: '🍔',
  system_prompt: '你是一个专业的美食推荐师...',
  skills: ['amap-maps'],
  welcome_message: '你好！想吃什么？告诉我你的口味偏好！',
  temperature: 0.8,
});

// 响应：返回创建的智能体完整配置对象
```

| 状态码 | 说明 |
|--------|------|
| 200 | 创建成功 |
| 400 | 参数校验失败（名称/提示词长度不合法） |

---

### 4.3 获取自定义智能体详情

```
GET /api/agents/custom/{agent_id}
```

```typescript
const res = await axios.get<AgentConfig>(`/api/agents/custom/${agentId}`);
```

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 404 | 智能体不存在 |

---

### 4.4 更新自定义智能体

```
PUT /api/agents/custom/{agent_id}
```

```typescript
// 请求：所有字段均可选，只传需要更新的字段
const res = await axios.put<AgentConfig>(`/api/agents/custom/${agentId}`, {
  name: '新名称',
  system_prompt: '更新的提示词',
  is_public: true,
});
```

| 状态码 | 说明 |
|--------|------|
| 200 | 更新成功 |
| 403 | 无权修改（仅创建者可修改自己的智能体） |
| 404 | 智能体不存在 |

---

### 4.5 删除自定义智能体

```
DELETE /api/agents/custom/{agent_id}
```

```typescript
const res = await axios.delete(`/api/agents/custom/${agentId}`);

// 响应
{ "status": "deleted" }
```

| 状态码 | 说明 |
|--------|------|
| 200 | 删除成功 |
| 403 | 无权删除 |
| 404 | 智能体不存在 |

---

### 4.6 克隆智能体

```
POST /api/agents/custom/{agent_id}/clone
```

```typescript
const res = await axios.post<AgentConfig>(`/api/agents/custom/${agentId}/clone`);

// 克隆后的智能体名称会自动加 "(克隆)" 后缀
// 状态为 "draft"，is_public = false
```

**用途**：从"智能体市场"克隆公开智能体到"我的智能体"工作区。

---

## 5. 技能模块

### 5.1 获取技能列表

```
GET /api/skills
```

```typescript
interface SkillInfo {
  name: string;          // 技能唯一名，如 "amap-maps"
  display_name: string;  // 显示名称，如 "高德地图"
  description: string;
  version: string;
}

const res = await axios.get<{ skills: SkillInfo[] }>('/api/skills');
```

**用途**：创建自定义智能体时，展示可选的技能列表（多选框）。

---

### 5.2 获取技能详情

```
GET /api/skills/{skill_name}
```

```typescript
const res = await axios.get<SkillDetail>(`/api/skills/${skillName}`);
// 返回技能的完整配置，包含 instructions、参数等
```

| 状态码 | 说明 |
|--------|------|
| 404 | 技能不存在 |

---

## 6. MCP 服务器模块

> MCP（Model Context Protocol）服务器提供外部工具能力，如 Web 搜索。前端可展示可用的 MCP 服务列表。

### 6.1 获取 MCP 服务器列表

```
GET /api/mcp/servers
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
  adapter_available: boolean;  // 适配器是否可用
}

const res = await axios.get<{ servers: MCPServerInfo[] }>('/api/mcp/servers');
```

---

### 6.2 获取 MCP 服务器详情

```
GET /api/mcp/servers/{server_id}
```

返回单个 MCP 服务器的完整配置和工具列表。

---

### 6.3 获取 MCP 服务器工具列表

```
GET /api/mcp/servers/{server_id}/tools
```

```typescript
const res = await axios.get<{
  server_id: string;
  tools: MCPToolInfo[];
}>(`/api/mcp/servers/${serverId}/tools`);
```

---

## 7. 行程模块

> 行程是最核心的资源。AI 对话的结果通常会生成一个行程对象，包含多天的活动和花费详情。

### 7.1 行程数据结构

```typescript
// —— 完整的行程对象 ——
interface Itinerary {
  id: number;
  user_id: string;
  title: string;           // 行程标题，如 "东京5日游"
  destination: string;     // 目的地
  start_date: string;      // 开始日期，ISO 8601（可选）
  end_date: string;        // 结束日期
  budget: string;          // 预算描述文本，如 "约8000元/人"
  status: string;          // 状态：planning / in_progress / completed
  session_id: string;      // 关联会话 ID
  raw_content: string;     // 原始 AI 生成内容（Markdown）
  created_at: string;
  updated_at: string;
  days: DayPlan[];         // 每日计划
  // —— 多方案对比字段（v1.1 新增） ——
  plans_json?: string;           // JSON 序列化的 Plan[] 数组
  confirmed_plan?: string | null; // 已确认方案标识：'sightseeing' / 'budget' / null
  confirmed_at?: string | null;   // 确认时间，ISO 8601
  recommended_plan?: string | null; // 推荐方案标识
}

interface DayPlan {
  day_index: number;       // 第几天，从 0 开始
  date: string;
  title: string;           // 当天标题，如 "浅草·秋叶原"
  summary: string;         // 当天摘要
  activities: Activity[];  // 活动列表
}

interface Activity {
  id: number;
  time_slot: string;       // 时间段，如 "09:00-12:00"
  title: string;           // 活动标题
  location: string;        // 地点
  description: string;     // 详细描述
  cost: number;            // 预算花费（元）
  actual_cost: number;     // 实际花费（元），初始为 0
  tips: string;            // 小贴士
  image_url: string;       // 图片 URL
  checked_in: boolean;     // 是否已打卡
}

// —— 多方案对比类型（v1.1 新增） ——

/** 方案类型枚举 */
type PlanType = 'sightseeing' | 'budget' | 'single';

/** 出行方式枚举 */
type TransportMode = 'flight' | 'train' | 'drive';

/** 费用分项 */
interface CostBreakdown {
  transport: number;       // 交通费用
  hotel: number;           // 住宿费用
  food: number;            // 餐饮费用
  tickets: number;         // 门票费用
  shopping: number;        // 购物预估
  other: number;           // 其他费用
  total: number;           // 总计
}

/** 出行方式选项 */
interface TransportOption {
  mode: TransportMode;     // 出行方式
  label: string;           // 显示名称，如 "飞机"、"高铁"、"自驾"
  price_range: string;     // 价格区间，如 "800-1500元"
  duration: string;        // 耗时，如 "2h"
  pros: string[];          // 优势
  cons: string[];          // 劣势
}

/** 单套方案 */
interface Plan {
  plan_type: PlanType;       // 方案类型
  plan_label: string;        // 方案显示名，如 "景点打卡型"、"经济实惠型"
  transport: TransportOption; // 出行方式
  cost_breakdown: CostBreakdown; // 费用明细
  version: number;           // 方案版本号
}

/** 多方案行程（统一模型） */
interface MultiPlanItinerary {
  id: string;
  session_id: string;
  user_id: string;
  destination: string;
  plans: Plan[];                // 方案列表（1=单方案，2=双方案对比）
  recommended_plan: string | null; // 推荐方案标识
  confirmed_plan: string | null;   // 已确认方案标识
  confirmed_at: string | null;     // 确认时间
}
```

---

### 7.2 创建行程

```
POST /api/itineraries
```

```typescript
interface CreateItineraryRequest {
  title: string;
  destination: string;
  start_date?: string;
  end_date?: string;
  budget?: string;
  session_id?: string;
  raw_content?: string;     // AI 生成的原始 Markdown 内容
  status?: string;          // 默认 "planning"
  days?: DayPlan[];         // 天数和活动详情
}

const res = await axios.post<Itinerary>('/api/itineraries', {
  title: '东京5日游',
  destination: '东京',
  start_date: '2026-07-01',
  end_date: '2026-07-05',
  budget: '约8000元/人',
  session_id: 'abc123',
});
```

---

### 7.3 获取行程列表

```
GET /api/itineraries
```

```typescript
const res = await axios.get<{ itineraries: ItinerarySummary[] }>('/api/itineraries');

// 响应（列表视图，不含 days 详情）
interface ItinerarySummary {
  id: number;
  title: string;
  destination: string;
  start_date: string;
  end_date: string;
  budget: string;
  status: string;
  created_at: string;
  updated_at: string;
}
```

**注意**：列表接口返回的行程**不包含 `days` 详情**，需点击进入详情页后用 7.4 接口加载。

---

### 7.4 获取行程详情

```
GET /api/itineraries/{itinerary_id}
```

```typescript
// 此接口返回完整的行程对象，包含所有 days 和 activities
const res = await axios.get<Itinerary>(`/api/itineraries/${itineraryId}`);
```

| 状态码 | 说明 |
|--------|------|
| 404 | 行程不存在 |

---

### 7.5 更新行程

```
PUT /api/itineraries/{itinerary_id}
```

```typescript
// 请求体与创建接口相同，所有字段可选
const res = await axios.put<Itinerary>(`/api/itineraries/${itineraryId}`, {
  title: '东京深度游',       // 只更新标题
  status: 'in_progress',      // 修改状态
});
```

---

### 7.6 删除行程

```
DELETE /api/itineraries/{itinerary_id}
```

```typescript
const res = await axios.delete(`/api/itineraries/${itineraryId}`);
// { "detail": "已删除" }
```

---

### 7.7 行程对比

```
POST /api/itineraries/compare
```

```typescript
interface CompareRequest {
  ids: number[];   // 必填，2-4 个行程 ID
}

interface CompareResult {
  id: number;
  title: string;
  destination: string;
  budget_total: number;
  actual_total: number;
  days_count: number;
  activities_count: number;
  days: { day_index: number; title: string; budget: number; actual: number; activities: Activity[] }[];
}

const res = await axios.post<{ itineraries: CompareResult[] }>(
  '/api/itineraries/compare',
  { ids: [1, 2, 3] }
);
```

| 状态码 | 说明 |
|--------|------|
| 400 | ID 数量不在 2-4 范围内 |

---

### 7.8 花费统计

```
GET /api/itineraries/{itinerary_id}/expense-summary
```

```typescript
interface ExpenseSummary {
  itinerary_id: string;
  title: string;
  budget_text: string;
  budget_total: number;
  actual_total: number;
  remaining: number;         // 剩余预算
  days: {
    day_index: number;
    title: string;
    budget: number;
    actual: number;
    activities: {
      id: number;
      title: string;
      budget: number;
      actual: number;
      checked_in: boolean;
    }[];
  }[];
}

const res = await axios.get<ExpenseSummary>(
  `/api/itineraries/${itineraryId}/expense-summary`
);
```

---

### 7.9 活动打卡

```
PATCH /api/itineraries/{itinerary_id}/activities/{activity_id}/checkin
```

```typescript
interface CheckinRequest {
  checked_in?: boolean;  // 默认 true；传 false 取消打卡
}

const res = await axios.patch<Activity>(
  `/api/itineraries/${itineraryId}/activities/${activityId}/checkin`,
  { checked_in: true }
);
```

---

### 7.10 删除活动

```
DELETE /api/itineraries/{itinerary_id}/activities/{activity_id}
```

```typescript
const res = await axios.delete(
  `/api/itineraries/${itineraryId}/activities/${activityId}`
);
// { "detail": "已删除" }
```

---

### 7.11 更新活动实际花费

```
PATCH /api/itineraries/{itinerary_id}/activities/{activity_id}/cost
```

```typescript
const res = await axios.patch<Activity>(
  `/api/itineraries/${itineraryId}/activities/${activityId}/cost`,
  { actual_cost: 150 }  // 单位：元
);
```

---

### 7.12 创建分享链接

```
POST /api/itineraries/{itinerary_id}/share
```

```typescript
interface CreateShareRequest {
  expires_at?: string;  // 可选，过期时间，ISO 8601
}

interface ShareResponse {
  token: string;
  itinerary_id: string;
}

const res = await axios.post<ShareResponse>(
  `/api/itineraries/${itineraryId}/share`,
  { expires_at: '2026-12-31T23:59:59' }  // 可选
);

// 前端生成分享链接：`${window.location.origin}/shared/${res.data.token}`
```

---

### 7.13 获取分享链接列表

```
GET /api/itineraries/{itinerary_id}/shares
```

```typescript
interface ShareInfo {
  token: string;
  created_at: string;
  view_count: number;
}

const res = await axios.get<{ shares: ShareInfo[] }>(
  `/api/itineraries/${itineraryId}/shares`
);
```

---

### 7.14 删除分享链接

```
DELETE /api/itineraries/{itinerary_id}/shares/{token}
```

```typescript
const res = await axios.delete(
  `/api/itineraries/${itineraryId}/shares/${token}`
);
```

---

### 7.15 查看分享行程

```
GET /api/shared/{token}
```

**公开接口，无需鉴权。** 用于分享页面的独立访问。

```typescript
interface SharedItinerary {
  itinerary: Itinerary;       // 完整行程对象
  share_info: {
    view_count: number;        // 浏览次数
    created_at: string;
  };
}

const res = await axios.get<SharedItinerary>(`/api/shared/${shareToken}`);
```

**注意**：分享页面的图片 URL 需要通过 `/api/album/{file_path}?token={token}` 加载（见 8.8）。

---

## 8. 相册模块

> 每个行程可以上传多张照片，系统自动提取 EXIF 地理位置并在行程地图上标记。

### 8.1 上传照片

```
POST /api/itineraries/{itinerary_id}/photos
```

**Content-Type**: `multipart/form-data`

```typescript
interface PhotoItem {
  id: number;
  file_name: string;         // 原始文件名
  file_size: number;         // 字节
  mime_type: string;         // 如 "image/jpeg"
  description: string;       // 照片描述
  day_index: number;         // 关联第几天，默认 0
  storage_path: string;      // 服务端存储路径
  thumbnail_path: string;    // 缩略图路径
  latitude: number | null;   // EXIF 经纬度
  longitude: number | null;
  ai_description: string;    // AI 生成的照片描述
  tags: string[];            // 标签
  is_cover: boolean;         // 是否封面
  created_at: string;
}

// 前端实现
const formData = new FormData();
files.forEach(file => formData.append('files', file));  // 支持多文件
formData.append('description', '东京塔夜景');
formData.append('day_index', '1');

const res = await axios.post<{ photos: PhotoItem[] }>(
  `/api/itineraries/${itineraryId}/photos`,
  formData,
  { headers: { 'Content-Type': 'multipart/form-data' } }
);
```

**注意**：
- 支持同时上传多张照片（`files` 字段传数组）
- 上传后系统会自动：提取 EXIF 地理位置 → 生成缩略图 → AI 生成描述

---

### 8.2 获取照片列表

```
GET /api/itineraries/{itinerary_id}/photos
```

```typescript
// 可选查询参数
interface PhotoListParams {
  day_index?: number;   // 筛选某天的照片
  tag?: string;         // 按标签筛选
}

interface PhotoListResponse {
  itinerary_id: string;
  photos: PhotoItem[];
  total: number;
  tags: string[];       // 所有可用标签（用于筛选器）
  cover: PhotoItem | null;  // 当前封面照片
}

const res = await axios.get<PhotoListResponse>(
  `/api/itineraries/${itineraryId}/photos`,
  { params: { day_index: 1, tag: '景点' } }
);
```

---

### 8.3 删除照片

```
DELETE /api/itineraries/{itinerary_id}/photos/{photo_id}
```

| 状态码 | 说明 |
|--------|------|
| 200 | 删除成功 |
| 403 | 无权删除此照片 |
| 404 | 照片不存在 |

---

### 8.4 更新照片信息

```
PATCH /api/itineraries/{itinerary_id}/photos/{photo_id}
```

```typescript
const res = await axios.patch<PhotoItem>(
  `/api/itineraries/${itineraryId}/photos/${photoId}`,
  {
    description: '更新后的描述',
    day_index: 2,
    tags: ['景点', '新标签'],
  }
);
```

---

### 8.5 设置封面照片

```
POST /api/itineraries/{itinerary_id}/photos/{photo_id}/cover
```

```typescript
// 无请求体
const res = await axios.post<PhotoItem>(
  `/api/itineraries/${itineraryId}/photos/${photoId}/cover`
);
// 返回设置为封面后的照片对象
```

---

### 8.6 获取照片地理位置

```
GET /api/itineraries/{itinerary_id}/photos/map
```

```typescript
interface PhotoMarker {
  photo_id: number;
  latitude: number;
  longitude: number;
  description: string;
  day_index: number;
  thumbnail_path: string;
}

const res = await axios.get<{
  itinerary_id: string;
  markers: PhotoMarker[];
}>(`/api/itineraries/${itineraryId}/photos/map`);
```

**用途**：在行程地图上用照片缩略图标记拍摄地点（Leaflet 自定义 marker）。

---

### 8.7 生成游记

```
POST /api/itineraries/{itinerary_id}/travelogue
```

```typescript
const res = await axios.post<{
  itinerary_id: string;
  content: string;           // Markdown 格式游记
}>(`/api/itineraries/${itineraryId}/travelogue`);
```

**用途**：基于行程数据和上传照片，AI 自动生成一篇游记（Markdown 格式，可在前端用 Markdown 渲染器展示）。

---

### 8.8 获取相册图片文件

```
GET /api/album/{file_path}
```

**关键**：前端 `<img>` 标签无法携带 `Authorization` Header，需要通过 URL 参数传递 Token：

```tsx
// 推荐方案：封装图片组件
function AlbumImage({ filePath, token }: { filePath: string; token: string }) {
  const src = `/api/album/${filePath}?token=${encodeURIComponent(token)}`;
  return <img src={src} alt="" />;
}

// 或者使用 thumbnail_path
const thumbnailUrl = `/api/album/${photo.thumbnail_path}?token=${token}`;
```

**响应**：图片文件的二进制数据（JPEG/PNG/WebP 等）。

---

## 9. 地理编码模块

> 将地址文本转换为经纬度坐标，用于地图标记。

### 9.1 国内地址批量编码

```
POST /api/geocode
```

```typescript
interface GeocodeRequest {
  addresses: string[];    // 最多 20 个地址
}

interface GeocodeResult {
  address: string;        // 原始地址
  lng: number;            // 经度
  lat: number;            // 纬度
  formatted: string;      // 格式化后的地址
}

const res = await axios.post<{ results: GeocodeResult[] }>('/api/geocode', {
  addresses: ['北京市海淀区', '上海市浦东新区'],
});

// 响应
{
  "results": [
    { "address": "北京市海淀区", "lng": 116.29845, "lat": 39.95989, "formatted": "北京市海淀区" },
    { "address": "上海市浦东新区", "lng": 121.54434, "lat": 31.22125, "formatted": "上海市浦东新区" }
  ]
}
```

**限制**：最多 20 个地址，使用高德地图 API。

---

### 9.2 国际地址编码

```
POST /api/geocode/intl
```

```typescript
interface IntlGeocodeRequest {
  address: string;        // 必填
  city?: string;          // 城市名（辅助定位）
}

const res = await axios.post<GeocodeResult>('/api/geocode/intl', {
  address: '东京塔',
  city: '东京',
});
```

**查找策略**：先查内置坐标库 → 再调用 Nominatim（OpenStreetMap）。

---

## 10. 记忆模块

> 系统自动从对话中提取用户偏好和旅行经验，分为短期记忆和长期记忆。

### 10.1 获取用户记忆

```
GET /api/memories
```

```typescript
interface MemoryItem {
  id: number;
  category: string;            // preference / fact / experience 等
  category_label: string;      // 中文分类名
  content: string;             // 记忆内容
  experience_tag: string | null;
  extraction_count: number;    // 被提取次数
  last_accessed_at: string;
  created_at: string;
}

interface MemoryResponse {
  long_term: MemoryItem[];     // 长期记忆
  short_term: MemoryItem[];    // 短期记忆
  summary: {
    total_ltm: number;         // 长期记忆总数
    total_stm: number;         // 短期记忆总数
    preferences: number;
    facts: number;
    experiences: number;
  };
}

const res = await axios.get<MemoryResponse>('/api/memories');
```

---

### 10.2 删除记忆

```
DELETE /api/memories/{memory_type}/{memory_id}
```

```typescript
// memory_type: "short_term" | "long_term"
const res = await axios.delete(`/api/memories/long_term/${memoryId}`);
```

---

## 11. 反馈模块

### 11.1 提交对话质量反馈

```
POST /api/feedback
```

```typescript
interface FeedbackRequest {
  session_id: string;            // 必填
  rating: 'good' | 'bad';       // 必填，👍 或 👎
  issue_type?: 'inaccurate'     // 内容不准确
              | 'tool_error'     // 工具调用错误
              | 'delegation_error' // 智能体委派错误
              | 'other';         // 其他，默认值
  comment?: string;              // 反馈意见，最多 1000 字符
  agent_id?: string;             // 关联的智能体 ID
  message_snippet?: string;      // 问题消息片段，最多 500 字符
}

const res = await axios.post<{ status: string; id: string }>('/api/feedback', {
  session_id: 'abc123',
  rating: 'bad',
  issue_type: 'inaccurate',
  comment: '推荐的景点已经关闭了',
  agent_id: 'travel',
  message_snippet: '帮我规划...',
});

// 响应
{ "status": "ok", "id": "fb_abc123" }
```

---

## 12. 热门推荐

### 12.1 获取热门旅行话题

```
GET /api/trending
```

**公开接口**，无需鉴权，可用于首页/未登录状态展示。

```typescript
interface TrendingItem {
  title: string;       // 话题标题
  tag: string;         // 标签，如 "热门"
  summary: string;     // 摘要
  content: string;     // 详细内容
  img: string;         // 图片 URL
  hotScore: string;    // 热度显示，如 "1.2万"
  hotChange: string;   // 热度变化，如 "上升"
}

const res = await axios.get<{ items: TrendingItem[] }>('/api/trending', {
  params: { refresh: true },  // 强制刷新（默认使用缓存）
});
```

**注意**：
- 数据每 30 分钟自动刷新一次
- 传 `refresh=true` 会强制立即刷新（需等待，建议加 loading）

---

## 13. 系统监控

### 13.1 健康检查

```
GET /health
```

**公开接口**，用于前端检测后端是否可用。

```typescript
const res = await axios.get<{
  status: string;
  details: { database: string };
}>('/health');

// 响应
{ "status": "healthy", "details": { "database": "ok" } }
```

---

### 13.2 Prometheus 指标

```
GET /metrics
```

**公开接口**，返回 Prometheus 格式文本数据。前端通常不需要直接调用。

---

## 14. 调试接口

以下接口无需鉴权，仅在开发环境使用，**生产环境应禁用**。

### 14.1 获取会话追踪

```
GET /debug/trace/{session_id}
```

返回会话的 LLM 调用链、工具执行记录等详细追踪信息。

### 14.2 获取会话快照

```
GET /debug/session/{session_id}
```

返回会话的运行时状态快照。

### 14.3 获取记忆快照

```
GET /debug/memory?query=&limit=10&session_id=default
```

### 14.4 MCP 服务器快照

```
GET /debug/mcp
```

### 14.5 MCP 工具选择

```
GET /debug/mcp/select?query=搜索&limit=4
```

### 14.6 获取任务快照

```
GET /debug/task/{session_id}
```

---

## 前端开发注意事项

### CORS 代理配置

开发环境通过 Vite 代理转发 API 请求，避免跨域问题：

```typescript
// vite.config.ts
export default defineConfig({
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
```

### 限流规则

全局限流：**每个用户 + IP 每 60 秒最多 60 个请求**（按 API 前缀聚合）。

收到 429 响应时，建议显示 Toast 提示"操作太频繁，请稍后再试"，不要自动重试。

### 错误处理模板

```typescript
async function apiCall<T>(fn: () => Promise<AxiosResponse<T>>): Promise<T> {
  try {
    const res = await fn();
    return res.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      const status = error.response?.status;
      const detail = error.response?.data?.detail || '未知错误';

      switch (status) {
        case 401:
          // Token 过期 → 跳转登录
          localStorage.removeItem('claw_token');
          window.location.href = '/login';
          break;
        case 429:
          // 限流 → 提示用户
          console.warn('请求过于频繁');
          break;
        case 500:
          console.error('服务器内部错误');
          break;
      }

      throw new Error(detail);
    }
    throw error;
  }
}
```

### 前端路由建议

| 路由 | 页面 | 主要接口 |
|------|------|----------|
| `/` | 首页/对话 | `POST /api/chat/stream` + `GET /api/agents` + `GET /api/session/:id/confirm-status` |
| `/login` / `/register` | 登录/注册 | `POST /api/auth/*` |
| `/itineraries` | 行程列表 | `GET /api/itineraries` |
| `/itineraries/:id` | 行程详情 | `GET /api/itineraries/:id` |
| `/itineraries/:id/album` | 相册 | `GET /api/itineraries/:id/photos` |
| `/compare` | 行程对比 | `POST /api/itineraries/compare` |
| `/shared/:token` | 分享页 | `GET /api/shared/:token` |
| `/agents` | 智能体管理 | `GET /api/agents` + CRUD |
| `/memories` | 记忆面板 | `GET /api/memories` |

---

## 15. 新闻收藏模块

> 用户可以收藏感兴趣的新闻话题，系统会自动提取到短期记忆中，让智能体在对话中能引用用户关注的内容。

### 15.1 获取新闻收藏列表

```
GET /api/news/favorites
```

**鉴权**：需登录

```typescript
interface NewsFavorite {
  id: number;
  title: string;           // 新闻标题
  summary: string;         // 摘要
  content: string;          // 完整内容
  url: string;             // 原始链接
  source: string;          // 来源（如 "微博"、"知乎"）
  tag: string;             // 标签（如 "热门"、"科技"）
  created_at: string;      // 收藏时间
}

const res = await axios.get<{ favorites: NewsFavorite[] }>('/api/news/favorites');
```

**用途**：在收藏页面展示用户已收藏的新闻列表。

---

### 15.2 收藏新闻

```
POST /api/news/favorites
```

**鉴权**：需登录

```typescript
interface NewsFavoriteRequest {
  title: string;           // 必填，1-200 字符
  summary?: string;         // 选填，最多 500 字符
  content?: string;         // 选填，最多 5000 字符
  url?: string;            // 选填，最多 1000 字符
  source?: string;          // 选填，最多 32 字符
  tag?: string;            // 选填，最多 32 字符
}

const res = await axios.post<{ status: string; title: string }>(
  '/api/news/favorites',
  {
    title: '2026年夏季旅游热门目的地TOP10',
    summary: '根据最新数据，2026年夏季...',
    url: 'https://example.com/article/123',
    source: '微博',
    tag: '热门',
  }
);

// 响应
{ "status": "ok", "title": "2026年夏季旅游热门目的地TOP10" }

// 幂等处理：如果已收藏，返回
{ "status": "already_favorited", "title": "..." }
```

**注意**：
- 收藏成功后会自动写入 `short_term_memories`，让智能体在对话中能引用
- 支持幂等操作，重复收藏同一标题会返回 `already_favorited`

---

### 15.3 取消收藏

```
DELETE /api/news/favorites/{favorite_id}
```

**鉴权**：需登录

```typescript
const res = await axios.delete(`/api/news/favorites/${favoriteId}`);

// 响应
{ "detail": "已取消收藏" }
```

| 状态码 | 说明 |
|--------|------|
| 200 | 取消成功 |
| 401 | 未登录 |
| 403 | 无权删除（只能删除自己收藏的） |
| 404 | 收藏记录不存在 |

---

## 通用错误格式

所有接口在出错时返回统一格式：

```json
{
  "detail": "错误描述信息"
}
```

常见 HTTP 状态码：

| 状态码 | 说明 | 前端处理 |
|--------|------|----------|
| 400 | 请求参数错误 | 检查表单数据 |
| 401 | 未登录或 Token 过期 | 跳转登录页 |
| 403 | 无权限操作 | 提示"无权操作" |
| 404 | 资源不存在 | 提示"资源不存在"或跳转 404 页 |
| 429 | 请求频率超限 | 提示"操作太频繁"，等待后重试 |
| 500 | 服务器内部错误 | 提示"服务繁忙，请稍后再试" |
| 503 | 外部服务不可用 | 提示"外部服务暂不可用"（如高德 API 限流） |

---

> **接口总数**：60 个 | **模块数**：15 | **最后更新**：2026-07-05（v1.2 新增学术智能体、自驾费用/天气工具、LLM 降级链；更新确认方案 plan_type 为 sightseeing/budget）
