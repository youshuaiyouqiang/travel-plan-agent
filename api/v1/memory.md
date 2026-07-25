# api/v1/ — 模块记忆

## 职责定位
API v1 全部 HTTP 路由的集中实现层；每个文件对应一类资源/用例，统一在 `__init__.py` 聚合后由 `server.py` 挂载到 `/api/v1` 和 `/api`。

## 关键文件
- `__init__.py`：将各子路由 include_router 到对应前缀（auth/chat/sessions/agents/skills/mcp/itineraries/memories/news/admin/geocode/share/debug/health/feedback/travel）。
- `auth.py`：注册/登录；登录只下发 HttpOnly `auth_token` + 独立随机 `csrf_token` Cookie，响应体不含 token 字段。
- `chat.py`：`POST /chat` 与 `/chat/stream`（SSE）；从 `SessionService` 解析会话模式与锁定 Agent，调用编排器，写审计边界日志。
- `session.py`：会话 CRUD 与方案确认（confirm-plan/revoke-confirm/confirm-status），经 `AuthorizationService.require_session` 做对象级授权。
- `agent.py`：内置/自定义/公开智能体列表、自定义 Agent CRUD 与克隆。
- `skill.py` / `mcp.py`：技能与 MCP server/工具的只读查询（含 `adapter_available` 状态）。
- `itinerary.py`：行程 CRUD、按会话归集、活动删除、分享链接管理（均经授权校验）。
- `memory.py`：用户长/短期记忆读取与按类型删除（short_term/long_term 白名单防注入）。
- `news.py`：热搜趋势、热点池只读列表、新闻研判会话创建（锚定 `news_id`、锁定 `news` Agent）、新闻收藏增删查。
- `admin_news.py`：新闻来源治理管理员 API，仅启动期锚定的单一管理员可访问。
- `geocode.py`：批量地理编码（高德）与国际地理编码（内置字典 → Nominatim 兜底）。
- `share.py`：通过 token 读取公开分享行程（无需认证）。
- `travel.py`：旅行草稿/存档全生命周期（创建/编辑/刷新预览/应用/确认/基于存档续编），含手工编辑字段保护。
- `debug.py` / `health.py` / `feedback.py`：调试快照、健康检查与 Prometheus 指标、对话质量反馈。

## 业务边界要点
- 会话模式：用户 API 仅允许 `yunhe_default` / `agent_locked`；`news_analysis_locked` 只能由新闻研判服务内部创建。
- 对象级授权：跨用户资源访问统一返回 404，不泄漏资源存在性。
- 方案确认并发安全：同会话已确认不同方案返回 409；同方案重复确认幂等。
- 新闻红线：`GET /hotspots` 只读缓存、严禁请求内外部抓取；研判会话锚点必须存在于热点池，否则 404；收藏只存元数据不存全文。
