# application/exceptions/ — 模块记忆

## 职责定位
统一业务异常体系：所有异常携带业务码 + HTTP 状态码，由 api/middleware/error_handler.py 统一转为结构化 JSON 响应。

## 关键文件
- `base.py`：`ClawException` 基类（code / message / http_status / details）。
- `auth.py`：认证/授权异常（401/403）。
- `not_found.py`：资源未找到（404）。
- `validation.py`：参数校验失败（400）。
- `conflict.py`：状态冲突（409，如重复确认不同方案、编辑不可变存档）。
- `rate_limit.py`：限流（429）。
- `internal.py`：内部错误/服务不可用（500/503）。
- `__init__.py`：聚合导出。

## 业务边界要点
- 对象级未授权与资源不存在统一 404，隐藏资源存在性。
- 业务码为 6 位数字；异常详情不得携带堆栈或敏感信息到客户端。
