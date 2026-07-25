# api/middleware/ — 模块记忆

## 职责定位
HTTP 级横切安全控制：认证（Bearer/Cookie 双模式）、CSRF 双重提交校验、请求频率限制、统一异常转 JSON 响应。

## 关键文件
- `auth.py`：`auth_middleware`（公共路径白名单、Bearer token 优先、Cookie + CSRF double-submit 校验）与 `rate_limit_middleware`（基于用户/IP/路径的 RPM 限流，Redis 或内存计数）。
- `error_handler.py`：`claw_exception_handler`（`ClawException` → 结构化错误体）与 `unhandled_exception_handler`（兜底 500，含 `trace_id`，不向客户端暴露堆栈）。
- `__init__.py`：包占位。

## 业务边界要点
- 公共路径白名单：`/api/auth/*`、`/api/news/trending`、`/api/health`、`/api/shared`、`/docs` 等免认证。
- 浏览器认证：`auth_token`（HttpOnly Cookie）+ `csrf_token` Cookie；不安全方法（POST/PUT/PATCH/DELETE）必须携带匹配的 `X-CSRF-Token`。
- 非浏览器客户端走 `Authorization: Bearer`，天然免疫 CSRF。
- 限流窗口 60s，限额 `settings.rate_limit_rpm`，超限返回 429；未认证/过期返回 401。
