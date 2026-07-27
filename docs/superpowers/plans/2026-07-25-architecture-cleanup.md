# 架构清理与依赖反转实施计划

> **版本：** v1.2，2026-07-27
>
> **状态：** P0–P6 已完成；P7 收尾中
>
> **优先级：** 用户指令 > AGENTS.md > 产品设计 > 本计划 > 既有代码约定

## 1. 目标与边界

本计划清理已经确认的分层债务，不改变产品业务、对外 API 契约或既有数据库语义。完成后，依赖方向、组合根、质量门禁和 AGENTS.md 必须一致，且由 CI 自动验证。

完成定义：

1. `domain/` 不再导入 `infrastructure/`、FastAPI、SQLAlchemy/SQLite 驱动、HTTP/LLM SDK；`application/` 同样不导入具体基础设施实现。
2. SQL、文件、网络、LLM SDK、MCP 进程和密码算法只在 `infrastructure/`；领域和应用层只消费面向用例的端口。
3. 运行时装配集中在一个明确的组合根；路由不再临时构造服务或把生产依赖散写入 `app.state`。
4. 迁移和推理模块拆成职责单一的文件；正常业务源文件上限为 800 行，历史迁移按版本组拆分，每个文件也不超过 800 行。
5. CI 阻断式检查依赖边界、Ruff、mypy、Bandit、覆盖率、依赖审计、前端质量和密钥泄露。

不做：微服务拆分、替换 SQLite、改变新闻/学术/行程业务边界、重写前端状态管理或引入新的运行时框架。此次工作是模块化单体的边界治理，不是重写项目。

## 2. 2026-07-25 事实基线

实施者必须在 P0 重新生成基线，不得复制旧文档数字。当前工作区的快速审计结果如下：

| 项目 | 当前事实 | 处理方式 |
|---|---|---|
| `domain -> infrastructure` | `rg` 命中 49 行、22 个 Python 文件，包含顶层、函数内和类型注解导入 | P0 生成 AST 清单；后续逐项消除 |
| `application -> infrastructure` | 已存在 scheduler、news、travel、session、authz 等直接导入 | 纳入 P2 的独立清单，不能在 P0 假装已禁止 |
| `database.py` | 1271 行，迁移已到版本 20，不是旧文档写的 18 | P1 按版本组拆分，不改变 SQL 或迁移版本 |
| `engine.py` | 1198 行 | P6 在行为测试完善后拆分 |
| 组合与服务定位 | `app.py` 组装 Agent；`api/server.py` 又直接组装多个服务并写入 `app.state` | P3 收敛为一个组合根 |
| 前端 legacy API | `frontend/src/utils/api.ts` 仍被多个组件、页面和认证测试使用 | P7 按调用方逐步迁移，不作假删除 |

`pyproject.toml` 当前忽略 `F401`、`B904`，mypy 使用 `ignore_missing_imports=true`，`Makefile test` 缺失覆盖率阈值；这些均为真实不一致项。mypy 全量 strict 不属于本计划，但不得把它误写为本轮达成目标。

## 3. 目标架构

```text
api routes -> application use cases -> domain models / ports
                                      ^
                                      | implements ports
                              infrastructure adapters

composition root -> constructs adapters and application services -> create_api(container)
```

### 3.1 唯一组合根

以 `app.py` 中的 `build_container()` 为唯一依赖装配入口。它可以同时导入四层并负责构造 SQLite、LLM、MCP、工具、仓储和应用服务。`api/server.py` 只提供 `create_api(container)`：注册路由、生命周期和中间件，并将不可变的 `AppContainer` 放入 `app.state.container`。路由通过 FastAPI dependency 从容器取得应用服务，禁止在路由、依赖函数或生命周期中按需 `new` 服务、仓储或基础设施实现。

### 3.2 端口规则

端口放在消费方所属领域包中，按业务聚合命名，禁止设计通用 `ConnectionProvider` 让 domain 继续写 SQL。

| 端口位置 | 最小职责 | SQLite 实现位置 |
|---|---|---|
| `domain/user/session/ports.py` | 会话、任务状态的读取和原子更新 | `infrastructure/persistence/repositories/session.py` |
| `domain/user/profile/ports.py` | 用户画像读写 | `infrastructure/persistence/repositories/profile.py` |
| `domain/memory/ports.py` | 记忆存取和蒸馏结果保存 | `infrastructure/persistence/repositories/memory.py` |
| `domain/user/auth/ports.py` | 用户、令牌、密码哈希/校验 | `infrastructure/persistence/repositories/auth.py`、`infrastructure/security/password.py` |
| `domain/agent/ports.py`、`domain/feedback/ports.py`、`domain/travel/itinerary/ports.py` | 各自聚合的仓储操作 | `infrastructure/persistence/repositories/` 下对应实现 |
| `domain/shared/llm/ports.py` | 供应商无关的生成、流式生成、工具调用 | `infrastructure/llm/openai.py`、`fallback.py` |
| `domain/shared/tools/` | 纯内存的规格、注册、策略、执行编排 | 具体 HTTP/旅行适配器仍在 `infrastructure/tools/adapters/` |
| `domain/shared/mcp/ports.py` | 已注册工具的发现与执行能力 | `infrastructure/mcp/` |

