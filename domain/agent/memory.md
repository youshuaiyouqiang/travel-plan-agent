# domain/agent/ — 模块记忆

## 职责定位
智能体抽象与编排核心：统一 Agent 接口、配置驱动的通用动态 Agent、云合调度者（Orchestrator）、Agent 工厂与自定义 Agent 仓储。

## 关键文件
- `base.py`：`BaseAgent` 抽象基类，定义 `name`/`description`/`chat`/`chat_stream` 接口与返回约定（final_answer / need_input / cannot_handle）。
- `schema.py`：`AgentConfig`（内置与自定义 Agent 统一配置模型）与 `SkillInfo`。
- `dynamic_agent.py`：`DynamicAgent`——由 `AgentConfig` 驱动，具备 ReAct 工具执行、Prompt 注入消毒、会话管理与审计。
- `orchestrator.py`：`OrchestratorAgent`（云合）——mode-first 路由 + function calling 委派主循环（Tier 0 快路径 / Tier 1 委派决策 / Tier 2 委派执行），含委派上下文状态机。
- `factory.py`：`AgentFactory`，按配置创建 Agent；内置特殊构造走分支，其余默认 `DynamicAgent`。
- `repository.py`：`CustomAgentRepository`，自定义 Agent 配置的数据库 CRUD。

## 业务边界要点
- 工具白名单由 `tool_executor.policy.filter_allowed_tools` 强制（学术 Agent 即使误配 web_search 也拿不到）。
- 云合委派上限 `_MAX_DELEGATIONS=3`、委派超时 1800s、独立迭代上限 10 防死循环。
- Agent 实例缓存 key 含 `user_id`，避免跨用户复用；仅 builtin 不被清理。
- Orchestrator 的 `chat` 签名与 `BaseAgent` 不同（多 mode/locked_agent_id），因其为顶层调度器不参与多态。

## 技术债
⚠️ `dynamic_agent.py`/`factory.py`/`orchestrator.py`/`repository.py` 直接 import `infrastructure.*`（LLM/tools/mcp/database），违反 domain 分层约束；`repository.py` 直接操写 `custom_agents` 表。
