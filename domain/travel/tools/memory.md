# domain/travel/tools/ — 模块记忆

## 职责定位
旅行专用工具实现与注册入口：保存行程、生成行程概览等工具，供 ReAct 引擎调用。

## 关键文件
- `travel_tools.py`：`_save_itinerary` / `_generate_itinerary_overview`（写文件/写库）；`get_travel_specs` / `get_travel_handlers` 注册入口；含多方案内容提取逻辑。

## 业务边界要点
- 工具只对旅行 Agent 开放（工具策略白名单控制）。
- 行程概览以结构化 `itinerary_id` 返回，供前端跳转。

## 技术债
⚠️ 直接写文件系统（`itineraries/*.md`）、操写 SQLite、依赖 `config.settings.project_root`，属典型基础设施职责落入 domain。