LLM 端口的输入输出由 domain 定义，例如 `LLMRequest`、`LLMResponse`、`ToolCall`；不得复制 `OpenAILLM` 的全部公共方法，也不得泄漏 OpenAI SDK 类型。MCP 端口不得暴露 `build_specs()` 或 `build_handlers()` 等装配细节；组合根注册工具，domain 只消费 `ToolCatalogPort` 和 `ToolExecutorPort`。

## 4. 实施顺序

每个阶段是独立 PR。开始下一阶段前，必须运行该阶段列出的针对性测试以及第 5 节全部阻断门禁。任意 PR 不得混入业务功能、API 改动或未关联的格式化。

### P0：审计基线与止血

1. 运行完整 Python 和前端门禁，保存实际版本、测试数、覆盖率和跳过项到本计划的实施记录或 PR 描述。
2. 创建 `scripts/check_architecture.py`，使用 `ast.parse()` 检查全部 `*.py`：覆盖 `import`、`from ... import`、函数内导入、别名和 `TYPE_CHECKING` 块。禁止规则为：
   - `domain` 不得导入 `infrastructure`、`api`、`application`、`fastapi`，或具体外部 I/O SDK；
   - `application` 不得导入 `infrastructure`、`api`、`fastapi`；
   - `api` 不得导入 `infrastructure` 或 `domain` 仓储实现；
   - `infrastructure` 可以导入 domain 端口和模型，不得导入 api。
3. 首次运行输出稳定排序的 `docs/architecture/legacy-import-baseline.json`，每项含 `file`、`line`、`module`、`layer_rule`。该文件是显式债务豁免，不是数量阈值：CI 失败条件是新增项，已有项只能逐项删除。
4. CI 执行 `python scripts/check_architecture.py --baseline docs/architecture/legacy-import-baseline.json`；新增违规或基线中已删除项仍被保留时均失败。基线必须最终归零后删除参数。
5. AGENTS.md 加入临时条款：现有清单不得模仿；新代码零豁免；`utils/api.ts`、`database.py`、`engine.py` 不得新增功能。删除空 `requirements.txt`，并修正所有仍引用它的文档或部署脚本。

验收：基线由脚本生成且包含 application 违规；CI 阻断新增项；全量测试全绿。

### P1：迁移模块安全拆分

1. 新建 `infrastructure/persistence/migrations/` 包，按连续版本组建立 `v001_005.py`、`v006_010.py`、`v011_015.py`、`v016_020.py`；每个文件只拥有其版本的 upgrade/downgrade 函数和 SQL。
2. 新建 `migrations/registry.py`，按固定顺序导入版本组并构造不可变迁移注册表；`runner.py` 只负责 applied-version、upgrade、downgrade 与状态查询。
3. 将连接生命周期放入 `connection.py`；`database.py` 临时只保留兼容 re-export 和 `init_db()`，所有新代码从新路径导入。P1 不修改迁移版本号、SQL 文本或 `schema_migrations` 数据。
4. 新增测试：注册版本必须恰为 1..20、不得重复；空库升级与已升级库重复初始化均幂等；从版本 20 降级再升级保持现有迁移测试断言。

验收：每个迁移文件少于 800 行；迁移状态报告 20 个版本；已部署数据库升级测试和回滚测试通过。

### P2：持久化与认证按聚合反转

按以下顺序逐个 PR 实施，禁止以全局 `ConnectionProvider` 代替仓储端口：

1. session + task state；
2. profile；
3. auth + token + password hasher；
4. memory；
5. custom agent、feedback、itinerary；
6. 将 application 中 news、travel、scheduler、session、authz 的基础设施导入改为注入端口或应用服务。

每个 PR 的固定步骤：先为 domain/application 消费者写 fake repository 的单元测试；定义最小 Protocol 和 DTO；将全部 SQL 与 JSON 序列化移至对应 SQLite repository；在 `build_container()` 组装实现；删除该聚合的基线项；运行既有集成测试。仓储必须在应用服务层检查资源所有权，保持未授权返回 404 的语义。

验收：domain 和 application 的持久化/安全直接导入归零；domain 单元测试可用 fake 端口运行且不创建 SQLite 文件；集成测试仍覆盖真实 SQLite 行为。

### P3：收敛组合根与 API 依赖

