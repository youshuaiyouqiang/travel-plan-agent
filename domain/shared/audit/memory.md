# domain/shared/audit/ — 模块记忆

## 职责定位
结构化审计子系统：并发安全的审计上下文、事件定义、PII 脱敏、按日期轮转的 JSONL 日志写入。

## 关键文件
- `context.py`：`AuditContext`——基于 `contextvars` 的并发安全审计上下文（session/user/trace id），保证单例组件下多请求不串号。
- `schema.py`：`AuditEvent` 数据类（审计事件字段定义）。
- `sanitizer.py`：PII 脱敏工具——手机号、身份证、邮箱、银行卡、护照、IP 正则替换。
- `logger.py`：`AuditLogger`——按日期轮转写 JSONL（data/audit/），涵盖 tool_call / llm_call / reasoning_step / context_built / api_boundary 等事件；启动时清理超期日志。

## 业务边界要点
- 写入审计前统一对 action/input/output/llm 文本执行脱敏。
- 日志保留 `audit_retention_days`（默认 30 天）。
- 密码、密钥、Token、论文草稿、新闻全文严禁进入审计正文。
- `run_shell` 工具审计风险标记为 high。
