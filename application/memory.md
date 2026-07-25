# application/ — 模块记忆

## 职责定位
应用服务层：DTO、用例编排、授权、会话模式、后台调度。承接 api 层请求，编排 domain 领域逻辑与 infrastructure 能力，不直接处理 HTTP 协议。

## 关键文件
- `scheduler.py`：后台周期任务——`run_memory_maintenance`（每小时逐用户记忆蒸馏+衰减，保证用户间隔离）、`run_hotspot_refresh`（每 15 分钟只抓 `enabled` 来源、不抓全文）、`run_hotspot_cleanup`（每 6 小时清理，当前为占位）。
- `__init__.py`：包占位。

## 子目录
- `academic/`：学术研究上下文服务（草稿不长期化）。
- `authz/`：集中式对象级授权（未授权统一 404）。
- `builtin_agents/`：内置 Agent 的 YAML 配置与加载器。
- `data/`：热搜缓存 JSON（运行时数据，遗留位置）。
- `dto/`：Pydantic 请求/响应契约。
- `exceptions/`：统一业务异常体系。
- `news/`：新闻来源治理、热点池、证据化研判。
- `session/`：会话模式与所有权校验。
- `travel/`：旅行草稿/存档生命周期。
- `trending/`：热搜抓取兼容包装（已委托 news.HotspotService）。

## 业务边界要点
- 定时任务是热点数据的唯一抓取入口；用户请求路径永不触发外部抓取。
- 记忆维护按用户逐一执行，防止跨用户数据混合。
