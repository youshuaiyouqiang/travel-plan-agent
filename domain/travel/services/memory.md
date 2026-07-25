# domain/travel/services/ — 模块记忆

## 职责定位
旅行 Agent 的编排服务集合：上下文准备、缓存管理、早退处理、行程直通生成、记忆后处理、Prompt 辅助。

## 关键文件
- `context_preparer.py`：`ContextPreparer` + `ChatPreparation`——编排意图分类、记忆/MCP/画像上下文、任务状态、早退动作，产出完整 `ChatPreparation`。
- `cache_manager.py`：`CacheManager`——工具结果缓存上下文构建与失效判定（出发地/目的地/日期/预算等核心字段变更才失效）。
- `early_action_handler.py`：`EarlyActionHandler`——早退动作处理（如直通生成行程概览，绕过 LLM 推理），同步/流式两种。
- `itinerary_generator.py`：`ItineraryGenerator`——从会话历史提取行程文本，直通生成行程概览与结构化 `itinerary_id`。
- `memory_processor.py`：`MemoryProcessor`——对话后触发记忆提取/蒸馏（受 `memory_extraction_enabled` 开关控制）。
- `prompt_helper.py`：`PromptHelper`——缺失信息提示、澄清问题、偏好注入等 prompt 片段。

## 业务边界要点
- 行程概览生成走"直通"路径，避免重复 LLM 推理浪费成本。
- 缓存失效只由核心行程要素变更触发，避免无谓重查外部 API。

## 技术债
⚠️ 各服务直接依赖 `infrastructure.llm/mcp/persistence`，违反 domain 分层约束。
