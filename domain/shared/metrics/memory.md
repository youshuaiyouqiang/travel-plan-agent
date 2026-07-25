# domain/shared/metrics/ — 模块记忆

## 职责定位
Prometheus 指标收集：请求计数、延迟、工具执行等运行指标。

## 关键文件
- `collector.py`：指标定义与收集；`track_request` 异步上下文管理器；按 `settings.metrics_enabled`/`metrics_port` 启动 metrics HTTP server。
- `__init__.py`：包占位。

## 业务边界要点
- 指标开关与端口由配置控制（默认端口 9090）。
- ⚠️ 起 HTTP server 属基础设施职责，按规范未来应移出 domain。
