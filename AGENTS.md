# 云合开发规范

> **版本：** v3.2，2026-08-01
>
> **优先级：** 用户指令 > 本文件 > 产品设计与实施计划 > 既有代码约定。

## 1. 权威与现状

- 产品业务基线：`docs/superpowers/specs/2026-07-16-product-and-news-agent-design.md`。
- 重构执行顺序：`docs/superpowers/plans/2026-07-17-refactor-roadmap.md`。
- `docs/api/` 下的旧改造文档和历史基线评估只作风险参考，不得作为业务范围或实现方案的依据。
- 当前后端/前端已完成重构；新增改动必须保持以下业务、安全和质量边界。
- 修改本文件前，必须先验证目标规则已在代码、测试和 CI 中实际落地。

## 2. 技术与目录

- Python 3.11+、FastAPI、Pydantic v2、SQLite、React 18、TypeScript strict、Vite 6。
- Python 依赖以 `requirements.lock` 为准；安装使用 `python -m pip install -r requirements.lock`。
- 前端依赖以 `frontend/package-lock.json` 为准；安装使用 `npm --prefix frontend ci`。

```text
api/              路由、中间件和协议适配
application/      DTO、用例、调度和应用服务
domain/           领域模型、端口和 Agent 编排
infrastructure/   SQLite、LLM、缓存、MCP、外部工具
config/           配置
frontend/src/     React；features/{auth,chat,news,travel,academic}
tests/            unit/、integration/、e2e/
docs/             产品设计、计划、验收报告
```

- API 层只处理协议、认证身份和响应；业务规则在 application/domain；外部 I/O 在 infrastructure。
- 领域代码不得直接依赖具体数据库、HTTP 客户端或 LLM SDK；通过端口或应用服务注入新增依赖。
- 不进行无关的目录迁移、批量改名或格式化；不回滚用户已有的无关改动。

## 3. 业务边界

- 云合是默认调度员：简单问题直接处理；默认会话每轮最多委派一个 Agent，回复后控制权回到云合。
- 用户主动选择专业 Agent 时锁定会话；新闻深度研判必须创建锚定热点的 `news_analysis_locked` 会话，且只能由新闻服务创建。
- 新闻热点由后端定时抓取和缓存；新闻锚点只含标题、来源、URL、摘要和发布时间。
- 正式新闻证据只能来自 `enabled` 来源；未审核来源只能作为未核实线索。
- 学术检索只允许 arXiv/论文数据库；用户草稿只存当前会话，不进长期记忆、画像或审计正文。
- 行程只在用户点击“更新信息”时查询外部数据；仅在用户点击“确认行程”时创建不可变存档。
- 严禁新增或恢复：情感识别、相册、照片/EXIF、游记、行程比较、打卡、实际费用、预订或支付。

## 4. 安全与数据

- 身份、管理员权限与资源所有权只能从服务端认证上下文取得；对象级未授权统一返回 404。
- 浏览器认证使用 `auth_token` HttpOnly Cookie 和独立随机 `csrf_token`；前端 API 必须使用 `features/auth/client.ts` 的 Cookie + CSRF 客户端。
- 浏览器不得持久化或读取长期认证 Token；不得恢复 Bearer Token 前端主路径。
- 非浏览器 Bearer 凭据若新增，必须有专用签发、撤销、审计和测试方案，不能复用登录响应。
- SQL 必须参数化；动态表名只能来自硬编码白名单；禁止接收客户端文件系统路径。
- 密码、密钥、Token、论文草稿、新闻全文和敏感信息不得进入日志、异常详情或仓库。
- 修改 SQLite 结构必须新建版本化迁移和回滚处理；不得修改历史迁移伪造状态。

## 5. 编码与 API

- Python 使用 3.11 内置泛型和 `X | None`；新增 Pydantic DTO 使用 v2 和 `ConfigDict(extra="forbid")`。
- 公共类、公共函数和复杂分支必须有简明、UTF-8 编码的 docstring 或解释性注释；禁止写乱码文本。
- 捕获具体异常并保留异常链；禁止裸 `except`、吞异常和向客户端暴露堆栈。
- 新 API 放在 `/api/v1`；先定义 DTO、授权边界和失败场景，再接入路由。
- 前端保持 TypeScript strict；禁止新增 `any`、未使用导入或 ESLint 禁用注释。
- 新前端 API 仅放入 `frontend/src/features/<domain>/api.ts`，并统一走 `features/auth/client.ts`。

## 6. 测试与 CI

- 每个行为变更先写失败测试，再实现最小代码；认证、授权、迁移、新闻证据和行程存档必须有集成测试。
- 单元测试不得访问真实网络或生产数据；使用 fake、stub 或 mock。
- 禁止通过 skip、降低覆盖率、`continue-on-error`、`|| echo` 或关闭规则绕过失败。
- 本机 Python 启动器无效时，先修复或重建 Python 3.11+ 虚拟环境；不得因无法运行而声称后端门禁通过。

