# 架构清理与依赖反转实施计划

> **版本：** v1.0，2026-07-25
>
> **状态：** 待评审 / 未开工
>
> **优先级：** 用户指令 > AGENTS.md > 产品设计 > 本计划 > 既有代码约定
>
> **目标：** 一次性清除分层债务，让代码与 AGENTS.md 描述完全一致，并把规则固化为 CI 阻断，防止债务再生。

---

## 1. 背景与动机

2026-07-17 重构后，业务、安全、测试门禁已落地，但分层架构存在**执行欠账**：

- AGENTS.md 第 2 节宣称"领域代码不得直接依赖具体数据库、HTTP 客户端或 LLM SDK"，但 `domain/` 层实测存在 **24 处** 对 `infrastructure/` 的直接 import（见 §2.1）。
- 两个巨型模块（`database.py` 49KB、`engine.py` 56KB）持续吸积代码，是屎山的标准起点。
- 静态检查工具配置与 AGENTS.md 文字规则不一致（ruff 关闭了 B904/F401，mypy 非 strict，Makefile 无覆盖率门槛），规则缺乏工具兜底。
- 前端 `src/utils/api.ts`（319 行 legacy 聚合层）与 AGENTS.md"新 API 仅入 features/<domain>/api.ts"并存，AI 易误用。

**不处理的后果：** AI 辅助开发面对"规则与代码矛盾"时会选择模仿周围代码，债务指数放大。

**本次目标（完成定义）：**

1. `domain/` 层对 `infrastructure/` 的 import **清零**（含类型注解位置），依赖方向全部反转。
2. 无超过约 800 行的单文件；`database.py`、`engine.py` 完成拆分。
3. 依赖方向由 CI 工具**阻断式**校验，不再依赖人审。
4. ruff/mypy/Makefile 与 AGENTS.md 文字规则一致。
5. AGENTS.md 更新为描述**真实达成**的架构。

---

## 2. 现状审计（证据清单）

### 2.1 domain → infrastructure 反向依赖（24 处，15 个文件）

| 类别 | 文件 | 依赖点 |
|---|---|---|
| 持久化 | `domain/user/session/manager.py`、`domain/user/session/task_state.py` | `infrastructure.persistence.database.get_connection` 等 |
| 持久化 | `domain/memory/manager.py`、`memory_extractor.py`、`memory_distiller.py` | `get_connection`、`_json_dumps/_json_loads` |
| 持久化 | `domain/user/profile/manager.py` | `get_connection` 等 |
| 持久化 | `domain/feedback/repository.py`、`domain/agent/repository.py`、`domain/travel/itinerary/repository.py` | `get_connection` |
| 持久化+安全 | `domain/user/auth/auth.py`、`token.py` | `get_connection`、`infrastructure.security.password` |
| LLM | `domain/agent/orchestrator.py`、`factory.py`、`dynamic_agent.py` | `infrastructure.llm.openai.OpenAILLM` |
| LLM | `domain/reasoning/engine.py`、`domain/memory/memory_extractor.py`、`memory_distiller.py`、`domain/travel/intent/travel_classifier.py`、`itinerary/parser.py`、`services/early_action_handler.py`、`services/context_preparer.py` | `OpenAILLM`（含类型注解） |
| 工具/MCP 框架 | `domain/agent/factory.py`、`dynamic_agent.py`、`domain/travel/core.py`、`domain/reasoning/engine.py`、`domain/reasoning/tool_selector.py`、`domain/travel/tools/travel_tools.py`、`services/context_preparer.py` | `infrastructure.tools.{base,registry,executor}`、`infrastructure.mcp.{runtime,catalog}` |

### 2.2 巨型模块

| 文件 | 规模 | 构成 |
|---|---|---|
| `infrastructure/persistence/database.py` | ~1260 行 | 连接管理（~60 行）+ 18 版迁移 `_upgrade_N/_downgrade_N`（~900 行）+ 迁移注册/执行/回滚 + `_json_dumps/_json_loads` |
| `domain/reasoning/engine.py` | ~1330 行 | JSON 提取工具函数 + `ReasoningEngine`（`run` 322 行、`run_stream` 230 行）+ 决策解析族（`_parse_decision` 等 8 个）+ 文本清洗族 |

### 2.3 工具链与规则不一致

- `pyproject.toml` ruff ignore 含 `F401`（未使用导入）、`B904`（异常链）——与 AGENTS.md 第 5 节矛盾。
- mypy 未开 strict，`ignore_missing_imports=true`。
- `Makefile` 的 `test` 目标无 `--cov-fail-under=70`，本地可绕过 CI 门槛。
- `requirements.txt` 为 0 字节空文件，易误导。
- `tests/e2e/` 为空目录，与 AGENTS.md 三层测试声明不符。

