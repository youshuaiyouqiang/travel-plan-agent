# yunhe（云合）— 项目根记忆

## 项目是什么
云合是**通用多智能体对话平台**：云合调度员识别意图并委派子 Agent（新闻/旅行/学术），汇总结果返回。FastAPI + Pydantic v2 + SQLite 后端，React 18 + TS strict + Vite 6 前端，DDD 四层架构。

## 权威文档（优先级从高到低）
1. 用户指令
2. `AGENTS.md`（开发规范 v3.0）
3. `docs/superpowers/specs/2026-07-16-product-and-news-agent-design.md`（业务基线）+ `docs/superpowers/plans/2026-07-17-refactor-roadmap.md`（执行顺序）
4. 既有代码约定

⚠️ `README.md` 与 `docs/api/` 是过时文档，其中相册/情感识别/多方案比较/打卡/花费/支付等功能已删除且禁止恢复。

## 根目录关键文件
- `app.py`：依赖注入容器——`build_orchestrator()` 装配 LLM（含降级链）、Skill、MCP、工具注册表、内置/自定义 Agent 与云合调度。
- `start.ps1` / `start.sh`：一键启动脚本（后端 uvicorn 8000 + 前端 Vite 5173）。
- `Makefile`：install/dev/lint/typecheck/test 等任务入口。
- `pyproject.toml` / `requirements.lock`：依赖以 lock 为准（`pip install -r requirements.lock`）。
- `.env`：本地真实密钥（已 gitignore，勿提交）。

## 目录导航（每个文件夹均有 memory.md）
- `api/`：FastAPI 路由与中间件（认证/CSRF/限流）。
- `application/`：DTO、用例、授权、会话模式、调度器。
- `domain/`：领域模型、Agent 编排、推理、记忆、用户域（注意：存在直接依赖 infrastructure 的技术债，见 domain/memory.md）。
- `infrastructure/`：SQLite、LLM、限流、MCP、Skill、工具框架。
- `frontend/`：React 前端（features/{auth,chat,news,travel,academic} 组织）。
- `config/`：Settings 与环境变量模板。
- `tests/`：unit（31）/ integration（22）/ e2e（空，缺口）。
- `docs/`：权威 specs/plans 与历史参考文档。
- `data/`：运行时数据（DB/日志/缓存，不入库）。

## 核心安全红线（速查）
- 浏览器认证：HttpOnly Cookie + CSRF；不持久化 token；登录响应无 token 字段。
- 对象级未授权统一 404；身份只取服务端认证上下文。
- SQL 参数化；表名白名单；迁移必须版本化可回滚。
- 敏感信息（密码/密钥/Token/论文草稿/新闻全文）不进日志、审计、仓库。
- 新闻证据只来自 enabled 来源；学术检索只允许 arXiv/论文库；行程外部信息仅用户主动更新。

## 质量门禁
ruff / mypy / bandit / pytest（覆盖率 ≥70%）/ pip_audit / 前端 lint+check+test+build / gitleaks，全部阻断式执行（命令见 AGENTS.md 第 6 节）。
