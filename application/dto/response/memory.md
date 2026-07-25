# application/dto/response/ — 模块记忆

## 职责定位
API 响应体模型与统一响应包装。

## 关键文件
- `common.py`：统一 `ApiResponse`（`{code, message, data}`）与 `ErrorResponse`。
- `auth.py`：登录响应——**不含 token 字段**（凭据只经 HttpOnly Cookie 下发）。
- `chat.py`：对话回复体。
- `__init__.py`：聚合导出。

## 业务边界要点
- 登录/注册响应体绝不返回长期认证 Token（P0 安全修复，前端亦有回归测试守护）。
- 前端统一按 `{code, message, data}` 解包。