### 2.4 基线状态（2026-07-25 实测）

- `ruff check .`：通过（170 文件）。
- `mypy api application domain infrastructure`：通过。
- pytest 全量：**开工前必须先补跑确认全绿**（作为重构安全网）。

---

## 3. 目标架构与依赖规则

### 3.1 依赖方向（唯一合法方向）

```text
api ──────────→ application ──────────→ domain
  │                                        ↑
  └────────────→ infrastructure ───────────┘
                 （实现 domain 定义的端口）

app.py（组合根）：唯一允许同时 import 全部四层的模块，
                 负责把 infrastructure 实现注入 application/domain。
```

- `domain/`：只允许 import 标准库与 `domain/` 内部模块。所有外部能力（DB、LLM、MCP、HTTP 工具）以 **Protocol 端口**声明于 domain。
- `infrastructure/`：实现 domain 端口；不得被 domain import。
- `application/`：编排用例，依赖 domain 端口与模型；不直接 import infrastructure（由组合根注入实现）。
- `api/`：只做协议适配，依赖 application 服务/DTO。

### 3.2 端口设计总表

| 端口（domain 定义） | 实现（infrastructure） | 注入点 |
|---|---|---|
| `domain/shared/persistence/ports.py`：`ConnectionProvider`（或按聚合细分的各 Repository Protocol） | `infrastructure/persistence/connection.py` + `repositories/` | `app.py` |
| `domain/shared/llm/ports.py`：`LLMPort`（方法面 = 现 `OpenAILLM` 公共方法集） | `infrastructure/llm/openai.py`、`fallback.py`（结构性满足 Protocol） | `app.py` |
| `domain/shared/tools/*`：工具框架本体（`ToolSpec`/`ToolRegistry`/`ToolExecutor`/`ToolCatalog`/`ToolPolicy`） | **迁移至 domain**（框架无外部 I/O）；I/O 留在 `infrastructure/tools/adapters/` | `app.py` |
| `domain/shared/mcp/ports.py`：`MCPRuntimePort`（`build_specs`/`build_handlers`）、`MCPCatalogPort` | `infrastructure/mcp/runtime.py`、`catalog.py` | `app.py` |
| `domain/user/auth/ports.py`：`PasswordHasherPort` | `infrastructure/security/password.py` | `app.py` / application auth 服务 |

### 3.3 落地策略：结构性 Protocol（非 ABC）

全部采用 `typing.Protocol` 结构化子类型：现有 `OpenAILLM`、`FallbackLLM`、`MCPProxyRuntime` 等**实现类零改动或极少改动**，只改 domain 侧的 import 与类型注解，把改动面控制在最小。

---

## 4. 分阶段实施计划

> 每个阶段独立成 PR/提交；每阶段结束必须四门禁全绿（ruff / mypy / bandit / pytest --cov-fail-under=70）+ 依赖方向检查通过，方可进入下一阶段。

### P0：门禁止血（半天，零业务风险）

**目标：** 先冻结债务，再还债。

1. 补跑 pytest 全量，确认基线全绿。
2. 新增 `scripts/check_dependencies.py`（或引入 import-linter）：扫描 `domain/`、`application/` 下 `import infrastructure` / `from infrastructure` 及 `import fastapi` 等违规项，输出清单并以非零码退出。违规数先以现状为基线快照（24 处），**只允许减少、不允许增加**。
3. CI 新增该检查（阻断式）。
4. AGENTS.md 增补"过渡条款"：声明 §2.1 清单为历史遗留、禁止模仿、新增代码禁止新增 domain→infrastructure import；声明 `frontend/src/utils/api.ts` 为 legacy 禁止新增函数；声明两个巨型模块禁止继续塞入新功能。
5. 删除空的 `requirements.txt`（或写入一行注释指向 `requirements.lock`）。

**验收：** CI 新增检查生效；pytest 基线全绿记录在案。

### P1：拆分 `database.py`（1 天，低风险）

纯物理拆分，不改任何行为：

1. 新建 `infrastructure/persistence/migrations.py`：迁入全部 `_upgrade_1..18`、`_downgrade_1..18`、`_MIGRATIONS`、`_run_migrations`、`run_upgrade`、`downgrade`、`get_migration_status`。
2. `database.py` 保留：`get_connection`、`reset_connection`、`init_db`、`_json_dumps/_json_loads`，并从 `migrations.py` 导入执行入口。
3. 为兼容存量 import（tests、其他模块），在 `database.py` 顶层 re-export 迁移公共 API（`downgrade`、`get_migration_status`、`run_upgrade`），标注"兼容导出，新代码请从 `migrations.py` 导入"。