```powershell
# Python
python -m pip install -r requirements.lock
python scripts/check_architecture.py
python -m ruff check .
python -m mypy api application domain infrastructure
python -m bandit -r api application domain infrastructure -lll
python -m pytest --cov=api --cov=application --cov=domain --cov=infrastructure --cov-fail-under=70
python -m pip_audit -r requirements.lock

# Frontend
npm --prefix frontend ci
npm --prefix frontend run lint
npm --prefix frontend run check
npm --prefix frontend run test
npm --prefix frontend run build
```

- `.github/workflows/ci.yml` 必须让上述检查（以及 gitleaks）保持阻断式执行。
- 提交或宣称完成前，运行与变更匹配的命令并报告实际输出。

## 7. 工作方式

- 先阅读目标模块、相邻测试和相关计划，再编辑；优先使用 `rg` 搜索和 `apply_patch` 修改。
- 先报告架构冲突、迁移风险和安全影响；未经明确同意，不执行破坏性数据清理或对外操作。
- 完成一个任务后先自审：业务边界、授权、敏感数据、迁移、测试、前端类型与可访问性。

## 8. 架构守卫

> 实施记录见 `docs/superpowers/plans/2026-07-25-architecture-cleanup.md`（P0–P7）。
> 实施前不得把架构状态写成"已完全解耦"；P7 完成、门禁有证据后方可使用此节作为正式约束。

### 8.1 端口先于实现

- 任何领域/应用层需要数据库、网络、LLM、MCP、缓存、限流、密码学或文件系统等外部能力时，必须先在消费方所属领域包中定义 `Protocol` 端口（如 `domain/<aggregate>/ports.py`、`domain/shared/<capability>/ports.py`）。
- 禁止设计通用 `ConnectionProvider`、`Database` 之类的"通用仓库"让 domain 继续写 SQL；端口按业务聚合命名（`SessionRepositoryPort`、`ItineraryRepositoryPort`、`LLMPort`、`MCPCatalogPort` 等）。
- 端口的输入/输出类型（DTO、`LLMRequest`、`ToolCall`）由 domain 定义；不得复制 `OpenAILLM` 的全部公共方法，不得泄漏 OpenAI SDK、MCP `build_specs()`/`build_handlers()`、SQLite 驱动等装配细节。
- 端口必须有可运行的 fake/stub 实现，领域单元测试不创建真实 SQLite 文件、不发起网络请求。

### 8.2 唯一组合根

- `app.py` 的 `build_container(settings) -> AppContainer` 是唯一依赖装配入口，负责创建 SQLite、LLM、MCP、工具、缓存、限流和应用服务，并显式注入端口实现。
- `api/server.py` 只提供 `create_api(container) -> FastAPI`：注册路由、生命周期和中间件，将 `AppContainer` 放入 `app.state.container`。
- 路由、依赖函数、生命周期钩子不得 `new` 服务、仓储或基础设施实现；只能通过 FastAPI dependency 从 `request.app.state.container` 取得应用服务。
- `app.py` 不得在 import 时初始化数据库、启动指标服务或读取外部状态；启动期副作用集中到 `lifespan` 钩子。

### 8.3 禁止的依赖方向

| 起点 | 禁止的依赖 |
|---|---|
| `domain` | `infrastructure`、`api`、`application`、`fastapi`、具体 I/O SDK（`sqlalchemy`/`aiosqlite`/`sqlite3`/`openai`/`anthropic`/`httpx`/`requests`/`aiohttp`/`urllib3`/`bcrypt`/`passlib`/`cryptography`/`starlette`/`uvicorn`/`redis`/`mcp`） |
| `application` | `infrastructure`、`api`、`fastapi` |
| `api` | `infrastructure`、领域仓储实现模块（`domain.*.repository` / `domain.*.repositories` 及其子模块） |
| `infrastructure` | `api` |

- `application` 可依赖 `domain`（包括仓储端口）；`infrastructure` 可实现 `domain` 端口并消费领域模型。
- 相对导入（`from . import ...`）视为同包内导入，不视为违规。

### 8.4 执行命令

```powershell
python scripts/check_architecture.py        # 零容忍：发现任何违规即失败
python -m ruff check .
python -m mypy api application domain infrastructure
python -m bandit -r api application domain infrastructure -lll
python -m pytest --cov=api --cov=application --cov=domain --cov=infrastructure --cov-fail-under=70
python -m pip_audit -r requirements.lock
```

- 架构检查由 `scripts/check_architecture.py` 实现，使用 `ast.parse` 扫描全部 `*.py`，覆盖顶层、函数内、`TYPE_CHECKING` 块、别名和 `try/except ImportError` 块导入。
- 违规条目使用正斜杠相对路径，保证跨平台 CI 一致。
- `tests/` 与 `scripts/` 目录不参与分层规则检查。

### 8.5 违规处理

- CI 阻断式执行；本地开发运行同一命令预览结果。
- 不允许通过 `--baseline`、per-file ignores、注释豁免或降低覆盖率绕过；必须修改代码消除违规。
- 既有违规必须通过端口化、迁移聚合、组合根收敛或前端 API 拆分消除，不得保留任何"已知违规"清单。
- 新增违规立即在 PR 反馈中修复；不得在 PR 中混入"暂留债务"提交。

