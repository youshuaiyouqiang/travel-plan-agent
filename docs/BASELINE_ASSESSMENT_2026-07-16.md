# 云合项目全面基线评估

> **状态说明（2026-07-18）：** 本文是重构前的现状审计记录，用于解释风险来源；不得作为当前产品范围或实施顺序的依据。产品范围以 `docs/superpowers/specs/2026-07-16-product-and-news-agent-design.md` 为准，执行顺序以路线图为准。

**评估日期：** 2026-07-16  
**评估方式：** 只读代码、配置、CI、文档和前端构建检查  
**评估范围：** FastAPI/Python 后端、React/TypeScript 前端、SQLite、Agent/LLM/MCP、测试、CI/CD、开发文档  
**结论等级：** C-，可继续作为开发和演示基线；不满足多用户生产上线条件。

## 1. 结论摘要

项目已具备可运行的单体应用基础：路由已按资源拆分，Pydantic v2、bcrypt、数据库迁移、审计日志、Prometheus 和前端生产构建均已有实现。`app.py` 也已经承担了组合根的一部分职责。

但工程的声明架构和实际运行架构尚未收敛。当前目录呈现 DDD 分层，实际则是 API、领域对象和仓储均直接访问 SQLite、LLM、MCP 和工具实现。对象级授权被复制在路由中且存在遗漏；质量门禁可绕过；生产默认配置不安全；日志、trace 和指标尚不能构成可靠的可观测性体系。

后续工作顺序必须是：先修复 P0 安全与授权边界，再抽取应用服务和端口，之后治理测试、CI、可观测性与目录，最后基于已验证的真实架构重写 `AGENTS.md`。不得以当前 `AGENTS.md` 的理想化目录规则驱动一次性全仓重构。

## 2. 评估证据与限制

### 已执行的验证

- 静态检查了 Python 模块边界、数据库访问、路由、DTO、异常、日志、指标、配置、启动脚本、CI 和文档。
- 检查了约 140 个 Python 文件；其中 5 个核心文件大于 600 行，最大文件为 `domain/reasoning/engine.py`（1293 行）。
- 扫描到 `domain/` 对 `infrastructure/` 的大量直接导入，以及 API 路由对 SQLite 的直接访问。
- 前端 ESLint 实测为 41 errors、1 warning；前端 Vite 生产构建实测成功，入口 JS 636.10 kB、gzip 191.60 kB。
- 检查了现有 15 个测试文件（221 个测试函数定义），其中未发现相册授权、文件路径穿越、令牌撤销、CORS 或生产配置启动失败的回归测试。

### 未完成的验证

本机没有安装项目 Python 运行时，随附 Python 也未带 `pytest` 与 `ruff`，因此本次无法实际运行后端测试、Ruff、mypy、Bandit 或产生可信的后端覆盖率。CI 配置显示这些检查的设计意图，但不能替代本次的执行证据。

### 评分含义

| 维度 | 基线 | 说明 |
| --- | --- | --- |
| 安全与租户隔离 | D | 已发现可利用的对象级授权和路径处理缺陷。 |
| 架构与模块边界 | D+ | 有目录分层和组合根，但实际依赖方向反转。 |
| API 与数据契约 | C- | Pydantic 和异常基础存在，响应/授权/版本策略不一致。 |
| 代码质量与类型 | C- | 存在可维护模块，也有超大文件、宽泛异常和宽松类型配置。 |
| 日志、审计、指标 | C- | 有实现雏形，但敏感数据、trace 和指标设计不满足生产要求。 |
| 测试与 CI | D+ | 测试数量可观，但关键安全路径缺测，CI 可绕过。 |
| 前端工程质量 | C | 生产构建可用，lint 未通过、类型检查宽松、首包过大。 |
| 配置、交付与文档 | D+ | 启动脚本可用，但生产默认值、依赖交付和文档同步存在风险。 |

## 3. P0：阻塞多用户上线的问题

### 3.1 相册资源未实施统一对象级授权

相册上传会校验行程所有权，但列表、更新、封面、地图和游记端点只检查用户已登录，未验证请求的行程或照片属于该用户。服务层的 `list_photos`、`set_cover`、`update_photo` 和 `generate_travelogue` 也没有用户参数，因此无法作为最终授权边界。

影响：已登录用户可以枚举或利用他人的 `itinerary_id` 读取照片、GPS、标签和封面，修改照片/封面，或触发对他人数据的 LLM 调用。

证据：

- `api/v1/album.py:92`
- `api/v1/album.py:137`
- `api/v1/album.py:160`
- `api/v1/album.py:173`
- `api/v1/album.py:196`
- `domain/travel/album/service.py:240`

