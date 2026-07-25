# domain/user/session/ — 模块记忆

## 职责定位
会话与任务状态子域：会话轮次的三级存储（内存 + Redis + SQLite）与 Agent 任务状态机。

## 关键文件
- `manager.py`：`Turn` / `Session` / `SessionManager`——会话读写、披露工具集合、委派上下文、会话模式（mode/locked_agent_id/news_id）持久化、增量持久化标记。
- `task_state.py`：`TaskStatus` / `TaskRecord` / `TaskStateStore`——任务状态机（idle → in_progress → needs_user_input/confirmation → completed/failed）、工具结果缓存。

## 业务边界要点
- 会话缓存 TTL 300s，防止永不刷新。
- `user_id` 首次创建后绑定且后续保持一致（P0-4，写入 `sessions.user_id` 列）。
- 状态机约束：completed/failed/idle 时清空 `pending_prompt`。
