# domain/travel/ — 模块记忆

## 职责定位
旅行规划领域层（项目最大子域）：Agent 主循环、上下文管理、Prompt 构建，下辖意图分类、行程模型、编排服务、旅行工具四个子包。

## 关键文件
- `core.py`：`Agent` 主类——装配所有 service/manager，实现 `chat`/`chat_stream` 主循环（准备上下文 → 早退处理 → ReAct 推理 → 收尾：保存会话、记忆处理、trace、审计）。
- `agent.py`：`TravelAgent`（包装 `Agent`，向后兼容）——注入多方案锚点、从结构化 `itinerary_id`/兜底正则提取行程跳转建议。
- `context_manager.py`：`ContextManager`——按 `max_context_turns`/`max_context_chars` 裁剪会话上下文，返回 `PreparedContext`。
- `prompting.py`：`PromptBuilder`——构建身份/优化/多方案/执行规则/任务/工具/会话各段 system prompt（快回复与 ReAct 两种）。
- `prompt_context.py`：`PromptContext` 数据类——聚合记忆/MCP/画像/缓存/行程确认等上下文片段。

## 子目录
- `intent/`：旅行意图分类（17 类）。
- `itinerary/`：行程领域模型、仓储、LLM 解析器。
- `services/`：上下文准备、缓存、早退、行程生成、记忆处理等编排服务。
- `tools/`：旅行专用工具（保存行程、生成概览）。

## 业务边界要点
- 紧急求助/签证等敏感话题需转人工旅行顾问。
- 行程跳转建议优先走结构化 `itinerary_id`，正则提取仅为过渡兜底（注释标注脆弱、待废弃）。

## 技术债
⚠️ `core.py` 及各子包大量直接 import `infrastructure.persistence/llm/mcp/tools`，违反 domain 分层约束。