### 8.6 拆分后的稳定模块（不得回退合并）

- `infrastructure/persistence/` 已按职责拆分为 `connection.py` / `schema.py` / `serialization.py` / `migrations/`（`v001_005` / `v006_010` / `v011_015` / `v016_020` / `registry` / `runner` / `types`）；`database.py` 仅为兼容 re-export，新代码必须从拆分后的模块直接导入。
- 迁移版本号固定为 20；不得修改历史迁移的 SQL 文本、版本号或 `schema_migrations` 数据。
- `domain/reasoning/` 已拆分为 `json_extract.py` / `text_cleaning.py` / `decision_parser.py` / `prompts.py` / `schema_builder.py` / `message_builder.py`，`engine.py` 仅负责编排状态机与端口调用（目标 < 600 行）。
- 前端 `utils/api.ts` 已按 `features/<domain>/api.ts` 拆分为 auth、chat、memory、agent、skill、mcp、news、travel（itinerary / geocode / draft-archive）等子模块；新 API 仅放入 `features/<domain>/api.ts`，并统一走 `features/auth/client.ts` 的 Cookie + CSRF 客户端。

### 8.7 架构守卫的同步约束

- 任何层违反 §8.3 的依赖方向，必须先开 PR 修复后才能合入；禁止在 PR 中以"暂未拆分"为由遗留。
- 添加新端口时，必须同步新增 fake 端口单测和真实实现集成测试。
- 任何对组合根、迁移、架构检查器、AGENTS.md 守卫条款本身的改动，必须在 PR 描述中显式声明并独立提交。
- 在 §8 全部条款稳定运行一个迭代后，方可在本文件中改用"架构已守卫"的措辞。

## 9. 提交规范

> 任何提交必须遵守本节规则；CI 与代码评审据此校验。**新提交**适用；既有历史 commit 不强制改写。

### 9.1 语言

- 提交信息**全部使用中文**（标题与正文均如此）。
- 范围（scope）保留为**英文代码模块名**（便于 `git log --grep` 与 IDE 跳转）：`stock` / `news` / `auth` / `frontend` / `docs` / `api` / `architecture` / `migration` / `ci` / `agents` / `travel` / `itinerary` / `memory` / `session` / `chat` / `health` / `feedback` / `share` / `geocode` / `mcp` / `skill` 等。
- ASCII 字符仅允许出现在：scope 关键字、文件路径、SQL 标识符、代码片段、命令行示例等代码语境。
- **禁止中英混用**：不允许出现"feat: 新增功能"、"fix: 修复 bug"、"功能: new feature"等半中半英。

### 9.2 格式

```
<类型>(<范围>): <主题>

<正文>
```

- **类型**（必填，从下表选一个）：

  | 类型 | 用途 |
  |------|------|
  | `功能` | 新增用户可见功能 |
  | `修复` | Bug 修复 |
  | `文档` | 仅文档变更（README / docs/ / 注释）|
  | `重构` | 不改变行为的代码结构调整 |
  | `测试` | 仅测试变更 |
  | `构建` | 构建系统 / 依赖改动 |
  | `持续集成` | CI / 工作流配置改动 |
  | `性能` | 性能优化（无功能变更）|
  | `样式` | 代码格式 / 命名风格（无逻辑变更）|
  | `杂项` | 工具 / 配置 / 其他 |

- **范围**（建议填写）：模块名，参考 9.1 列出的关键字。改动跨多个模块时省略或写 `all`。
- **主题**（必填）：简短描述改动，建议 ≤ 50 中文字符；不写句号；祈使语气（"新增" / "修复" / "重构" / "调整"）。
- **正文**（建议填写）：用空行分隔；说明**动机、影响、回归测试、回滚方案**。

### 9.3 显式声明触发条件

涉及以下改动的提交，**必须在正文中显式声明对应条款**（不满足不得合入）：

- 组合根 / 迁移 / 架构检查器 / AGENTS.md 守卫条款本身：声明"本次为 §8.7 要求的独立提交"。
- 新增数据库迁移：声明迁移版本号、SQL 摘要、回滚方式。
- 涉及业务边界调整：声明对应的 AGENTS.md §3 子条款。
- 涉及鉴权 / Cookie / Bearer / CSRF 改动：声明"本次涉及 §4 安全条款"。

### 9.4 示例

```
功能(stock): 新增 stock_fetch_log 表

记录每个股票代码当日的抓取状态（成功 / 失败 / 跳过），
供 warmup 阶段判定是否需要回填。

本次为 Task 20。
```

```
修复(api): 修复 stock review 任务跨用户访问泄漏存在性

原行为：用户 A 通过 GET /stock/review/tasks/{task_id} 访问
用户 B 的 task 时返回 task 数据。
修复：跨用户访问统一返回 404，不暴露 task 存在性。

测试：tests/integration/test_stock_task_auth.py
回归：现有 9 个 stock 集成测试全部通过。
```

### 9.5 紧急例外

- 紧急 hotfix 可在 PR 描述中说明"违反 §9 提交规范的原因"，由 reviewer 决定是否合并。
- 不允许在本地通过 `--no-verify` / `--amend` 绕过本节规则。