### 3.2 图片服务具有路径逃逸风险

图片接口把客户端的 `file_path` 直接拼接到 `data/album` 后并调用 `FileResponse`，未解析路径、验证根目录或核对数据库记录。

影响：带有效认证令牌的请求可能用 `..`、编码路径或符号链接访问相册目录之外的可读文件，例如项目配置文件；同时路径接口无法证明返回文件属于当前用户。

证据：

- `api/v1/album.py:209`
- `api/v1/album.py:220`

### 3.3 行程和会话授权不完整

`GET /itineraries/{id}` 仅验证登录，不验证行程归属。活动修改先验证 URL 中行程归属，再仅按 `activity_id` 查询和修改，未验证活动是否属于该行程。分享链接列表/删除不验证行程归属；会话方案确认与查询按 `session_id` 操作，未验证会话用户归属。

影响：跨用户读取、修改或删除数据；在 ID 可猜测或泄露时可形成越权链。

证据：

- `api/v1/itinerary.py:197`
- `api/v1/itinerary.py:242`
- `api/v1/itinerary.py:269`
- `api/v1/itinerary.py:283`
- `api/v1/itinerary.py:377`
- `api/v1/itinerary.py:387`
- `api/v1/session.py:84`
- `api/v1/session.py:147`
- `api/v1/session.py:188`

### 3.4 调试和 trace 数据未隔离

调试路由由认证中间件直接放行，端点没有管理员控制或会话所有权校验。trace 还保存用户消息和记忆上下文，并存于进程内字典。

影响：普通访问者可读取会话、MCP、工具和可能含个人信息/提示词的 trace；多进程部署时 trace 行为不一致且重启丢失。

证据：

- `api/middleware/auth.py:62`
- `api/v1/debug.py:12`
- `domain/shared/runtime/trace.py:13`
- `domain/shared/runtime/trace.py:45`

## 4. 架构与目录基线

### 4.1 当前架构不是可执行的 DDD

目录命名为 `api -> application -> domain -> infrastructure`，但真实依赖方向广泛反转：领域层直接导入 `OpenAILLM`、`MCPProxyRuntime`、`ToolExecutor`、`ToolRegistry`、`get_connection` 等具体实现；领域下还存放 SQLite repository。API 路由直接创建 repository、直接执行 SQL、负责业务计算和事务处理。

这不是“轻微不纯”的 DDD，而是把技术实现分散在三层中。后果是：测试需要打到全局数据库/配置，授权规则复制，替换 LLM/DB 困难，无法明确事务和审计边界。

典型证据：

- `domain/reasoning/engine.py:11`
- `domain/travel/core.py:10`
- `domain/memory/manager.py:9`
- `domain/user/auth/auth.py:8`
- `domain/travel/itinerary/repository.py:7`
- `api/v1/itinerary.py:120`
- `api/v1/session.py:99`
- `api/v1/news.py:32`

### 4.2 推荐的目标边界

保留单体部署，采用“模块化单体”而非一次性微服务化：

```text
api/                         HTTP、身份提取、DTO 映射
application/<bounded_context>/  用例、授权、事务、端口接口
domain/<bounded_context>/       实体、值对象、领域规则；不导入基础设施
infrastructure/              SQLite、LLM、MCP、Redis、文件、外部 HTTP 的适配器
bootstrap/ 或 app.py         组合根：注入适配器并创建应用服务
```

第一批 bounded context 应为 `identity`、`sessions`、`itineraries`、`album`、`agents`。Agent/LLM/MCP 编排应在该基础稳定后拆分，避免同时改变产品主路径与技术底座。

### 4.3 目录与模块问题

- `domain/` 同时包含业务模型、SQL repository、HTTP/LLM 工具调用和运行时组件，目录职责不单一。
- `application/` 当前主要容纳 DTO、异常、scheduler、trending，缺少承载核心用例的服务层。
- `api/v1/` 的路由拆分是正确方向，但多个路由仍有全局 repository 单例、SQL、授权、事务和业务计算。
- `app.py` 已是依赖组装点，但还直接负责数据库初始化、指标启动和多个具体类；应演进为唯一组合根，避免导入时产生副作用。
- `api/routes/` 是空目录，README 中的目录图和真实结构均有过时描述。

### 4.4 高风险大文件

大文件不是自动缺陷，但以下文件同时具有多职责和高变更风险，应按用例/策略拆分：

