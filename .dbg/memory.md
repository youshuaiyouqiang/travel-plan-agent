# .dbg/ — 模块记忆

## 职责定位
调试日志目录：前端/会话级调试追踪记录（NDJSON），由调试工具产出。

## 文件
- `trae-debug-log-itinerary-overview-no-redirect.ndjson`：行程概览页"不重定向"问题的调试事件记录（渲染/挂载/拉取埋点）。

## 业务边界要点
- ⚠️ 调试日志含 `userId` 与会话内容片段，属敏感用户数据；已在 .gitignore 忽略，确认不要提交。
- 问题排查完成后可清理。