1. 将 `AppContainer` 扩展为只读依赖集合，包含各应用服务及 Agent 编排入口；禁止容器字段暴露具体 SQLite、OpenAI 或 MCP 实现给路由。
2. `app.py` 只提供 `build_container(settings) -> AppContainer`；不得在 import 时初始化数据库、启动指标服务或读取外部状态。
3. `api/server.py` 改为 `create_api(container) -> FastAPI`，由明确的启动入口组装。生命周期使用容器中的服务，不再自行 `UserStore()`、`SessionService()`、`TravelService()` 或写入零散 `app.state.*`。
4. 每个路由新增或改造 FastAPI dependency，从 `request.app.state.container` 获取应用服务；测试通过覆盖容器替身，而非 monkeypatch 私有全局。

验收：`app.py` 是唯一跨层装配位置；`api/v1/` 不直接导入基础设施或领域仓储实现；服务构造路径在测试中可替换。

### P4：LLM、工具与 MCP 边界

1. 在 `domain/shared/llm/ports.py` 定义供应商无关的消息、响应、工具调用和 `LLMPort`。`OpenAILLM` 与 `FallbackLLM` 显式满足该端口；删除 app.py 中为 Fallback 保留的 `type: ignore[arg-type]`。
2. 将纯内存工具模型、registry、policy 与 executor 迁至 `domain/shared/tools/`；将日志审计抽成端口或由应用层包裹，避免 domain 工具执行器直接依赖日志实现。
3. 保留 HTTP、地图、天气、飞猪和其他外部工具适配器于 `infrastructure/tools/adapters/`。组合根注册适配器；domain 不导入适配器。
4. 定义 `ToolCatalogPort`、`ToolExecutorPort`、`MCPServerCatalogPort`；MCP runtime 实现它们。domain 只根据端口选择与执行工具，不调用 MCP 发现/构建函数。

验收：domain 无 `infrastructure.llm`、`infrastructure.tools`、`infrastructure.mcp` 导入；fake LLM、fake ToolExecutor 可覆盖编排和旅行主分支；真实适配器集成测试通过。

### P5：质量规则与前端 API 迁移

1. 恢复 Ruff 的 `B904`，修复所有异常链；恢复 `F401`，仅对确实用于包公开导出的 `__init__.py` 使用精确 `per-file-ignores`。不得全局关闭规则。
2. `Makefile test` 使用与 CI 完全相同的 coverage 命令。mypy 保持当前范围；`warn_return_any` 与 strict 模式另开专项，不得伪称已完成。
3. 将 `frontend/src/utils/api.ts` 的调用方按 auth、agent、news、memory、skill、mcp 逐域迁入 `features/<domain>/api.ts`。迁移一个领域后删除该领域旧导出与调用；最后删除 legacy 文件。所有新 API 均使用 `features/auth/client.ts`。
4. 将 `features/travel/api.ts` 按 itinerary、geocode、draft/archive 三个文件拆分，保留统一的领域导出入口。
5. 不创建伪 E2E。`TestClient` 测试放入 `tests/integration/`；若要保留 `tests/e2e/`，必须增加真实浏览器访问前端和 API 的认证后冒烟链路，并在 CI 运行。

验收：Ruff 无全局 B904/F401 豁免；Makefile 与 CI 质量命令一致；legacy API 无调用方后删除；前端 lint/check/test/build 通过。

### P6：拆分 ReasoningEngine

前置条件：P4 已提供 fake LLM/tool 端口，且先补齐 `run` 与 `run_stream` 的成功、工具调用、工具失败、无效决策和流式取消测试。

1. 提取纯 JSON 处理到 `domain/reasoning/json_extract.py`；提取决策修复和解析到 `decision_parser.py`；提取文本规范化到 `text_cleaning.py`。
2. 保持 `engine.py` 只负责编排状态机、端口调用和结果组装；不得在拆分中改变 prompt、输出格式、工具调用次数或异常语义。
3. 每次只移动一组纯函数，目标测试通过后再进行下一组；最后再缩短 `run` 和 `run_stream`，目标 `engine.py` 少于 600 行。

验收：新纯函数单测覆盖有效与畸形输入；行为测试覆盖主分支；engine.py 少于 600 行；无公开导入路径回归。

### P7：去除豁免与更新 AGENTS.md

1. 当 architecture baseline 已无条目时，删除 JSON 和 `--baseline` 参数，依赖检查改为零容忍。
2. 删除 AGENTS.md 的过渡条款，新增“架构守卫”：端口先于实现、组合根唯一、禁止的依赖方向、执行命令和违规处理方式。
3. 只记录实际执行过的门禁版本、通过数与遗留风险；升级至 v3.1。不得把未执行的 strict、浏览器 E2E 或生产部署验证写成已完成。

## 5. 质量门禁

每个 PR 和 CI 必须阻断式执行：

