# 最终开发验收报告

**验收日期：** 2026-07-19  
**验收范围：** 当前工作区及最新提交 `9b4a311`。  
**结论：** **不通过，不能作为可发布版本或交付完成版本。**

## 已验证的质量门禁

| 命令 | 结果 | 证据 |
| --- | --- | --- |
| `npm --prefix frontend run lint` | 警告 | `frontend/src/pages/Home.tsx:96` 有 `react-hooks/exhaustive-deps` 警告。 |
| `npm --prefix frontend run check` | 通过 | `tsc -b --noEmit` 退出成功。 |
| `npm --prefix frontend run test` | 通过 | 在非受限环境中，Vitest 5 个文件、19 个测试全部通过。 |
| `npm --prefix frontend run build` | 通过但有性能告警 | Vite 构建成功；主 JS 为 614.88 kB（gzip 187.18 kB），超过默认 500 kB 告警阈值。 |
| Python 测试/静态检查 | 未执行 | 当前 shell 没有 `python`；提供的 `D:\python\AI_RAG\.venv` 启动器仍指向不存在的 Python 3.11。 |

受限沙箱内曾出现 Vite/Vitest 配置文件访问错误；已在非受限环境复验通过，因此该错误不作为项目缺陷记录。

## 阻断问题

### P0-1: 长期认证 Token 仍保存到浏览器持久化存储

**证据：**

- `frontend/src/hooks/useAuthStore.ts:2` 引入 Zustand `persist`。
- `frontend/src/hooks/useAuthStore.ts:28-33` 将 `token` 写入 `yunhe-auth` 持久化 state。
- `frontend/src/utils/api.ts:29-37`、`frontend/src/features/news/api.ts:82-89` 从该 state 读取 token 并发送 `Authorization: Bearer`。
- `frontend/src/pages/Login.tsx:35` 将登录响应中的 token 交给该 store。

**影响：** 违反 `AGENTS.md` 的 Token 存储红线；XSS、恶意浏览器扩展或共用设备可读取长期登录凭据。Cookie 认证改造被旧 Bearer 主路径绕过。

**修复要求：** 浏览器登录响应不得暴露 token；从 `useAuthStore`、`utils/api.ts`、`features/news/api.ts` 和 `useSessionStore.ts` 清除 Bearer 流程；所有浏览器 API 统一走 `features/auth/client.ts` 的 cookie + CSRF 流程。增加测试确认 localStorage/sessionStorage 与 `yunhe-auth` 均不含 token。

### P0-2: CSRF Cookie 直接等于认证 Token

**证据：** `api/v1/auth.py:35-46` 中 `auth_token` 与可由 JavaScript 读取的 `csrf_token` 均使用 `value=token`。

**影响：** JavaScript 可借由 CSRF Cookie 直接读出 HttpOnly 认证 Token，HttpOnly 保护失效。

**修复要求：** 为 CSRF 单独生成随机值（例如 `secrets.token_urlsafe(32)`）；认证 Token 只能出现在 HttpOnly Cookie。保留双提交校验，并新增测试断言两个 Cookie 值不同。

### P1-1: 已删除的打卡和实际费用功能仍在实现与 UI 中

**证据：**

- `domain/travel/itinerary/repository.py:163` 仍有 `check_in_activity`。
- `domain/travel/itinerary/repository.py:253` 仍有 `update_actual_cost`。
- `domain/travel/itinerary/schema.py:139-173` 仍公开 `actual_cost`、`checked_in`。
- `frontend/src/features/travel/api.ts:36-38` 仍定义这两个字段。
- `frontend/src/components/itinerary/ActivityCard.tsx:36` 等多个组件仍展示/处理 `checked_in`。
- `infrastructure/persistence/database.py:101-109`、`:1020-1022` 仍维护对应列。

**影响：** 直接违反已确认业务红线；下一位开发者仍能调用或恢复这些功能。

**修复要求：** 删除相关路由、DTO、领域方法、前端类型与展示；为 SQLite 历史列制定迁移策略；扩展删除回归测试，验证公开 API、前端契约与领域符号均不存在。

### P1-2: 生产环境管理员配置不具备 fail-fast 行为

**证据：** `api/server.py:141-153` 在 `YUNHE_ADMIN_USERNAME` 缺失或找不到用户时仅记录 warning，仍继续启动并让 `admin_user_id=None`。

**影响：** 生产环境可没有唯一管理员，新闻来源审核不可用，违背来源治理要求。

**修复要求：** 增加明确的运行环境配置；生产环境中管理员未配置或无法解析时必须终止应用启动。补充生产失败和正常解析的自动化测试。

### P1-3: Python 质量门禁无法在当前开发环境执行

**证据：** `python` 命令不存在；`D:\python\AI_RAG\.venv\Scripts\python.exe` 启动时报其基础解释器 `C:\Users\29105\AppData\Local\Programs\Python\Python311\python.exe` 不存在。

**影响：** Ruff、mypy、Bandit、pip-audit、pytest 和覆盖率门槛均未得到本地复验，新增后端实现不能验收。

**修复要求：** 安装可用 Python 3.11+，在本项目创建新的虚拟环境，执行 `pip install -r requirements.lock` 后完整运行 Python 门禁。

## 非阻断但必须处理

### P2-1: CI 的 mypy 不阻断失败

**证据：** `.github/workflows/ci.yml:18-19` 为 mypy 配置 `continue-on-error: true`，并保留待处理 TODO。

**影响：** 与“类型检查是 CI 质量门禁”的正式规范不一致；类型错误可进入主分支。

**修复要求：** 在清理现有 mypy 错误后移除 `continue-on-error`，并删除 TODO；在此之前，该检查只能视为信息性扫描，不能视为质量门禁。

### P2-2: React Hook 依赖警告

`frontend/src/pages/Home.tsx:96` 的 `useEffect` 缺少 `initSession` 与 `sessionId` 依赖。修复或将函数稳定化，确保 lint 零警告。

### P2-3: 前端主包超过构建告警阈值

非受限生产构建成功，但 `index-*.js` 为 614.88 kB（gzip 187.18 kB），Vite 报告超过 500 kB。应为地图、复杂行程组件或管理页采用路由级动态加载，或在变更说明中明确接受该预算例外。

### P2-4: 工作区仍有未提交变更

本次验收包含未提交的 `news.yaml`、`Home.tsx`、`Login.tsx`、`utils/api.ts` 修改和 `docs/DEVELOPMENT_SPECIFICATION.md` 删除。完成修复后应逐项审查、测试并提交；不能将未审计工作区当作正式发布版本。

## 下一位 AI 的复验顺序

1. 先完成 P0-1 与 P0-2，补全真实浏览器 Cookie/CSRF 集成测试。
2. 删除 P1-1 的所有业务遗留，补充删除回归测试。
3. 实现 P1-2 的生产 fail-fast 测试和行为。
4. 修复 Python 环境，并将 mypy 改为阻断式检查。
5. 在干净环境完整运行：

```powershell
pip install -r requirements.lock
python -m ruff check .
python -m mypy api application domain infrastructure
python -m bandit -r api application domain infrastructure -lll
python -m pytest --cov=api --cov=application --cov=domain --cov=infrastructure --cov-fail-under=70
pip-audit -r requirements.lock
npm --prefix frontend ci
npm --prefix frontend run lint
npm --prefix frontend run check
npm --prefix frontend run test
npm --prefix frontend run build
```

只有这些命令均为成功状态，并且 P0/P1 删除回归测试通过，才能重新申请最终验收。
