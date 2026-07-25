# domain/travel/intent/ — 模块记忆

## 职责定位
旅行意图分类子包：把用户消息分类为 17 种旅行意图，驱动工具提示与上下文准备。

## 关键文件
- `travel_schema.py`：`TravelIntentType`（17 类）、`INTENT_TOOL_HINTS`（意图→工具提示映射）、`INTENT_RAG_KEYWORDS`。
- `travel_classifier.py`：`TravelIntentClassifier` + `TravelIntentResult`——三级分类：闲聊快路径 → 关键词分类（阈值 0.85）→ LLM 分类；产出意图/目标/缺失信息/多方案修改元数据。

## 业务边界要点
- 关键词分类阈值从 0.7 提升到 0.85（P2-10），降低误判为旅行意图的概率。
- 快聊集合与 Orchestrator 保持一致，避免调度和分类行为分叉。

## 技术债
⚠️ `travel_classifier.py` 直接依赖 `infrastructure.llm.openai`。
