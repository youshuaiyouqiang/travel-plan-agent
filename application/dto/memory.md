# application/dto/ — 模块记忆

## 职责定位
全局请求/响应数据契约层（Pydantic v2 模型），集中参数校验与字段约束，是 API 输入输出的唯一 schema 来源。

## 结构
- `request/`：各资源的请求 DTO（详见其 memory.md）。
- `response/`：响应 DTO 与统一响应包装（详见其 memory.md）。
- `__init__.py`：包占位。

## 业务边界要点
- 新增 DTO 必须使用 Pydantic v2 且默认 `ConfigDict(extra="forbid")` 防参数注入。
- 先定义 DTO、授权边界和失败场景，再接入路由（AGENTS.md 第 5 节）。
