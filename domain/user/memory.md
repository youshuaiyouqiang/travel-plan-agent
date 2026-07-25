# domain/user/ — 模块记忆

## 职责定位
用户域：认证（账号密码 + Token）、用户画像、会话与任务状态管理。

## 子目录
- `auth/`：用户存储、密码认证与 Token 生命周期。
- `profile/`：用户画像（标签、意图、关注领域）。
- `session/`：会话管理（内存+Redis+SQLite 三级）与任务状态机。

## 业务边界要点
- 身份只能从服务端认证上下文取得；浏览器长期凭据走 HttpOnly Cookie。
- 数据库只存 Token 哈希（SHA-256），明文不落盘。

## 技术债
⚠️ 各子包均直接 `from infrastructure.persistence.database import get_connection` 读写用户/会话/任务表，并依赖 `infrastructure.security.password`，违反 domain 分层约束。