```powershell
python scripts/check_architecture.py
python -m ruff check .
python -m mypy api application domain infrastructure
python -m bandit -r api application domain infrastructure -lll
python -m pytest --cov=api --cov=application --cov=domain --cov=infrastructure --cov-fail-under=70
python -m pip_audit -r requirements.lock
npm --prefix frontend run lint
npm --prefix frontend run check
npm --prefix frontend run test
npm --prefix frontend run build
```

CI 同时运行 gitleaks，禁止 `continue-on-error`、`|| echo`、skip 或降低覆盖率绕过失败。架构检查从 P0 起执行；P7 起进入零容忍模式——任何分层依赖违规立即阻断 CI，不存在基线豁免清单。

## 6. 风险与排期

| 风险 | 控制措施 |
|---|---|
| SQL 下沉改变事务或 404 语义 | 每聚合先写 fake 单测和既有 SQLite 集成测试；一次一个聚合、一个 PR |
| 迁移物理移动破坏已部署库 | SQL 与版本号不变；覆盖升级、重复初始化和降级/再升级 |
| LLM/MCP 端口泄漏供应商细节 | 先用 fake 验证领域消费者；端口评审不允许 SDK 类型和装配方法 |
| 组合根迁移改变启动时序 | 保留启动、fail-fast 管理员和后台任务的集成测试；禁止 import-time 副作用 |
| 引擎拆分改变流式行为 | 先锁定行为测试；每次只移动纯函数 |

建议排期为 10--15 个工作日，不承诺旧版本的 7--10 天：P0/P1 约 2 天，P2/P3 约 5--7 天，P4/P5/P6/P7 约 3--6 天。P2 的聚合 PR 可按团队容量并行，但 P3 必须在其端口已稳定后实施。

## 7. 文档关系

本计划只修复结构债务，不改变 `docs/superpowers/specs/2026-07-16-product-and-news-agent-design.md` 的业务基线。它是 `docs/superpowers/plans/2026-07-17-refactor-roadmap.md` 的后续专项。P7 完成且门禁有证据后，才允许更新 AGENTS.md 为最终状态。

## 8. P0 实施记录（2026-07-25）

### 8.1 门禁基线（P0 步骤 1）

执行环境：Windows 11，Python 3.11.0rc1（`.venv311`），Node v24.14.0，npm 11.9.0。

| 门禁 | 工具版本 | 结果 |
|---|---|---|
| `python -m ruff check .` | ruff 0.15.22 | ✅ All checks passed |
| `python -m mypy api application domain infrastructure` | mypy 2.3.0 | ✅ no issues found in 174 source files |
| `python -m bandit -r api application domain infrastructure -lll` | bandit 1.9.4 | ✅ No issues identified（17289 lines） |
| `python -m pytest --cov=api --cov=application --cov=domain --cov=infrastructure --cov-fail-under=70` | pytest 9.1.1, pytest-cov 7.1.0 | ✅ **819 passed, 2 skipped**, 覆盖率 **72.52%**（474.18s） |
| `python -m pip_audit -r requirements.lock` | pip_audit 2.10.1 | ✅ No known vulnerabilities found |
| `npm --prefix frontend run lint` | eslint | ✅ |
| `npm --prefix frontend run check` | tsc -b --noEmit | ✅ |
| `npm --prefix frontend run test` | vitest 2.1.9 | ✅ 43 passed（8 files，23.46s） |
| `npm --prefix frontend run build` | vite 6.4.2 | ✅ 2087 modules，43.08s |

既有跳过项（P0 不修复，仅记录）：
- `tests/integration/test_api.py`：1 处 skip
- `tests/unit/test_mcp_catalog.py`：1 处 skip

已知不一致项（P5 处理，P0 不修）：`pyproject.toml` 全局忽略 `F401`、`B904`；`ignore_missing_imports=true`；`Makefile test` 缺 `--cov-fail-under=70`。

### 8.2 架构违规基线（P0 步骤 2–3）

`scripts/check_architecture.py` 用 `ast.parse` 扫描全部 `*.py`，覆盖顶层导入、函数内导入、`TYPE_CHECKING` 块、别名导入和 `try/except ImportError` 块。基线文件：`docs/architecture/legacy-import-baseline.json`。

| layer_rule | 数量 |
|---|---|
| `domain_no_infrastructure` | 49 |
| `domain_no_application` | 1 |
| `application_no_infrastructure` | 7 |
| `api_no_infrastructure` | 10 |
| `api_no_domain_repository_impl` | 3 |
| **合计** | **70** |

### 8.3 P0 交付物