**测试：** 现有迁移相关集成测试（`test_news_favorites_migration.py` 等）必须原样通过；新增一个"迁移函数全部注册且版本连续"的单元测试。

**验收：** `database.py` ≤ 200 行；迁移测试全绿。

### P2：持久化层依赖反转（2~3 天，核心阶段）

1. `infrastructure/persistence/connection.py`：连接管理从 `database.py` 进一步独立（`database.py` 转为兼容壳或整体迁入，最终删除）。
2. domain 侧定义端口（Protocol）：
   - 对已是仓储形态的模块（`domain/agent/repository.py`、`domain/travel/itinerary/repository.py`、`domain/feedback/repository.py`）：**接口留 domain，实现迁 infrastructure** —— domain 保留 Protocol（如 `CustomAgentRepositoryPort`），SQLite 实现移至 `infrastructure/persistence/repositories/`。
   - 对 Manager 形态模块（`SessionManager`、`ProfileManager`、`MemoryManager/Extractor/Distiller`、`task_state`、`auth.py/token.py`）：抽出 `ConnectionProvider` Protocol（或聚合级 Repository Protocol）注入构造函数；SQL 语句下沉至 infrastructure 实现类。
3. `app.py` 组合根统一构造连接提供器与各仓储实现，注入所有消费方（orchestrator、factory、application 服务、api 依赖）。
4. `domain/user/auth`：`PasswordHasherPort` 注入，移除 `infrastructure.security.password` 直接 import。

**测试（先行）：** 为每个被反转的仓储/Manager 先写"使用 fake 端口实现"的单元测试（这正是反转的红利——domain 首次可以脱离 SQLite 单测）；现有 session/memory/auth/itinerary 集成测试原样通过。

**验收：** `rg "from infrastructure|import infrastructure" domain/` 中持久化相关条目清零；新增 domain 纯单测 ≥ 10 个；覆盖率不下降。

### P3：LLM 依赖反转（1 天，中低风险）

1. 新建 `domain/shared/llm/ports.py`：`LLMPort` Protocol + `LLMResponse`、`ToolCallResult` 等类型**从 `infrastructure/llm/openai.py` 上移**到 domain（infrastructure 改为从 domain import 这些类型，方向反转）。
2. 全量替换 domain 层类型注解：`OpenAILLM` → `LLMPort`（约 11 个文件）；`app.py` 中 `# type: ignore[arg-type]` 的 FallbackLLM 契约问题随之消解（二者结构性满足同一 Protocol）。
3. `FallbackLLM` 保持 infrastructure 不变，验证其结构满足 `LLMPort`。

**测试：** 现有 `test_fallback_llm.py`、编排器/分类器单测原样通过；mypy 必须无新增 ignore。

**验收：** domain 层 `OpenAILLM` import 清零；`app.py` 不再出现 `# type: ignore[arg-type]`。

### P4：工具框架归属迁移 + MCP 端口化（1~2 天）

1. 迁移（纯移动 + import 更新）：`infrastructure/tools/{base,registry,executor,catalog,policy}.py` → `domain/shared/tools/`。这些是框架本体，无直接外部 I/O，本属领域能力。
2. `infrastructure/tools/adapters/`（http/amap/fliggy/qweather/drive_cost/shared/interaction）留在 infrastructure，反向 import domain 框架并注册。
3. MCP：domain 定义 `MCPRuntimePort`、`MCPCatalogPort`（Protocol），`infrastructure/mcp/{runtime,catalog}.py` 结构性实现；`domain/travel/core.py`、`factory.py`、`dynamic_agent.py`、`context_preparer.py` 改为依赖端口注解。
4. `domain/travel/tools/travel_tools.py`、`domain/reasoning/tool_selector.py` 改为从 `domain.shared.tools` import。

**验收：** domain 层 `infrastructure.tools` / `infrastructure.mcp` import 清零；工具相关单测原样通过。

### P5：拆分 `engine.py`（1~2 天，中风险，必须最后做）

前置：P2~P4 完成后 `ReasoningEngine` 依赖面已清晰；先补 `run`/`run_stream` 的行为级单测（fake LLMPort 脚本化响应），再拆分：

1. `domain/reasoning/json_extract.py`：`_strip_code_fences`、`_extract_json_by_brackets`、`_extract_json_object`（纯函数）。
2. `domain/reasoning/decision_parser.py`：`_parse_decision` 族 8 个方法 → 独立 `DecisionParser` 类或纯函数集（`_try_fix_json`、regex/XML 解析等）。
3. `domain/reasoning/text_cleaning.py`：`_clean_final_answer`、`_strip_reasoning_prefix`、`_strip_tool_calls_from_text`、`_looks_grounded`、`_make_signature`、`_tool_status_text`。
4. `engine.py` 仅保留 `ReasoningEngine` 主流程（`run`、`run_stream`、工具执行编排），目标 ≤ 500 行。
5. 兼容导出：`domain/reasoning/__init__.py` 保持现有公共 import 路径不变。

