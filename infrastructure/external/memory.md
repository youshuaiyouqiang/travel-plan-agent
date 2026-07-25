# infrastructure/external/ — 模块记忆

## 职责定位
预期的"外部服务/第三方集成"适配层，当前为空占位包（仅 0 字节 `__init__.py`），无任何实现。

## 现状
- 实际的外部集成能力分散在：`tools/adapters/`（amap/fliggy/qweather/http）、`mcp/servers/`（web-search 等）、`skills/builtin/`。

## 业务边界要点
- 新增外部集成时优先评估应放入 `tools/adapters/` 还是本目录，避免继续分散。
