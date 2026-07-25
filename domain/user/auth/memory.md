# domain/user/auth/ — 模块记忆

## 职责定位
认证子域：用户账号创建/认证与 Token 签发/验证/撤销。

## 关键文件
- `auth.py`：`User` / `UserStore`——账号创建、密码认证（bcrypt 校验，发现旧 PBKDF2 哈希自动就地升级为 bcrypt）、按 id/username 查询，带 300s 缓存 TTL。
- `token.py`：`TokenData` 与 `generate/verify/revoke_token`、`hash_token`（SHA-256）；默认 7 天过期。

## 业务边界要点
- 数据库只存 `sha256(token)`；bearer/cookie 共用 `auth_token_hashes` 表；验证前先清理过期项。
- 密码哈希自动升级：认证成功时发现需升级则就地重算。
- 密码、Token 明文严禁进入日志和异常详情。
