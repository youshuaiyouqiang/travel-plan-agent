# domain/ — 模块记忆

## 职责定位
领域层（DDD 核心）：领域模型、端口、Agent 编排、推理引擎、记忆、用户域。按规范不得直接依赖数据库/HTTP/LLM SDK（通过端口或应用服务注入）。

## 子目录
- `academic/`：学术域——论文实体、研究上下文、检索端口（分层最干净的子域）。
- `agent/`：智能体抽象与编排——BaseAgent、DynamicAgent、云合 Orchestrator、工厂、自定义 Agent 仓储。
- `feedback/`：对话质量反馈仓储。
- `memory/`：双层记忆（短期/长期）的管理、提取、蒸馏。
- `reasoning/`：ReAct 推理引擎、成本守卫、工具选择器。
- `safety/`：Prompt 注入防御（纯函数）。
- `shared/`：共享内核——类型、审计、指标、运行时。
- `travel/`：旅行子域（最大）——意图、行程、编排服务、旅行工具。
- `user/`：用户域——认证、画像、会话与任务状态。

## 已知技术债（⚠️ 重要）
规范要求 domain 不直接依赖基础设施，但当前大量文件违反：
- 直接依赖数据库（`infrastructure.persistence.database`）：agent/repository、feedback/repository、memory/*、travel/itinerary/repository、travel/tools、user/*。
- 直接依赖 LLM SDK（`infrastructure.llm.openai`）：reasoning/engine、memory 提取/蒸馏、travel 分类器/解析器/services。
- 横切基础设施落入 domain：shared/audit/logger（写文件）、shared/metrics/collector（Prometheus HTTP server）、shared/runtime/logging（全局日志配置）。

保持端口/依赖倒置较干净的子域：`academic/`（Protocol 端口）、`safety/`（纯函数）。新增代码应遵循规范走端口注入，不要效仿现有违规写法。
