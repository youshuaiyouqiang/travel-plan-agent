# domain/shared/ — 模块记忆

## 职责定位
跨领域共享内核：基础类型、审计、指标、运行时（上下文/日志/链路追踪）。

## 关键文件
- `types.py`：共享枚举与数据类——`IntentType`、`IntentResult`、`DecisionType`、`ToolCall`、`Decision`、`TraceEvent`。
- `__init__.py`：包占位。

## 子目录
- `audit/`：审计上下文、事件 schema、PII 脱敏、JSONL 审计日志。
- `metrics/`：Prometheus 指标收集。
- `runtime/`：日期事实、日志配置、推理 trace 存储。

## 技术债
⚠️ `audit/logger.py`（写文件系统）、`metrics/collector.py`（起 HTTP metrics server）、`runtime/logging.py`（全局 logging 配置）均属基础设施职责落入 domain 共享包。
