# infrastructure/cache/ — 模块记忆

## 职责定位
工具调用限流能力：Redis 滑动窗口限流，Redis 不可用时自动降级为进程内内存限流。注意：这不是通用 KV 缓存，只做限流。

## 关键文件
- `rate_limit.py`：`RateLimiter`——Redis 滑动窗口（zremrangebyscore/zadd/expire）与内存兜底（固定窗口 + 定时清理）；`is_allowed(key, limit, window)` 返回 `(allowed, {limit, remaining, reset})`。
- `__init__.py`：包占位。

## 业务边界要点
- 默认窗口 60s；Redis 连接失败仅警告并回退内存，不抛异常。
- 内存模式为单进程计数，多进程部署各计各的（已在注释声明此限制）。
- 会话缓存后端由 `config.session_backend`（redis/sqlite）在别处处理，与本模块无关。
