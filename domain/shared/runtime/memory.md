# domain/shared/runtime/ — 模块记忆

## 职责定位
运行时支撑：当前时间事实、全局日志配置、推理链路 trace 存储。

## 关键文件
- `facts.py`：当前日期/时间问答与本地时间文本生成（供 Agent 回答"今天几号"类问题）。
- `logging.py`：JSON/Console 日志格式化与全局 `setup_logging` 初始化。
- `trace.py`：`RunTrace` / `TraceStore`——按 session 保留最近 10 条推理 trace，供 debug 端点排查决策过程。
- `__init__.py`：包占位。

## 业务边界要点
- trace 只保留内存最近 10 条，非持久化。
- ⚠️ `logging.py` 操作全局 logging 配置，属基础设施职责落入 domain。