| 文件 | 行数 | 观察 |
| --- | ---: | --- |
| `domain/reasoning/engine.py` | 1293 | ReAct 解析、执行、流式、兜底解析和 trace 混合。 |
| `infrastructure/persistence/database.py` | 662 | 连接生命周期、完整 schema、迁移和 JSON 工具混合。 |
| `infrastructure/mcp/runtime.py` | 651 | 运行时、协议调用、错误处理和工具代理混合。 |
| `domain/travel/intent/travel_classifier.py` | 645 | 分类规则、LLM 交互和回退逻辑混合。 |
| `domain/agent/orchestrator.py` | 609 | 路由、授权前提、Agent 选择与执行流混合。 |

## 5. API、DTO、数据与异常基线

### 5.1 API 契约不统一

虽然定义了 `ApiResponse` 和 `ErrorResponse`，实际大多数成功路由直接返回不同形状的 dict，错误中间件又返回另一种形状；路由普遍没有 `response_model`、`summary` 或 `description`。同一 router 同时挂载 `/api` 和 `/api/v1`，没有弃用策略或兼容期边界。

影响：OpenAPI 不可靠，前后端类型无法自动对齐，未来破坏性修改难以治理。

证据：

- `application/dto/response/common.py:8`
- `api/server.py:124`
- `api/server.py:128`
- `api/v1/itinerary.py:53`

### 5.2 DTO 的验证强度不足

部分 DTO 已使用 Pydantic v2，但 `UpdateItineraryRequest` 使用 `extra="allow"`，日期、预算、状态、嵌套 `days` 和照片元数据多数是宽泛的 `str`/`dict`/`list`，没有范围、枚举或跨字段校验。认证密码只要求长度 6，低于当前通常的生产基线。

影响：非法数据会穿透到业务/数据库层，导致路由中出现手工 `str()`、`float()`、异常分支和不可预测的 API 行为。

证据：

- `application/dto/request/itinerary.py:48`
- `application/dto/request/itinerary.py:36`
- `application/dto/request/auth.py:13`

### 5.3 数据访问和事务边界分散

SQLite 已启用 WAL 和外键，这是正向基础；也有版本迁移表。但连接由线程本地单例管理、多个层自行 commit/close，API 路由直接执行跨表事务；`auth_tokens` 表在 token 模块中运行时创建，而不是纳入迁移。

影响：事务范围、失败回滚和连接关闭不能统一保证；schema 变更缺少单一来源。

证据：

- `infrastructure/persistence/database.py:17`
- `infrastructure/persistence/database.py:29`
- `domain/user/auth/token.py:21`
- `api/v1/session.py:99`

### 5.4 异常体系有基础但没有边界纪律

自定义 `YunheException` 和明确 HTTP 状态码是正确基础。但业务层和基础设施层约有 93 处 `except Exception`；部分路由把原始异常文字包装到 `InternalException` 或 SSE 事件中。错误 handler 期待 `request.state.trace_id`，但没有全局请求 trace middleware，因此多数普通请求的 trace ID 为 `None`。

目标应是：边界层只负责映射异常；应用服务定义业务错误；适配器捕获已知外部错误并保留 cause；未知错误统一记录、安全响应、关联 trace ID。

证据：

- `application/exceptions/base.py:5`
- `api/middleware/error_handler.py:24`
- `api/v1/chat.py:108`
- `api/v1/session.py:139`
- `api/v1/session.py:182`

## 6. 代码质量、类型、注释与时间处理

### 6.1 类型检查未形成防线

后端 Ruff 忽略了包括未使用导入/变量、导入顺序和多个 bugbear/upgrade 规则在内的较大规则集；mypy 关闭 `warn_return_any`、允许缺失导入、排除 tests。前端 TypeScript 关闭 `strict`、未使用检查和路径大小写一致性检查。

这与当前前端 ESLint 的 41 个 error 相互印证：静态检查工具已安装，但没有作为可信质量信号。

证据：

- `pyproject.toml:48`
- `pyproject.toml:55`
- `frontend/tsconfig.json:19`
- `frontend/src/components/SessionSidebar.tsx:3`

### 6.2 类型、命名和注释不一致

- Python 3.11 项目仍有 `typing.Optional`，大量无参数化 `dict`、`list` 和 `Any`。
- 多个 datetime 使用已废弃且无时区的 `datetime.utcnow()`，数据库中时间字符串格式不完全一致。
- 注释同时混有技术债标签、历史阶段号和实现细节；部分 docstring 缺失或与职责不符。
- 前端的 `utils/api.ts` 聚合了大量类型、HTTP 调用、地理编码和相册逻辑，成为跨领域的巨型模块。

证据：

- `domain/agent/repository.py:5`
- `domain/user/session/task_state.py:31`
- `frontend/src/utils/api.ts:70`
- `frontend/src/pages/ItineraryOverview.tsx:1`

