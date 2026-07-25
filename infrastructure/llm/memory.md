# infrastructure/llm/ — 模块记忆

## 职责定位
LLM 调用适配层：封装 OpenAI 兼容协议（含 DashScope/通义千问）的同步/流式/工具/JSON 调用，并提供多 provider 自动降级链。

## 关键文件
- `openai.py`：`OpenAILLM` + `LLMResponse`/`ToolCallResult`——`complete`、`stream_complete`、`complete_with_tools`（原生 tool calling，失败回退纯文本）、`complete_json`（容错 JSON 解析）；每次调用经 `AuditContext` + `audit_logger` 写审计。
- `fallback.py`：`FallbackLLM`——按优先级遍历 provider，捕获 RateLimit/ServiceUnavailable/Connection/Timeout 自动切换，全部失败抛 `AllProvidersFailedError`；覆盖全部接口。
- `__init__.py`：包占位。

## 业务边界要点
- 并发审计上下文用 `ContextVar` 隔离，单例下多请求不串号（P0-5）。
- `complete_json` 容错：先 `json.loads`，失败再截取首个 `{` 到末个 `}`。
- fallback 仅对限流/网络类异常降级；末位 provider 的其它异常直接上抛。
- API Key 从 settings/环境变量读取，不进日志。
