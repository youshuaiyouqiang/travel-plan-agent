# 云合开发规范

> **版本：** v3.0，2026-07-19
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
