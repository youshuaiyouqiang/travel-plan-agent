# frontend/src/features/ — 模块记忆

## 职责定位
按业务域组织的 API 客户端与类型契约层（academic/auth/chat/news/travel），是前端"领域驱动 + Cookie/CSRF"架构的核心。

## 子目录
- `academic/`：学术类型契约（无运行时调用）。
- `auth/`：认证客户端（HttpOnly Cookie + CSRF）。
- `chat/`：会话 CRUD 与 SSE 流式对话。
- `news/`：热点、研判会话、来源审核 API。
- `travel/`：行程、分享、地理编码、草稿/存档 API。

## 业务边界要点
- 所有域 API 必须走 `features/auth/client.ts` 的 `AuthClient`（Cookie + CSRF），不持久化 token（P0-1）。
- 聊天/旅行请求不发送客户端 `user_id`/`agent_id`；身份与路由由后端认证上下文与会话模式决定。
- 管理员授权由后端 403 强制，前端不做角色判断。
- 新前端 API 只能放入 `features/<domain>/api.ts`（AGENTS.md 第 5 节）。