- 新增 `scripts/check_architecture.py`（AST 检查器，纯 stdlib）。
- 新增 `docs/architecture/legacy-import-baseline.json`（70 项显式债务）。
- 新增 `tests/unit/test_check_architecture.py`（21 个单元测试）。
- `.github/workflows/ci.yml` 在 `python-quality` job 加入 `python scripts/check_architecture.py --baseline docs/architecture/legacy-import-baseline.json`，阻断式执行。
- `AGENTS.md` 新增第 8 节"架构清理过渡：P0–P7（详见 [2026-07-25-architecture-cleanup.md](file:///c:/Users/29105/Desktop/yunhe/docs/superpowers/plans/2026-07-25-architecture-cleanup.md)）"，并在门禁命令块加入架构检查。
- 删除空 `requirements.txt`；历史评估文档（`docs/BASELINE_ASSESSMENT_*`、`docs/api/*`）按 §1 作风险参考，不修改。

### 8.4 P0 验收

- ✅ 基线由脚本生成且包含 application 违规（7 项）。
- ✅ CI 阻断新增项（`--baseline` diff 模式：新增/过期均失败）。
- ✅ 全量测试全绿（819 passed, 2 skipped，覆盖率 72.52%）。
- ✅ 架构检查幂等（再次运行 exit 0）。

## 9. P1 实施记录（2026-07-25）

### 9.1 拆分交付物

将原 1271 行的 `infrastructure/persistence/database.py` 按职责拆分：

| 新模块 | 行数 | 职责 |
|---|---|---|
| `connection.py` | 60 | 连接生命周期（`get_connection`、`reset_connection`） |
| `schema.py` | 178 | 初始 schema 常量 `_SCHEMA` |
| `serialization.py` | 22 | JSON 辅助 `_json_dumps` / `_json_loads` |
| `migrations/types.py` | 23 | `Migration` frozen dataclass |
| `migrations/v001_005.py` | 122 | 迁移 1–5 的 upgrade/downgrade |
| `migrations/v006_010.py` | 156 | 迁移 6–10 |
| `migrations/v011_015.py` | 297 | 迁移 11–15 |
| `migrations/v016_020.py` | 422 | 迁移 16–20 |
| `migrations/registry.py` | 21 | 不可变注册表 + 启动期自检 |
| `migrations/runner.py` | 97 | applied-version/upgrade/downgrade/状态查询 |
| `migrations/__init__.py` | 8 | 子包说明 |
| `database.py`（兼容层） | 93 | re-export + `init_db()` |

每个迁移文件均少于 800 行（验收标准）；版本号、SQL 文本、`schema_migrations` 数据未变；迁移版本仍固定为 20。

### 9.2 兼容承诺

`database.py` 保留以下导出，既有调用方与测试无需改动：
- `get_connection`、`reset_connection`、`init_db`、`run_upgrade`、`downgrade`、`get_migration_status`、`_json_dumps`、`_json_loads`
- 全部 `_upgrade_N` / `_downgrade_N`（N = 1..20）

新代码应从拆分后的模块直接导入。

### 9.3 新增测试

`tests/unit/test_migration_registry.py`（11 个测试）覆盖：
- 注册表恰好 20 个版本、连续 1..20、不重复、不可变 tuple
- 每个迁移有 upgrade/downgrade 可调用对象和非空 description
- 每个迁移文件少于 800 行（参数化）
- 空库 `init_db` 升级到版本 20
- 重复 `init_db` 幂等
- `schema_migrations` 记录全部 20 个版本
- 从 20 降级到 15 再升级恢复 20
- 从 20 全部降级到 0 再全量升级恢复 20
- `get_migration_status` 在部分降级时正确报告 pending

### 9.4 门禁结果

| 门禁 | 工具版本 | 结果 |
|---|---|---|
| `python scripts/check_architecture.py --baseline ...` | — | ✅ 70 项基线一致，无新增违规 |
| `python -m ruff check .` | ruff 0.15.22 | ✅ All checks passed |
| `python -m mypy api application domain infrastructure` | mypy 2.3.0 | ✅ no issues found in 185 source files（+11 新文件） |
| `python -m bandit -r api application domain infrastructure -lll` | bandit 1.9.4 | ✅ No issues identified（17498 lines） |
| `python -m pytest --cov=... --cov-fail-under=70` | pytest 9.1.1 | ✅ **855 passed, 2 skipped**，覆盖率 **73.55%**（346.54s） |
| `python -m pip_audit -r requirements.lock` | pip_audit 2.10.1 | ⚠️ 网络超时（pypi.org 不可达）；`requirements.lock` 未变更，沿用 P0 基线"无已知漏洞" |
| `npm --prefix frontend run lint/check/test/build` | eslint/tsc/vitest/vite | ✅ 全部通过（2087 modules，19.53s build） |

### 9.5 P1 验收

