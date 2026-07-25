# frontend/src/utils/ — 模块记忆

## 职责定位
未迁入 features/ 前的遗留通用 API 客户端与类型（auth 注册登录、趋势、收藏、记忆、Agent/Skill/MCP 中心）。

## 关键文件
- `api.ts`：`register/login`（走 AuthClient，无 token）、trending 与 news favorites（legacy）、memories、Agent/Skill/MCP 中心 API；类型 `AgentInfo/SkillInfo/MCPServerInfo/NewsFavorite/MemoryItem` 等。chat/travel/academic 已迁移到 features/（文件注释有标注）。

## 业务边界要点
- P0-1 修复后不再使用 Bearer token，统一走 `features/auth/client.ts`。
- `fetchAgents` 返回 `{builtin, custom, public}` 三类；`AgentInfo.source` 区分 builtin/custom。
- 演进方向：剩余 API 逐步迁往 `features/<domain>/api.ts`，新代码不要往这里加。
