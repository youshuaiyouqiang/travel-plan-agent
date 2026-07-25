# domain/travel/itinerary/ — 模块记忆

## 职责定位
行程聚合：行程领域模型（Itinerary/DayPlan/Activity）、数据库仓储与 LLM 文本解析器。

## 关键文件
- `schema.py`：`PlanType`/`TransportMode`/`CostBreakdown`/`TransportOption`/`Plan`/`DayPlan`/`Activity`/`Itinerary` 等领域模型（含 `from_row`/`to_dict`）。
- `repository.py`：`ItineraryRepository`——行程与天/活动增删改查、整行程保存、分享链接 CRUD。
- `parser.py`：`ItineraryParser`——用 LLM 将行程文本解析为结构化 `Itinerary`；`parse_simple` 为简易解析。
- `__init__.py`：导出 `Itinerary`/`DayPlan`/`Activity`/`ItineraryRepository`/`ItineraryParser`。

## 业务边界要点
- 行程 `version` 每次更新递增。
- 历史上支持多方案（sightseeing/budget/single）；新业务基线已收敛为单草稿+确认存档（见 application/travel），本模型保留兼容。
- 不含打卡、实际花费、相册等已删除字段（禁恢复清单）。

## 技术债
⚠️ `repository.py` 直接操写 SQLite、`parser.py` 直接依赖 LLM SDK，违反 domain 分层约束。