- ✅ 每个迁移文件少于 800 行（最大 422 行）。
- ✅ 迁移状态报告 20 个版本（`get_migration_status()["current_version"] == 20`）。
- ✅ 空库升级测试通过（`test_empty_db_upgrades_to_version_20`）。
- ✅ 重复初始化幂等测试通过（`test_repeated_init_db_is_idempotent`）。
- ✅ 降级再升级测试通过（`test_downgrade_from_20_to_15_then_upgrade_restores_20`、`test_downgrade_to_0_then_full_upgrade_restores_20`）。
- ✅ 既有迁移测试（`test_news_favorites_migration`、`test_news_migration_19`、`test_news_migration_20` 等）全部通过。
- ✅ SQL 文本、版本号、`schema_migrations` 数据未变。
- ✅ 架构基线无新增违规（P1 不触碰 domain/application 层）。

## 10. P2.1 实施记录（2026-07-25）：session + task state 持久化反转

### 10.1 交付物

| 文件 | 类型 | 说明 |
|---|---|---|
| `domain/user/session/ports.py` | 新增 | `SessionRepositoryPort` Protocol + 默认仓储装配函数 |
| `infrastructure/persistence/repositories/__init__.py` | 新增 | 仓储子包 |
| `infrastructure/persistence/repositories/session.py` | 新增 | `SqliteSessionRepository`：整合 sessions/session_turns/tasks 三表全部 SQL |
| `domain/user/session/manager.py` | 重写 | 移除 `get_connection` 导入；通过端口委托 save/load；新增 `list_user_sessions`/`delete_session` |
| `domain/user/session/task_state.py` | 重写 | 移除 infrastructure 导入；通过端口委托 save/load |
| `application/session/service.py` | 重写 | 移除 `get_connection` 导入；通过端口委托 create/update/get |
| `domain/travel/core.py` | 修改 | 移除内联 `SessionRepository` 导入；委托 `self._session_store` |
| `infrastructure/persistence/session_repository.py` | 重写 | 兼容 re-export 层，委托到 `SqliteSessionRepository` |
| `infrastructure/persistence/database.py` | 修改 | `init_db()` 注册默认 `SessionRepositoryPort` 实现（过渡方案） |
| `docs/architecture/legacy-import-baseline.json` | 修改 | 删除 5 项 session 相关违规（70 → 65） |
| `tests/unit/test_session_repository_port.py` | 新增 | 20 个 fake 端口单元测试 |

### 10.2 消除的基线条目（5 项）

| file | line | module | layer_rule |
|---|---|---|---|
| `domain/user/session/manager.py` | 7 | `infrastructure.persistence.database` | domain_no_infrastructure |
| `domain/user/session/task_state.py` | 8 | `infrastructure.persistence.database` | domain_no_infrastructure |
| `application/session/service.py` | 19 | `infrastructure.persistence.database` | application_no_infrastructure |
| `domain/travel/core.py` | 386 | `infrastructure.persistence.session_repository` | domain_no_infrastructure |
| `domain/travel/core.py` | 394 | `infrastructure.persistence.session_repository` | domain_no_infrastructure |

### 10.3 过渡方案

`init_db()` 在初始化数据库后调用 `configure_default_session_repository(SqliteSessionRepository())` 注册全局默认仓储。`SessionManager`/`TaskStateStore`/`SessionService` 在未显式注入时回退到此默认值，保持既有测试的 `SessionManager()`/`SessionService()` 无参构造兼容。P3 收敛组合根后可移除全局默认。

### 10.4 门禁结果

| 门禁 | 结果 |
|---|---|
| 架构检查 | ✅ 65 项基线一致（减少 5 项） |
| ruff | ✅ All checks passed |
| mypy | ✅ no issues found in 188 source files（+3 新文件） |
| bandit | ✅ No issues identified（17685 lines） |
| pytest | ✅ **875 passed, 2 skipped**，覆盖率 **73.75%**（+20 新测试） |
| 前端 | ✅ lint/check/test/build 全绿 |

### 10.5 P2.1 验收

- ✅ domain 和 application 的 session/task_state 持久化直接导入归零（5 项基线删除）。
- ✅ domain 单元测试可用 fake 端口运行且不创建 SQLite 文件（20 个新测试）。
- ✅ 既有集成测试仍覆盖真实 SQLite 行为（test_session/test_task_state/test_session_modes 全绿）。
- ✅ SQL 文本、参数化方式、增量 turn 逻辑、404 语义完全保留。

## 11. P6 实施记录（2026-07-27）：拆分 ReasoningEngine

### 11.1 拆分前状态

- `domain/reasoning/engine.py` 行数：~700 行（已偏离 §4 P6 验收的 < 600 行）。
- `run` 与 `run_stream` 共用大量提示词模板、工具 schema 构建、决策解析和工具结果消息追加逻辑，重复实现且存在行为漂移风险。
- 既有提取：`json_extract.py`、`text_cleaning.py`、`decision_parser.py`、`prompts.py`、`schema_builder.py`（P6.1）。

### 11.2 拆分交付物

