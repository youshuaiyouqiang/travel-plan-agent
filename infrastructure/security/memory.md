# infrastructure/security/ — 模块记忆

## 职责定位
密码与凭证安全模块：密码哈希/校验与旧格式自动升级。

## 关键文件
- `password.py`：bcrypt 哈希/校验（轮数 12）；缺 bcrypt 依赖时回退 PBKDF2（60 万次迭代）；支持旧 PBKDF2 格式（salt$hex，默认 10 万次）向后兼容与自动升级。

## 业务边界要点
- 密码明文/哈希不得进入日志、异常详情。
- 升级路径：认证成功时发现旧格式哈希则就地重算为 bcrypt（由 domain/user/auth 调用）。
