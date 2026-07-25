# application/authz/ — 模块记忆

## 职责定位
集中式对象级授权服务：统一校验资源归属，是"未授权统一返回 404"安全规则的唯一实现点。

## 关键文件
- `service.py`：`AuthorizationService`——提供 `require_itinerary` / `require_activity` / `require_session`，校验资源属于当前认证用户；资源不存在或不归属时统一抛 404（NotFound），不泄漏资源存在性。
- `__init__.py`：导出 `AuthorizationService`。

## 业务边界要点
- 用户 ID 只取自服务端认证上下文，绝不信任请求体中的 user_id。
- 活动（activity）经 `day_id` 反查行程做间接归属校验。
- 服务无状态，可单例复用；新增用户拥有的资源类型时应在此扩展 require_* 方法。
