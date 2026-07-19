# 云合开发规范

> **优先级：** 用户指令 > 本文件 > 产品设计与实施计划 > 既有代码约定。
>
> 产品与重构依据：`docs/superpowers/specs/2026-07-16-product-and-news-agent-design.md` 与 `docs/superpowers/plans/2026-07-17-refactor-roadmap.md`。

## 1. 技术基线

- Python 3.11+、FastAPI、Pydantic v2、SQLite、React 18、TypeScript strict、Vite 6。
- Python 依赖锁定文件为 `requirements.lock`；安装命令统一 `pip install -r requirements.lock`。
- Python 质量工具：Ruff、mypy、pytest、pytest-asyncio、bandit、pip-audit。
- 前端质量工具：ESLint、tsc（strict 模式）、Vitest、Vite build。
- 不引入 Black、isort 或 flake8；Python 格式与静态检查统一由 Ruff 管理。

## 2. 目录与分层

```text
api/              FastAPI 路由、依赖和中间件
application/      用例、DTO、调度任务与应用服务
domain/           业务实体、领域服务、端口和 Agent 编排
infrastructure/   SQLite、LLM、缓存、MCP、外部工具与安全实现
config/           配置读取
frontend/         React 前端（features/{chat,travel,academic,news,auth} 按领域拆分）
tests/            Python 测试
docs/             评估、产品设计和实施计划
```

- API 层负责协议、认证身份提取和响应；业务规则放在 application/domain；外部 I/O 放在 infrastructure。
- 领域代码不得直接依赖具体数据库、HTTP 客户端或 LLM SDK；新增依赖通过端口、接口或应用服务注入。
- 新代码优先放入职责最接近的既有模块；单个改动不得跨层制造循环依赖。
- 不进行与当前任务无关的目录迁移、命名批量修改或格式化。

## 3. 业务红线

- 云合是默认调度员：简单通用问题可直接回答；默认会话一轮最多委派一个专业 Agent，回复后控制权回到云合。
- 用户主动选择的 Agent 会锁定当前会话；新闻深度研判必须锁定新闻 Agent 并锚定热点。
- 不新增或恢复情感识别、相册、照片文件/EXIF、游记、行程比较、打卡、实际费用、预订或支付流程。
- 新闻热点由后端定时抓取和缓存；新闻 Agent 的锚点仅包含标题、来源、URL、摘要和发布时间。
- 不抓取、保存、写入记忆或日志新闻全文；未审核来源不得支撑正式事实结论或证据卡片。
- 学术检索仅允许 arXiv 与论文数据库；用户论文草稿只存在于当前会话，禁止进入长期记忆、画像或审计正文。
- 行程只在用户点击"更新信息"时访问外部信息；只有用户点击"确认行程"时创建不可变存档。

## 4. 安全与数据

- 用户 ID、管理员身份和资源所有权只能从服务端认证上下文取得，不信任客户端传入的 `user_id`、角色或路径。
- 所有用户拥有资源在应用服务层执行对象级授权；未授权统一返回 404。
- SQL 必须使用 `?` 参数绑定。动态表名仅可来自代码内硬编码白名单。
- 密码、密钥、Token、草稿正文、新闻全文和其他敏感信息不得写入日志、异常详情或仓库。
- 不接受客户端提供的文件系统路径。
- 新增认证代码不得将长期认证令牌存入浏览器 localStorage 或 sessionStorage。
- 修改表结构必须添加版本化迁移及回滚处理；不得修改历史迁移来伪造新状态。

## 5. 编码与 API 约束

- 使用 Python 3.11 内置泛型和 `X | None`；新增 Pydantic 模型使用 v2 API 与 `ConfigDict(extra="forbid")`。
- 公共函数、公共类和复杂业务分支必须有简明 docstring 或解释性注释。
- 捕获具体异常并保留异常链；禁止裸 `except`、吞掉异常和向客户端暴露内部堆栈。
- 新增 API 放在 `/api/v1`。成功与失败响应必须遵守现有统一响应和异常处理模式。
- 新增或变更 API 时，先定义请求/响应 DTO、权限边界和失败场景，再接入路由。
- 前端使用 TypeScript strict 模式；不得新增 `any`、未使用导入或 ESLint 禁用注释。
- 前端新增 API 按领域放入 `features/{chat,travel,academic,news}/api.ts`，使用 `features/auth/client.ts`（cookie+CSRF）。

## 6. 测试与验证

- 每个行为变更先写会失败的测试，再实现最小代码，再运行目标测试。
- Python 单元测试不访问真实网络或生产数据；外部服务使用 stub、fake 或 mock。
- 改动认证、授权、会话、迁移、新闻证据或行程存档时，必须补充对应集成测试。
- 不通过跳过测试、降低覆盖率、`|| echo` 或关闭规则掩盖失败。

## 7. CI 质量门禁

提交前运行与改动匹配的命令；CI（`.github/workflows/ci.yml`）强制执行以下门禁：

```powershell
# Python
pip install -r requirements.lock
python -m ruff check .
python -m mypy api application domain infrastructure
python -m bandit -r api application domain infrastructure -lll
python -m pytest --cov=api --cov=application --cov=domain --cov=infrastructure --cov-fail-under=70
pip-audit -r requirements.lock

# 前端
npm --prefix frontend ci
npm --prefix frontend run lint
npm --prefix frontend run check
npm --prefix frontend run test
npm --prefix frontend run build
```

- `mypy` 当前以 `continue-on-error` 运行（预存类型债务修复后改为阻断）。
- gitleaks 扫描整库敏感信息泄露。
- 所有安全命令均为阻断式，禁止 `|| echo` 绕过。

## 8. 工作方式

- 先阅读目标模块、相邻测试和相关计划，再编辑。
- 使用 `rg` 搜索；使用 `apply_patch` 或编辑工具修改；不回滚或覆盖用户已有的无关改动。
- 先报告发现的架构冲突、数据迁移风险和安全影响；未经明确同意，不执行破坏性数据清理或对外操作。
- 计划中的新目录、端点、测试工具与 CI 命令，仅在对应计划任务实施时创建。