### 6.3 建议的编码标准方向

不要立刻以“所有文件小于 N 行”阻断合并。改用可自动化的渐进标准：

- 新增/修改的公共函数必须完整类型、明确返回值和异常契约。
- 新增 DTO 默认 `extra="forbid"`，复杂输入采用嵌套模型和 validator。
- 业务注释解释决策与不变量，不重复代码；历史迁移说明保留在迁移文档。
- 时间统一使用 `datetime.now(timezone.utc)` 和 ISO 8601 UTC。
- 新增宽泛异常须在边界层，记录原因、关联 ID、重试/降级策略并使用 `raise ... from exc`。

## 7. 日志、审计、trace 与指标基线

### 7.1 日志体系

项目已有 JSON formatter 和 audit logger，这是可保留的基础。问题在于根 logger 固定为 DEBUG，文件 handler 固定 DEBUG，未见统一敏感字段过滤器和请求上下文注入。普通请求没有统一 trace ID，部分 chat 路由手工生成；日志会记录用户消息，trace 保存用户消息和记忆上下文。

影响：生产日志可能暴露个人信息、提示词或敏感上下文；故障排查无法稳定关联单次 HTTP 请求到 LLM/MCP/DB 操作。

证据：

- `domain/shared/runtime/logging.py:63`
- `domain/shared/runtime/logging.py:79`
- `api/v1/chat.py:30`
- `domain/travel/core.py:199`

### 7.2 审计与 trace

`AuditContext` 采用 context variable，是处理并发上下文的正确方向。但 trace 和 debug API 的访问控制不完整，trace 存储没有持久化、容量/TTL 配置和脱敏策略。审计应区分安全审计事件与诊断 trace，不应把原始提示词、会话内容或照片描述无差别保留。

### 7.3 指标体系

Prometheus collector 在指标标签中使用 `session_id`，这是高基数标签，会随着用户/会话增长无界消耗 Prometheus 内存。指标服务器由应用进程另开端口，而 health 路由还提供 metrics 文本，暴露与部署模式不明确。指标也未覆盖 HTTP 状态、授权拒绝、限流、DB、LLM/MCP 依赖失败等关键 SLI。

证据：

- `domain/shared/metrics/collector.py:24`
- `domain/shared/metrics/collector.py:48`
- `domain/shared/metrics/collector.py:86`
- `app.py:119`

## 8. 测试、CI 与前端基线

### 8.1 测试结构

现有测试按 `unit` 和 `integration` 分目录，仓储、记忆、工具、推理和会话已有不少覆盖，这是积极基础。但所谓 API 集成测试使用 mock app，不覆盖实际 `api.server` 中间件、路由、认证、授权、异常 handler 或数据库迁移。`e2e` 目录为空。

必须优先补充真实 TestClient/AsyncClient 的黑盒测试：对象级授权、路径穿越、分享过期/撤销、令牌撤销、限流、异常响应、生产配置和安全头。

证据：

- `tests/integration/test_api.py:29`
- `tests/integration/test_api.py:53`
- `tests/e2e/__init__.py:1`

### 8.2 CI 门禁

CI 执行 Ruff 和 pytest，但全局跳过 `test_prompting`；Bandit 失败被 `|| echo` 转为成功；没有前端 lint、TypeScript check、production build、mypy、依赖漏洞扫描、密钥扫描或覆盖率阈值。Codecov 上传不等于阻断阈值。

证据：

- `.github/workflows/ci.yml:17`
- `.github/workflows/ci.yml:27`
- `.github/workflows/ci.yml:38`

### 8.3 前端

前端 production build 通过，但 lint 实测失败。主要问题是未使用导入/参数、`any`、hook 依赖问题；`strict: false` 让 TypeScript 无法补位。入口包超过默认告警阈值，应将地图、相册、Agent 编辑器和大型对话组件按路由或功能动态加载。

证据：

- `frontend/package.json:7`
- `frontend/tsconfig.json:19`
- `frontend/vite.config.ts:5`
- `frontend/src/pages/ItineraryOverview.tsx:1`

## 9. 配置、交付、部署与文档基线

### 9.1 生产默认值危险

默认日志级别为 DEBUG，Shell 和任意 HTTP 访问默认允许，Redis URL 默认指向本机；CORS 在缺少 `cors_origins` 时退化为 `*` 且允许 credentials。没有显式 `environment`/`production` 设置对象来在启动时拒绝危险组合。

证据：

- `config/settings.py:37`
- `config/settings.py:63`
- `config/settings.py:64`
- `api/server.py:105`

### 9.2 依赖和启动交付不一致