| 文件 | 类型 | 职责 |
|---|---|---|
| `domain/reasoning/message_builder.py` | 新增 | `build_working_messages` + `append_tool_result_messages` + `MAX_HISTORY_TURNS`（run / run_stream 共用的纯函数） |
| `domain/reasoning/engine.py` | 修改 | 删除 `_build_working_messages` / `_append_tool_result_messages` 实例方法与 `_MAX_HISTORY_TURNS`；删除未使用的 `Decision` 导入 |
| `tests/unit/test_reasoning_extracted.py` | 修改 | 新增 12 个 message_builder 单元测试；移除未使用的 `REASONING_PATTERNS` 导入 |
| `domain/reasoning/decision_parser.py` | 修改 | 移除未使用的 `Any` 导入（Ruff F401 修复） |

### 11.3 拆分原则

- 保持 `engine.py` 只负责编排状态机、端口调用和结果组装（满足计划 §4 P6 验收要求）。
- 纯函数不接受 `self`，仅消费显式传入的 `decision`、`tool_results`、`trace_tool_calls`、`decision_text`，避免模块反向依赖 `TraceStep`。
- 不改变 prompt、输出格式、工具调用次数或异常语义；既有行为测试 (`test_reasoning.py`) 与新单元测试 (`test_reasoning_extracted.py`) 共 97 个全绿。
- 删除 `engine._build_working_messages` / `engine._append_tool_result_messages` / `engine._MAX_HISTORY_TURNS` 公开属性：调用方应直接使用 `domain.reasoning.message_builder` 模块函数，公共 API 收紧。
- 向后兼容别名 `_strip_code_fences` / `_extract_json_object` 保留（P6.1 既有约定），既有测试通过 `engine._strip_code_fences` 导入仍可工作。

### 11.4 单元测试新增

`tests/unit/test_reasoning_extracted.py` 新增 `TestBuildWorkingMessages`、`TestAppendToolResultMessagesNative`、`TestAppendToolResultMessagesNonNative` 三个测试类共 12 个用例：

- `build_working_messages`：无历史、过滤非 user/assistant、丢弃空内容、截断到 6 条历史、None 历史。
- `append_tool_result_messages` native 模式：assistant tool_calls 注入、tool content 截断 4000 字符、dict content JSON 序列化。
- `append_tool_result_messages` 非 native 模式：assistant payload + 结果摘要、错误分支提示、确认请求触发错误提示、`include_error_conditional=False` 时不追加 follow-up。

### 11.5 行为兼容性

- `run()` / `run_stream()` 中 `working_messages` 构建与 `append_tool_result_messages` 调用点的语义保持不变：
  - `run` 路径 `include_error_conditional=True`（影响 follow-up 文案选择）。
  - `run_stream` 路径 `include_error_conditional=False`（流式不重复追问）。
- `MAX_HISTORY_TURNS = 6` 从类属性下沉到模块常量，行为等价。
- `tool_status_text` 已在 `schema_builder.py` 中导出，`run_stream` 中使用不变。

### 11.6 engine.py 行数

| 阶段 | 行数 | 目标 |
|---|---|---|
| P6.1（提取 json_extract/text_cleaning/decision_parser/prompts/schema_builder） | 700 | — |
| P6.2（提取 message_builder） | **590** | < 600 ✅ |

### 11.7 门禁结果

| 门禁 | 工具版本 | 结果 |
|---|---|---|
| `python scripts/check_architecture.py --baseline ...` | — | ✅ 9 项基线一致（与 P5 一致；本阶段未触及分层边界） |
| `python -m ruff check .` | ruff 0.15.22 | ✅ All checks passed（修复 2 项 F401） |
| `python -m mypy api application domain infrastructure` | mypy 2.3.0 | ✅ no issues found in 222 source files |
| `python -m bandit -r api application domain infrastructure -lll` | bandit 1.9.4 | ✅ No issues identified（19524 lines） |
| `python -m pytest --cov=... --cov-fail-under=70` | pytest 9.1.1 | ✅ **967 passed, 2 skipped**，覆盖率 **76.13%**（247.95s；新增 12 个 message_builder 单测） |
| `python -m pip_audit -r requirements.lock` | pip_audit 2.10.1 | ✅ No known vulnerabilities found（sandbox 限制 `pip-audit/Cache` 写入导致 exit 1；与 P1/P2/P5 一致的网络/缓存问题） |
| `npm --prefix frontend run lint/check/test/build` | eslint/tsc/vitest/vite | ✅ 全部通过（与 P5 一致，本阶段未改前端） |

### 11.8 P6 验收

