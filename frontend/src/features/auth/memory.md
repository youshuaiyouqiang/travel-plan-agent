# frontend/src/features/auth/ — 模块记忆

## 职责定位
浏览器认证客户端：HttpOnly Cookie + CSRF 请求包装，是全前端唯一合法的 HTTP 客户端。

## 关键文件
- `client.ts`：`AuthClient`——所有请求 `credentials: 'include'`；不安全方法（POST/PUT/PATCH/DELETE）从 `csrf_token` cookie 读取并注入 `X-CSRF-Token`；GET/HEAD/OPTIONS 不加 CSRF；支持测试注入 fetch。
- `client.test.ts`：测试——不持久化 token、附加 credentials、按方法加 CSRF、保留调用方 header。

## 业务边界要点（安全红线）
- 绝不向 localStorage/sessionStorage 持久化任何 token。
- JS 无法读取 HttpOnly 认证 cookie；CSRF token 从独立的可读 cookie 获取。
- 调用方显式提供 `X-CSRF-Token` 时尊重调用方。
- 禁止恢复 Bearer Token 前端主路径（AGENTS.md 第 4 节）。