**验收：** 新增行为级单测覆盖 run/run_stream 主分支；engine.py ≤ 500 行；全门禁绿。

### P6：工具链收紧 + 前端对齐（半天~1 天）

1. `pyproject.toml`：ruff 移除 `B904`、`F401` 豁免并修复全部现存违规；mypy 评估开启 `warn_return_any`、逐步收紧（如改动面过大，单独立项，不在本计划阻塞）。
2. `Makefile`：`test` 目标补齐 `--cov-fail-under=70`，与 CI 一致。
3. `tests/e2e/`：新增最小 e2e 冒烟（TestClient 打 `/api/v1/health` + 一条未认证 401/404 路径），使三层测试名副其实。
4. 前端（小步、不阻塞后端阶段）：
   - `src/utils/api.ts` 头部标注 legacy  deprecation 注释；其中尚有消费方的函数逐步迁入对应 `features/<domain>/api.ts`，清空后删除文件。
   - `features/travel/api.ts`（542 行）按 行程/地理编码/草稿存档 拆为三个模块，`features/travel/` 内聚。

**验收：** CI 全绿；前端 lint/check/test/build 四连绿。

### P7：AGENTS.md 定稿（半天）

1. 移除 P0 过渡条款，第 2 节分层规则恢复为**陈述事实**（此时代码已满足）。
2. 新增"架构守卫"小节：依赖方向检查命令、违规处理方式、端口新增流程（先 domain 定义端口 → infra 实现 → app.py 注入）。
3. 保留并强化业务红线、安全条款（这些是本轮验证过的高价值条款，不动）。
4. 版本号升 v3.1，日期更新，文末记录本轮清理的完成证据（门禁输出摘要）。

---

## 5. 风险登记与缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| P2 持久化反转改动面大，SQL 下沉时行为漂移 | 高 | 每聚合先写 fake 端口单测 + 现有集成测试双保险；一次只反转一个聚合，逐个提交 |
| `engine.py` 拆分破坏流式行为 | 中 | P5 前必须先补 run_stream 行为测试；拆分只移动纯函数，主流程最后动 |
| 迁移文件物理移动影响已部署库的 `schema_migrations` 记录 | 低 | 只移动 Python 函数，版本号/SQL 内容一字不改；P1 后跑 `get_migration_status` 核对 18 版 |
| Protocol 结构不匹配导致 mypy 大面积报错 | 中 | P3 先在 1 个文件试点验证 Protocol 方法面，再全量推广 |
| 期间业务需求插入 | 中 | 每阶段独立可交付；P0 止血后任何插入需求按新规则开发，不加重债务 |

## 6. 明确不做的事

- 不做任何目录改名/大规模文件迁移（除 P1/P4 列明的模块级移动）。
- 不改动业务行为、API 契约、数据库 schema（本轮零新迁移）。
- 不重写前端状态管理/路由；不引入新框架、新依赖（import-linter 为可选项，可用自研脚本替代）。
- mypy 全量 strict 不在本轮范围（单独立项）。
- ErrorBoundary、toast 等前端体验增强不在本轮范围。

## 7. 工期与顺序总览

| 阶段 | 内容 | 预估 | 依赖 |
|---|---|---|---|
| P0 | 门禁止血 + AGENTS.md 过渡条款 | 0.5 天 | pytest 基线绿 |
| P1 | database.py 拆分 | 1 天 | P0 |
| P2 | 持久化依赖反转 | 2~3 天 | P1 |
| P3 | LLM 依赖反转 | 1 天 | 可与 P2 并行 |
| P4 | 工具框架迁移 + MCP 端口 | 1~2 天 | P3 |
| P5 | engine.py 拆分 | 1~2 天 | P2~P4 |
| P6 | 工具链 + 前端对齐 | 0.5~1 天 | 任意，建议收尾前 |
| P7 | AGENTS.md 定稿 | 0.5 天 | 全部 |

**合计约 7~10 个工作日。** 顺序上 P0→P1→P2 为关键路径；P3 可提前并行。

---

## 8. 与既有文档的关系

- 本计划是 `2026-07-17-refactor-roadmap.md` 的后续专项，不改动业务基线 `2026-07-16-product-and-news-agent-design.md` 的任何业务范围。
- 完成后由 P7 更新 AGENTS.md 至 v3.1；本文件归档为执行记录。
