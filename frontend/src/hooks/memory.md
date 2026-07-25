# frontend/src/hooks/ — 模块记忆

## 职责定位
zustand 全局状态管理：认证展示态、对话流、会话/智能体状态、行程详情。

## 关键文件
- `useAuthStore.ts`：认证 UI 展示态（userId/username/isAuthenticated）；`persist` 仅持久化这三个非令牌字段；login/logout 不碰 token。
- `useAuthStore.test.ts`：P0-1 回归测试——持久化不含 token、请求不带 Authorization。
- `useChatStore.ts`：消息列表、流式追加、思考步骤、会话列表、加载/升级状态。
- `useSessionStore.ts`：当前激活智能体（展示态）、操作卡片、多方案确认状态（confirmPlan/revokeConfirm/syncConfirmStatus）、服务端会话模式同步。
- `useItineraryStore.ts`：行程详情加载、选中天、活动详情、删除活动。

## 业务边界要点
- 认证红线：persist 只存 UI 字段，长期凭据全在 HttpOnly Cookie。
- 多方案确认：后端存 `sightseeing/budget`，前端映射 `plan1/plan2`；409 冲突时回查服务端状态。
- `sessionMode` 仅由后端响应写入；侧边栏 Agent 选择只是展示态。