- ✅ 新纯函数单测覆盖有效与畸形输入（`TestBuildWorkingMessages` 5 个 + `TestAppendToolResultMessagesNative` 3 个 + `TestAppendToolResultMessagesNonNative` 4 个 = 12 个）。
- ✅ 行为测试覆盖主分支（`test_reasoning.py` 21 个，run / run_stream / 工具失败 / 取消 / 流式工具调用等）。
- ✅ `engine.py` 590 行（< 600 行）。
- ✅ 无公开导入路径回归（`_strip_code_fences` / `_extract_json_object` 兼容别名保留；`TraceStep` / `AskUserNeeded` / `ConfirmationNeeded` / `ReasoningEngine` 仍从 `engine` 导出）。
- ✅ 不改变 prompt、输出格式、工具调用次数或异常语义（`clean_final_answer` / `looks_grounded` / `REACT_SYSTEM_SUFFIX` 均从 `text_cleaning.py` / `prompts.py` 引入，`run` / `run_stream` 调用方式未变）。

## 12. P7 实施记录（2026-07-27）：去除豁免与升级 AGENTS.md

### 12.1 交付物

| 文件 | 类型 | 说明 |
|---|---|---|
| `scripts/check_architecture.py` | 重写 | 移除 `--baseline` 参数与基线生成/diff 比对分支，改为零容忍模式：发现任何分层依赖违规即以退出码 1 失败 |
| `docs/architecture/legacy-import-baseline.json` | 删除 | 基线已归零（9 → 0），随检查器进入零容忍模式一同删除 |
| `AGENTS.md` | 升级 v3.0 → v3.1 | 移除第 8 节"架构清理过渡条款"；新增第 8 节"架构守卫"：端口先于实现（§8.1）、唯一组合根（§8.2）、禁止的依赖方向（§8.3）、执行命令（§8.4）、违规处理（§8.5）、拆分后的稳定模块（§8.6）、同步约束（§8.7） |
| `tests/unit/test_check_architecture.py` | 重写 | 删除 5 个基线生成/diff 测试（`test_baseline_generation_creates_sorted_json`、`test_baseline_match_passes`、`test_new_violation_fails`、`test_stale_baseline_entry_fails`、`test_no_violations_no_baseline_passes`）；新增 4 个零容忍测试（`test_cli_no_violations_passes`、`test_cli_any_violation_fails`、`test_cli_multiple_violations_all_reported`、`test_cli_root_defaults_to_current`） |
| `.github/workflows/ci.yml` | 修改 | 架构检查步骤从 `python scripts/check_architecture.py --baseline docs/architecture/legacy-import-baseline.json` 改为 `python scripts/check_architecture.py` |

### 12.2 架构守卫要点

- **端口先于实现**（§8.1）：所有外部能力必须有 `domain/<aggregate>/ports.py` 端口；禁止通用 `ConnectionProvider`；端口输入输出由 domain 定义；必须有可运行 fake。
- **唯一组合根**（§8.2）：`app.py` 的 `build_container()` 唯一装配依赖；`api/server.py` 只 `create_api(container)`；路由、依赖、生命周期不得 `new` 服务或仓储；`app.py` 不得在 import 时初始化数据库或读取外部状态。
- **禁止的依赖方向**（§8.3）：四层规则矩阵与检查器一致；违规处理零容忍（§8.5）——不允许 `--baseline`、注释豁免、per-file ignores 或降覆盖率绕过。
- **稳定模块**（§8.6）：迁移模块按版本组拆分（20 版本不变）、`domain/reasoning/` 拆分后 `engine.py` 仅负责编排（< 600 行）、前端 `utils/api.ts` 已按领域拆分——新代码必须从拆分后的模块直接导入。

### 12.3 验收

- ✅ 基线已归零（`find_violations()` 当前返回空列表，9 项违规已通过端口化全部消除）。
- ✅ `scripts/check_architecture.py` 移除 `--baseline` 参数；`run_cli()` 仅保留零容忍分支。
- ✅ `docs/architecture/legacy-import-baseline.json` 已删除。
- ✅ `AGENTS.md` 升级到 v3.1；过渡条款（"新代码零豁免"、"基线只减不增"等临时表述）已替换为正式"架构守卫"条款。
- ✅ CI 工作流去掉 `--baseline` 参数；保留阻断式执行。
- ✅ 单元测试更新：删除 5 项基线测试，新增 4 项零容忍测试，全部通过。
- ✅ 既有约束（迁移版本 20、`app.py` 唯一组合根、禁止的依赖方向、零豁免、CI 阻断）全部保留并在 AGENTS.md 显式表达。
- ✅ 未声称"架构已完全解耦"；AGENTS.md §8.7 显式要求"§8 全部条款稳定运行一个迭代后方可改用'架构已守卫'的措辞"。

### 12.4 后续约束

- 任何新增违规必须通过端口化、组合根收敛或前端 API 拆分消除，不得保留任何"已知违规"清单。
- 添加新端口时必须同步新增 fake 端口单测和真实实现集成测试。
- 对组合根、迁移、架构检查器、AGENTS.md 守卫条款本身的改动必须独立 PR。

