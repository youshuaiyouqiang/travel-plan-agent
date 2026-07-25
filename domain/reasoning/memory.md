# domain/reasoning/ — 模块记忆

## 职责定位
推理引擎领域层：通用 ReAct 推理循环、成本守卫与工具选择器，供 travel/agent 子域复用。

## 关键文件
- `engine.py`：`ReasoningEngine`——核心 ReAct 循环（原生 tool calling 与 JSON 降级双轨）、工具渐进式披露、重复调用检测、成本记账、流式推理；定义 `AskUserNeeded`/`ConfirmationNeeded` 异常与 `TraceStep`。
- `cost_guard.py`：`CostGuard`——按 token/工具调用/迭代次数做预算检查与预警（80% 阈值）。
- `tool_selector.py`：`ToolSelector`——按用户消息关键词/类别对工具打分，推荐 top-N 相关工具。

## 业务规则
- `force_tool` 时未用工具则重试（最多 2 轮）；工具结果连续 ≥3 轮"未接地"（ungrounded）则接受最佳文本回答。
- 重复工具签名 ≥3 次触发提示；接近迭代上限（`settings.max_iterations`）强制终答。
- `CostGuard` 默认 `max_tool_calls=20`、`token_budget=50000`。
- 工具原始 traceback 对 LLM 屏蔽，转为结构化错误。

## 技术债
⚠️ `engine.py` 类型注解直接引用 `infrastructure.llm.openai.OpenAILLM` 与 `infrastructure.tools.*`（构造注入尚属依赖倒置，但类型耦合了基础设施具体类）。
