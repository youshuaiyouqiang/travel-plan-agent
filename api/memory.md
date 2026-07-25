# api/ — 模块记忆

## 职责定位
接口适配层（DDD 最外层）：FastAPI 服务器装配入口与全局横切关注点（认证、限流、异常处理）。只处理协议、认证身份和响应；业务规则在 application/domain。

## 关键文件
- `server.py`：创建 FastAPI 实例；注册 lifespan 后台任务（热搜池刷新、记忆维护、热点清理）；挂载中间件与全局异常处理器；将 `SessionService`/`AuthorizationService`/`HotspotService`/`admin_user_id` 注入 `app.state`；把 v1 路由同时挂到 `/api/v1` 与 `/api`（向后兼容）。
- `intl_coords.py`：内置国际目的地（东京、巴黎、纽约等）经纬度字典 `INTL_COORDS` 与 `lookup_intl_coords()` 模糊匹配，供国际地理编码兜底。
- `__init__.py`：包占位。

## 子目录
- `middleware/`：认证、CSRF、限流、统一异常响应。
- `routes/`：路由聚合占位包（实际路由在 `v1/`）。
- `v1/`：全部 HTTP 路由实现。

## 业务边界要点
- 管理员启动期从 `YUNHE_ADMIN_USERNAME` 解析：生产环境缺失必须 fail-fast（RuntimeError），开发环境降级为 `None`。
- 可锁定 Agent 白名单排除调度员 `yunhe` 与新闻锚点 `news`，仅 `travel`/`academic` 等可被用户手动锁定。
- 路由双前缀 `/api/v1` 与 `/api` 复用同一套 v1 路由，保证前端平滑迁移；新契约优先放 `/api/v1`。
