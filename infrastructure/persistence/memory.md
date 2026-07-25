# infrastructure/persistence/ — 模块记忆

## 职责定位
SQLite 持久化层：统一封装连接管理、版本化迁移与各领域 Repository。

## 关键文件
- `database.py`：线程局部连接管理（WAL 模式、外键开启）+ 迁移跟踪；提供 `get_connection` 与 JSON 序列化辅助。
- `news_repository.py`：新闻来源治理仓储（来源/候选/审计）。
- `session_repository.py`：会话/任务/轮次仓储。
- `travel_repository.py`：旅行草稿与存档仓储。
- `health.py`：健康巡检（SQLite/Redis 连通性）。

## 业务边界要点
- SQL 全部 `?` 参数绑定；动态表名只能来自硬编码白名单。
- 修改表结构必须新建版本化迁移并含回滚处理，不得修改历史迁移伪造状态。
- 不存新闻全文；旅行存档仅存行程 JSON 快照（不可变）。
- 数据库路径由 `YUNHE_DATABASE_PATH` 配置（默认 `data/yunhe.db`）。
