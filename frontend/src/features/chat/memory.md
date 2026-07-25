# frontend/src/features/chat/ — 模块记忆

## 职责定位
对话域 API：会话管理与 SSE 流式对话，强类型事件契约。

## 关键文件
- `api.ts`：会话 CRUD（listSessions/createSession/updateSessionMode/deleteSession/getSessionMessages）；`sendMessageStream`（async generator）——只发 `session_id + message`，解析 SSE 判别联合，401 → `AUTH_EXPIRED`，429 → 限流提示。
- `types.ts`：`StreamEvent` 判别联合（chunk/route/error/done/tool_status/need_input/actions/control_returned/status），全强类型无 any。
- `api.test.ts`：测试——不发送 user_id、SSE 解析、401 抛 AUTH_EXPIRED。

## 业务边界要点
- 会话模式：`yunhe_default | agent_locked | news_analysis_locked`；`user_id`/`agent_id` 由后端决定，客户端传入被忽略。
- `done.next_controller` 仅 `yunhe` 或 `locked_agent`（对应"委派后控制权回到云合"）。
- `need_input` 支持 string / string[] / {question, field} 多种形态。
