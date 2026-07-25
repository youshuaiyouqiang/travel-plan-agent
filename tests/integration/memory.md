# tests/integration/ — 模块记忆

## 职责定位
集成测试层（22 个文件）：覆盖 API、会话模式、授权、Token 安全、新闻治理、旅行草稿/存档、热点池等关键业务与安全边界。

## 代表性文件
- `test_resource_authorization.py`：对象级授权（未授权统一 404）。
- `test_token_security.py`：Token 哈希存储、Cookie/CSRF 边界。
- 新闻：分析会话、收藏迁移、来源仓储、管理 API。
- 旅行：草稿编辑、存档、行程。
- `test_removed_album_routes.py` / `test_removed_travel_features.py`：固化禁恢复清单（相册、情感、支付等确已移除），防回归。
- fail-fast：生产环境管理员缺失时启动失败。

## 业务边界要点
- 认证、授权、迁移、新闻证据、行程存档的行为变更必须在此补集成测试。
- `test_removed_*` 是禁恢复清单的守护测试，删改前必须确认产品决策。