`requirements.txt` 为空，但 README 的本地与 Render 部署示例使用 `pip install -r requirements.txt`；本地启动脚本实际使用 `pip install -e ".[dev]"`。这会导致按 README 部署的环境缺失运行依赖。依赖版本主要是下限，未见锁文件、SBOM、漏洞更新策略或可复现构建。

证据：

- `requirements.txt:1`
- `README.md:292`
- `README.md:327`
- `start.ps1:92`

### 9.3 文档已发生漂移

README 仍引用已删除的 `docs/DEVELOPMENT_SPECIFICATION.md`，且把旧目录/接口结构当作当前事实；API 文档鼓励 localStorage token，并将 `/debug/*` 公开。文档本身因此会把开发者和 AI 引导向不安全实现。

证据：

- `README.md:379`
- `README.md:419`
- `docs/api/API.md:53`
- `docs/api/API.md:86`

## 10. 分阶段改造路线

### 阶段 A：安全与行为冻结

目标：在不改变对外业务能力的前提下，消除 P0 越权和文件读取问题，并把现有 API 行为写成回归测试。

1. 为行程、相册、会话、分享链接和 Agent 建立 application-level `AuthorizationService`。
2. 将图片下载改为“照片 ID -> 授权 -> 数据库记录 -> 受限存储路径”，不接受任意文件路径。
3. 生产默认不注册 debug 路由；开发调试要求管理员和资源归属。
4. 修复共享链接过期校验，增强 token 生命周期和撤销。
5. 新增真实 API 集成测试并将其设为 CI 先决条件。

**完成定义：** 双用户越权、路径穿越、过期链接、撤销 token 和生产 debug 禁用测试在 CI 中通过。

### 阶段 B：核心用例与持久化边界

目标：将正在修复的旅行/相册/会话主路径移动到可测试的应用层，不进行全仓重写。

1. 创建 `application/itinerary`、`application/album`、`application/session` 用例服务。
2. 将 SQL repository 实现移至 `infrastructure/persistence`，在 application 定义端口/协议。
3. 路由只做 DTO/身份转换和调用用例；事务由用例或 unit of work 管理。
4. 迁移 `auth_tokens` 和运行时建表到版本化迁移。
5. 为每个用例建立单元测试，为 API 保留契约测试。

**完成定义：** 目标路由不导入 `get_connection` 或具体 repository；领域模型不导入 SQLite；API 契约兼容测试通过。

### 阶段 C：运行时与 Agent 边界

目标：减少 Agent/LLM/MCP 复杂度对核心业务的渗透。

1. 定义 `LLMClient`、`ToolExecutorPort`、`MCPClient` 端口并由基础设施实现。
2. 拆分 reasoning engine 的决策、解析、工具执行和流式输出职责。
3. 将外部调用统一到 adapter，定义超时、重试、限流、allowlist 和错误映射。
4. 将 trace/审计的持久化、脱敏和访问控制独立于业务对象。

**完成定义：** 领域业务测试可用 fake port 运行，不需要 OpenAI、MCP、Redis 或 SQLite。

### 阶段 D：质量、可观测性和交付

目标：让质量标准由自动化实际执行。

1. 清零前端 ESLint error，逐步开启 TypeScript strict 选项。
2. 缩小 Ruff ignore，按目录恢复 mypy 严格度并设置覆盖率防回退阈值。
3. CI 新增前端 lint/check/build、Bandit/依赖/密钥扫描并禁止忽略失败。
4. 建立全局 request ID middleware、敏感日志过滤器、低基数指标和健康/就绪检查。
5. 修复 README、API 文档和部署方式；提供单一依赖安装方式与锁定策略。

**完成定义：** 所有 required checks 为阻断项；生产启动会拒绝不安全配置；每次发布都有可复现构建和回滚说明。

### 阶段 E：基于事实重写 AGENTS.md

只在阶段 A-D 的关键边界已经落地后执行。新的根目录 `AGENTS.md` 应控制在约 150 行，且只写可验证、已实施的规则：目录边界、授权入口、生产配置、必须运行的命令、迁移约束、测试/CI 门禁和敏感数据规则。细节示例移入 `docs/standards/`。

## 11. 决策原则

- 先保障权限、数据和可观察的正确性，再追求目录纯度或代码行数。
- 每个架构改造以一个可测试的业务路径为单位；不进行“搬目录式重构”。
- 保持 `/api` 兼容层直到版本弃用策略生效；新能力只增加到 `/api/v1` 或后续版本。
- 每个新增硬规范必须能被 CI、测试或明确的审查清单验证。
- 不以引入微服务、消息队列或新数据库作为默认答案；先满足已量化的可靠性和扩展需求。
