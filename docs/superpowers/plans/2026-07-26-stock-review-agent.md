# 股市复盘 Agent Implementation Plan v2.1

> **For agentic workers:** 本文档面向 AI 开发者，配合 `superpowers:subagent-driven-development` 使用。每个 Task 严格遵循四步骤："先写失败测试 → 写最小实现 → 运行测试验证 → **提交一次 commit**"。Task 之间有明确依赖关系，必须按序执行。

**修订记录：**
- v2.1（2026-07-28）：按二审意见修复——模型/端口迁至 `domain/stock/`（斩断 3 处跨层违规）、删除全部 baseline 表述并对齐 AGENTS.md v3.1、补回 8 张表完整 DDL / 任务注册表 / 历史回填 / 观察池入出池逻辑、读侧改为只读 SQLite 缓存（`sqlite_data_source`）、修正全部无法运行的示例代码（`init_db(tmp_db)` 位置参数、`downgrade()`、`Migration(description=...)`、`Query(pattern=)`）、调度窗口防漏补抓、修复全部相对链接；**新增提交纪律：每个 Task 完成后独立 commit**。
- v2.0（2026-07-28）：重写——新增"与现有架构的接缝"章节、LLM 集成设计、调度器时区/反爬设计、TDD 步骤结构。

**业务基线：** [`infrastructure/skills/builtin/stock-review/SKILL.md`](../../../infrastructure/skills/builtin/stock-review/SKILL.md)（启发式方法论，46KB）

**目标：** 为云合新增"股市复盘"专业 Agent，每日通过 akshare 抓取 A 股市场数据并按情绪周期方法论产出"观点+依据+概率性表达"的复盘文；提供 ECharts 多日趋势曲线（同时供 AI 读取趋势数据）与历史复盘文存档。

---

## 1. Goal

构建一个完整的"数据采集 → 缓存 → 复盘生成 → 前端展示"链路：

1. **数据层**：每日 11:30 / 16:30（北京时间）后台任务用 akshare 抓 A 股数据，缓存至 SQLite（8 张新表，迁移 v021）
2. **复盘层**：用户触发后，复盘 Service 编排 7 步思维链，**只读 SQLite 缓存**（禁止复盘链路调用实时接口），调用 LLM（系统 prompt 嵌入 SKILL.md）产出 Markdown 复盘文
3. **展示层**：独立 `/stock` 页面用 ECharts 展示多日趋势曲线 + 复盘文列表 + 触发按钮（任务状态轮询）
4. **Agent 层**：stock-review skill 已存在于 `infrastructure/skills/builtin/stock-review/`，`FileSkillProvider` 会自动加载

**复盘文边界（不可违反）：**
- 仅"观点+依据+概率推演"，**不预测具体涨跌**，**不给目标价/买卖点**
- 末尾强制声明"不构成投资建议"
- 数据缺失时如实标注"该维度数据缺失"，**不臆测**
- 庄股/抱团股相关性分析**仅周复盘**：`get_correlation` 工具只在周复盘 Agent 会话注册；HTTP 缓存未就绪返回 409

---

## 2. Architecture

### 2.1 整体数据流

```
akshare  ──>  infrastructure/stock/*_fetcher.py  ──>  SQLite (8 张新表, 迁移 v021)
  (写路径，仅调度器/admin 触发)                            │
                                                          │ 只读
                                                          ▼
              domain/stock/ports.py: StockDataSource <—— infrastructure/stock/sqlite_data_source.py
                             │ 端口注入（组合根装配）
                             ▼
              application/stock/review_service.py
                             │
                             │ 7 步思维链编排 + 注入 SKILL.md 到 system prompt
                             ▼
                        LLM (domain/shared/llm/ports.py: LLMPort，复用既有端口)
                             │
                             ▼
                      review_reports (Markdown 存档, upsert by user_id+trade_date)
                             │
                             ▼
                  /api/v1/stock/* (api/v1/stock.py，与既有平铺约定一致)
                             │
                             ▼
              frontend/src/features/stock/* (React + ECharts + 轮询)
```

**关键架构决策：**
- **模型与端口在 domain**：`domain/stock/models.py`（DTO）、`domain/stock/ports.py`（`StockDataSource`）、`domain/stock/heuristics.py`（纯函数启发式）。与既有 `domain/user/session/ports.py`、`domain/travel/itinerary/ports.py` 同构（AGENTS.md §8.1）。
- **读/写分离**：写路径 = fetcher（调度器/admin 触发）；读路径 = `sqlite_data_source.py`（实现 `StockDataSource`，全部参数化 SELECT）。**复盘链路永不触达 akshare**。
- **LLM 端口复用**：`domain/shared/llm/ports.py: LLMPort`（已存在，含 FallbackLLM 降级链），不新建端口。
- akshare 只能出现在 `infrastructure/stock/`；`domain/`、`application/` 不得 import akshare / infrastructure（§8.3，检查器零容忍）。

### 2.2 与现有架构的接缝（AI 开发必读）

**以下行号引用已逐一核实（2026-07-28）。新代码怎么"接"到现有系统里，照此办理。**

#### 接缝 1：组合根（`app.py:build_orchestrator()`）

**现有模式**（news 服务的接入方式，[`app.py:322`](../../../app.py#L322)）：

```python
# app.py 第 322 行
news_analysis_service = NewsAnalysisService(
    sources=SourceService(), evidence_provider=EmptyEvidenceProvider()
)
# 然后塞进 AppContainer（第 365 行）
return AppContainer(..., news_analysis_service=news_analysis_service)
```

**stock 服务照着接入**（在 `build_orchestrator()` 内，news 服务构造之后）：

```python
# ===== 股市复盘服务 =====
from application.stock.pipeline import StockPipelineService, set_default_pipeline
from application.stock.report_service import ReportService
from application.stock.review_service import StockReviewService
from application.stock.review_tasks import ReviewTaskRegistry
from application.stock.watchlist_service import WatchlistService
from infrastructure.stock.akshare_client import AkshareClient
from infrastructure.stock.cache_repository import StockCacheRepository
from infrastructure.stock.correlation_analyzer import CorrelationAnalyzer
from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

stock_cache_repo = StockCacheRepository(conn)
stock_akshare_client = AkshareClient()                    # 仅写路径（fetcher/pipeline）使用
stock_correlation = CorrelationAnalyzer()                 # 进程内存缓存，周五任务填充
stock_data_source = SqliteStockDataSource(                # 读路径：只读 SQLite
    conn, correlation_analyzer=stock_correlation
)
stock_pipeline = StockPipelineService(                    # 抓取管线门面（调度器/admin 用）
    client=stock_akshare_client, repo=stock_cache_repo,
    correlation_analyzer=stock_correlation,
)
set_default_pipeline(stock_pipeline)                      # 供 scheduler 惰性取用（见接缝 4）
stock_review_service = StockReviewService(
    data_source=stock_data_source,
    llm=llm,                                              # 复用组合根已构造的 LLMPort
    watchlist_service=WatchlistService(repo=stock_cache_repo),
    report_service=ReportService(repo=stock_cache_repo),
    skill_md_path=settings.skills_dir / "builtin" / "stock-review" / "SKILL.md",
)
stock_review_tasks = ReviewTaskRegistry()                 # 进程内存任务注册表
```

> **禁止**：`stock_data_source = AkshareClient()`——那会让复盘链路直连实时接口，违反"只读缓存"约束。`AkshareClient` 只能注入 fetcher/pipeline。

**AppContainer 加字段**（现有 `news_analysis_service` 字段在 [`app.py:75`](../../../app.py#L75)）：

```python
@dataclass
class AppContainer:
    ...
    stock_review_service: StockReviewService | None = None
    stock_review_tasks: ReviewTaskRegistry | None = None
    stock_pipeline: StockPipelineService | None = None
```

> 组合根改动属 AGENTS.md §8.7 声明事项：对应 commit 必须在 message body 显式声明（见 §3 提交纪律）。

#### 接缝 2：路由注册（`api/v1/__init__.py`）

**现有模式**（每域单文件平铺，[`api/v1/__init__.py:43-44`](../../../api/v1/__init__.py#L43)）：

```python
router.include_router(news_router, prefix="/news")
router.include_router(admin_news_router, prefix="/admin/news")
```

**stock 路由照着加**（遵循同一平铺约定，**单文件** `api/v1/stock.py`，不建子包）：

```python
from api.v1.stock import router as stock_router
router.include_router(stock_router, prefix="/stock")
```

> 现有 `api/v1/` 全部是每域单文件（`news.py`、`travel.py`…）。13 个端点 + DTO 收在单文件，与 `news.py` 规模相当，不偏离约定。

#### 接缝 3：app.state 绑定（`api/server.py:create_api()`）

**现有模式**（[`api/server.py:151`](../../../api/server.py#L151)）：

```python
app.state.news_analysis_service = container.news_analysis_service
```

**stock 照着加**：

```python
app.state.stock_review_service = container.stock_review_service
app.state.stock_review_tasks = container.stock_review_tasks
app.state.stock_pipeline = container.stock_pipeline
```

路由内通过 `request.app.state.stock_review_service` 取用（与 news 完全一致）。

#### 接缝 4：后台任务（`api/server.py:lifespan`）

**现有模式**（[`api/server.py:109-112`](../../../api/server.py#L109)，现有 4 个后台 task）：

```python
_BACKGROUND_TASK = asyncio.create_task(_periodic_refresh_pool())
_MEMORY_TASK = asyncio.create_task(_periodic_memory_maintenance())
_HOTSPOT_REFRESH_TASK = asyncio.create_task(_periodic_hotspot_refresh())
_HOTSPOT_CLEANUP_TASK = asyncio.create_task(_periodic_hotspot_cleanup())
```

**stock 调度器照着挂**（lifespan 内现有 4 个 task 之后；`yield` 后同步追加 cancel）：

```python
_STOCK_MORNING_TASK = asyncio.create_task(run_stock_morning_fetch())
_STOCK_CLOSE_TASK = asyncio.create_task(run_stock_close_fetch())
```

**依赖获取方式（关键约束）**：现有 `run_hotspot_refresh`（[`application/scheduler.py:107`](../../../application/scheduler.py#L107)）的做法是**函数内惰性 import application 层服务**：

```python
from application.news.hotspot_service import get_default_service
service = get_default_service()
```

stock 照此模式：调度函数体内 `from application.stock.pipeline import get_default_pipeline`（由接缝 1 的 `set_default_pipeline()` 在组合根装配时注册）。**禁止 `from app import ...`**——application 反向导入组合根会造成循环依赖。

#### 接缝 5：迁移注册（`infrastructure/persistence/migrations/registry.py`）

**现有约束**（[`registry.py:19-29`](../../../infrastructure/persistence/migrations/registry.py#L19)）：`_validate_registry()` 校验版本号 1..N 连续；追加 v21 后恰为 1..21，自检自动通过，无需改动校验器。

**修改方式**（与现有 `+` 拼接风格一致，仅追加一项）：

```python
from infrastructure.persistence.migrations.v021_025 import MIGRATIONS as _v021_025

MIGRATIONS: tuple[Migration, ...] = (
    _v001_005 + _v006_010 + _v011_015 + _v016_020 + _v021_025
)
```

**Migration 类型字段**（[`types.py:20-23`](../../../infrastructure/persistence/migrations/types.py#L20)，已核实）：`Migration(version, description, upgrade, downgrade)`——是 `upgrade/downgrade` 且**必须带 `description`**（runner 写入 `schema_migrations`）。不要写成 `up=/down=`。

#### 接缝 6：Skill 加载（自动，无需改动）

`FileSkillProvider`（[`infrastructure/skills/provider.py:31`](../../../infrastructure/skills/provider.py#L31)）自动扫描 `skills/builtin/*/SKILL.md`。stock-review skill 已存在，**无需额外注册**。但需确认 `agents/openai.yaml` 的 15 个工具名与后端端口方法一致（Task 8）。

#### 接缝 7：前端菜单（`frontend/src/components/NavSidebar.tsx`）

**现有模式**（新闻审核菜单）：

```tsx
<button onClick={() => navigate('/admin/news')} className={...}>
  <ShieldCheck size={18} className="flex-shrink-0" />
  新闻来源审核
</button>
```

**stock 菜单照着加**（`TrendingUp` 从 `lucide-react` 导入）：

```tsx
const isStock = location.pathname.startsWith('/stock')
<button onClick={() => navigate('/stock')} className={...}>
  <TrendingUp size={18} className="flex-shrink-0" />
  股市复盘
</button>
```

#### 接缝 8：风格参考

- **application service**：参考 [`NewsAnalysisService`](../../../application/news/analysis_service.py)——构造注入端口、docstring、捕获具体异常并 `raise ... from e`、不向客户端暴露堆栈。
- **scheduler**：参考 [`run_hotspot_refresh`](../../../application/scheduler.py#L97)——`asyncio.sleep` 首次延迟 + `while True` + `try/except Exception` 包循环体（`exc_info=True`）+ 固定间隔 sleep。**项目无 APScheduler**，不得引入。
- **API 测试认证**：参考 [`tests/integration/test_token_security.py`](../../../tests/integration/test_token_security.py)——经注册/登录端点拿真实 token；GET 用 `cookies={"auth_token": token}`，POST 用 Bearer 或 cookies + `X-CSRF-Token` header。
- **迁移测试**：参考 [`tests/integration/test_news_migration_20.py`](../../../tests/integration/test_news_migration_20.py)——`tmp_db` fixture（`monkeypatch` 劫持 `config.settings.database_path` + `reset_connection()`）。

---

## 3. Global Constraints

严格遵循 [`AGENTS.md`](../../../AGENTS.md) **v3.1**，本次新增重点约束：

1. **测试先行**：每个 Task 必须先写失败测试，再写最小实现（§6）
2. **端口归属**：端口与 DTO 定义在 `domain/stock/`；`application` 不得 import `infrastructure`；`infrastructure` 只 import `domain`（§8.1/§8.3）
3. **迁移版本**：从 21 起，新建 `v021_025.py`，**不得修改历史迁移**（§4/§8.6）
4. **SQL 参数化**：动态表名只能来自硬编码白名单（§4）
5. **DTO 规范**：Pydantic v2 + `ConfigDict(extra="forbid")`，公共类有 docstring（§5）
6. **对象级未授权**：跨用户访问统一 404，不返回 403（§4）
7. **认证**：身份/管理员/所有权只能从服务端认证上下文取得（§4）
8. **敏感数据**：密码/Token/会话凭据/用户隐私不进日志或异常详情；行情为公开数据可入日志，但不得关联账户敏感信息（§4）
9. **前端规范**：TypeScript strict，禁用 `any` / 未使用导入 / ESLint 禁用注释（§5）
10. **前端 API**：仅放入 `frontend/src/features/stock/api.ts`，走 `features/auth/client.ts`（§8.6）
11. **架构守卫**：`python scripts/check_architecture.py` **零容忍，无 baseline/豁免参数**；新增端口必须同步 fake 单测 + 真实实现集成测试（§8.5/§8.7）
12. **不预测**：复盘文不给"明天必涨/必跌"结论，所有判定用概率性表达（SKILL.md 红线）
13. **庄股/抱团仅周复盘**：`get_correlation` 仅在周复盘 Agent 会话注册；HTTP 缓存未就绪 → 409 `CORRELATION_NOT_READY`
14. **只读缓存**：复盘链路只读 SQLite 缓存，禁止调用实时接口
15. **异常具体化**：禁止裸 `except` 与 `except Exception` 一把梭；akshare 无统一异常基类，按 requests/解析层具体异常捕获并保留异常链（§5）

### 提交纪律（每个 Task 必须执行）

16. **每 Task 一次独立 commit**：完成"失败测试 → 最小实现 → 测试验证"三步且门禁通过后，立即提交；**不得**把多个 Task 混入一个 commit，不得携带红测试/未运行门禁的工作区进入下一 Task。
17. **提交前门禁**：至少运行该 Task"步骤 3"列出的命令（目标 pytest + `ruff check` + `mypy` + `python scripts/check_architecture.py`，前端 Task 跑 lint/check/test），全绿方可提交。
18. **commit message 格式**：`feat(stock): task<N> <简述>` / `test(stock): ...` / `chore(stock): ...`；body 列出变更要点与测试结果摘要。
19. **声明事项独立成段**：涉及组合根（`app.py`）、迁移（`migrations/`、`registry.py`）、架构检查器、AGENTS.md 的改动（Task 1/5/6），按 AGENTS.md §8.7 在 commit body 显式声明"本提交含组合根/迁移改动"。
20. **同步勾选**：提交时把本文档验收清单中该 Task 对应项勾选（`- [x]`）并包含在同一 commit，保持计划与实际进度一致。

---

## 4. LLM 集成设计（核心章节）

### 4.1 端口与注入

复用既有 `domain/shared/llm/ports.py: LLMPort`（含 FallbackLLM 降级链），不新建端口。`StockReviewService` 构造函数（**全部依赖显式注入、全部带类型标注**）：

```python
class StockReviewService:
    """股票周期复盘服务：编排 7 步思维链，调用 LLM 产复盘文。"""

    def __init__(
        self,
        data_source: StockDataSource,        # domain/stock/ports.py
        llm: LLMPort,                        # domain/shared/llm/ports.py（复用）
        watchlist_service: WatchlistService, # 观察池入/出池判定
        report_service: ReportService,       # 存档/查询/所有权
        skill_md_path: Path,
    ) -> None: ...
```

### 4.2 Prompt 工程（SKILL.md 注入策略）

**问题**：SKILL.md 46KB。中文按 UTF-8 约 1.5 万字符，**约 1.5–3 万 tokens**（中文单字通常 1–2 token，"46KB ≈ 12000 tokens"的估计偏乐观，按上限做预算）。叠加多日数据后存在超 context 风险。

**策略**：分层注入 + 数据裁剪 + 超限降级。

```python
async def generate_review(self, user_id: str, trade_date: str) -> ReviewReport:
    # 1. 系统提示：SKILL.md 全文；若组合后超模型 context 预算，
    #    降级为注入 SKILL.md 核心章节（方法论 + 7 步思维链 + 红线），
    #    并在复盘文"方法论说明"章节如实标注"本次注入为精简版"。
    system_prompt = self._load_skill_prompt()

    # 2. 用户提示：结构化数据（裁剪规则见下），情绪趋势格式化为 Markdown 表格
    user_prompt = self._build_user_prompt(...)

    # 3. 调用 LLM
    markdown = await self.llm.generate(
        system=system_prompt, user=user_prompt,
        temperature=0.3,    # 低温度保证结构稳定
        max_tokens=4000,    # 复盘文约 2000-3000 字
    )
```

**裁剪规则**：
- 情绪趋势：最近 10 个交易日
- 板块数据：top20 板块
- 观察池：仅 active 状态
- 个股日线：每只股票仅近 10 日 OHLCV

### 4.3 章节校验与降级（含 status 生命周期）

**校验规则**：LLM 输出必须含 9 个章节 + "不构成投资建议"声明。

```python
REQUIRED_SECTIONS = [
    "## 一、周期定位", "## 二、大盘与量能", "## 三、情绪指标详解",
    "## 四、板块轮动", "## 五、观察池复盘", "## 六、新信号扫描",
    "## 七、明日条件预判", "## 八、风险提示", "## 九、方法论说明",
    "不构成投资建议",
]

def _validate_markdown(self, markdown: str) -> None:
    """校验复盘文章节完整性。缺失则抛 ReviewValidationError。"""
    missing = [s for s in REQUIRED_SECTIONS if s not in markdown]
    if missing:
        raise ReviewValidationError(f"复盘文缺失章节: {missing}")
```

**三级降级**（所有结局都存档，`review_reports.status` 列区分，生命周期闭环）：

| 级别 | 触发条件 | 行为 | status |
|------|----------|------|--------|
| L1 正常 | 输出含 9 章节 + 声明 | 存档，任务置 done | `final` |
| L2 重试 | 输出缺章节 | user_prompt 追加"上次缺失 X 章节，请补全"，**重试恰好 1 次** | — |
| L3 降级 | 重试仍缺 | **存档但标记降级**：内容原样保留 + 卷首插入缺失说明；任务置 done | `degraded` |
| L0 无数据 | 情绪趋势与观察池均为空 | 不调 LLM，存档占位文"该交易日无缓存数据" | `no_data` |

**不静默修复**：L3 不伪造章节内容；降级/占位报告在列表与详情中如实展示 status。**允许重生成**：用户对同一交易日重新触发复盘（upsert 覆盖，status 刷新）。

### 4.4 Context 裁剪细节

多日趋势格式化为 Markdown 表格（LLM 看趋势比看 JSON 更容易）：

```python
def _format_emotion_trend(self, trend: list[EmotionIndicators]) -> str:
    """格式化多日情绪趋势为 Markdown 表格，供 LLM 看趋势。"""
    if not trend:
        return "情绪指标数据缺失"
    rows = []
    for e in reversed(trend):  # 最新在前
        rows.append(
            f"| {e.trade_date} | {e.limit_up_count} | {e.valid_limit_up_count} | "
            f"{e.broken_limit_ratio:.1%} | {e.max_consecutive_boards} | "
            f"{e.yesterday_limit_up_today_premium or 'N/A'} |"
        )
    return "| 日期 | 涨停 | 有效涨停 | 炸板率 | 最高连板 | 昨涨停溢价 |\n|---|---|---|---|---|---|\n" + "\n".join(rows)
```

### 4.5 失败处理

| 失败类型 | 处理 |
|----------|------|
| akshare 抓取失败 | 缓存缺数据 → 复盘文标注"该维度数据缺失"（读侧返回空，不抛异常） |
| LLM 调用超时 | LLMPort 内部 FallbackLLM 已含降级；仍失败 → 任务置 `failed`（`error_code=LLM_UNAVAILABLE`） |
| LLM 输出缺章节 | L2 重试 1 次 → L3 降级存档（见 4.3） |
| SQLite 写入失败 | 任务置 `failed`，记 error 日志（不暴露堆栈给客户端） |
| 数据完全为空 | 存档 `no_data` 占位报告，不调用 LLM |

---

## 5. 调度器设计

### 5.1 时区与节假日

**时区**：A 股按北京时间（UTC+8），调度器用 `datetime.now(ZoneInfo("Asia/Shanghai"))`。

**节假日**：启动时调用 `akshare.tool_trade_date_hist_sina()` 缓存全年交易日历到进程内存（不持久化，重启重新加载，由 `StockPipelineService` 持有）；运行时查表：

```python
def _is_trading_day(now: datetime, trade_dates: frozenset[str]) -> bool:
    """判断北京时间当日是否为交易日（查交易日历缓存）。"""
    beijing = now.astimezone(ZoneInfo("Asia/Shanghai"))
    return beijing.strftime("%Y%m%d") in trade_dates
```

### 5.2 调度计划

| 北京时间 | 任务 | 频率 |
|----------|------|------|
| 11:30 | 抓上午盘后数据 | 交易日 |
| 16:30 | 抓收盘数据 + 聚合情绪 + 扫描新信号 + 观察池入池 | 交易日 |
| 周五 16:30 | **同一任务内串行追加**：庄股/抱团股相关性分析 | 周频 |

周五不设独立并发 job——相关性分析依赖当日数据已落库，在 16:30 管线完成后**同一任务内串行追加**，消除时序竞争。

### 5.3 触发窗口与补抓（防漏设计）

朴素写法 `now.hour == 16 and now.minute >= 30` + 30 分钟 sleep **会漏**：两次检查落在 16:29 → 17:00 时整日错过；进程停机同样漏数据。**必须双保险**：

```python
async def run_stock_close_fetch() -> None:
    """后台任务：交易日 16:30（北京时间）后抓收盘数据，含漏抓补偿。

    防漏机制：
    - 进程内存记录 last_done_date，同一交易日只执行一次（节流）；
    - 每次唤醒做 due 判定：交易日、已过 16:30、当日未完成 → 立即执行
      （覆盖窗口抖动与进程重启场景）；
    - 依赖经 get_default_pipeline() 惰性取用（与 run_hotspot_refresh 同模式），
      禁止 from app import。
    """
    await asyncio.sleep(300)  # 首次延迟 5 分钟
    last_done_date: str | None = None
    while True:
        try:
            from application.stock.pipeline import get_default_pipeline

            pipeline = get_default_pipeline()
            now = datetime.now(ZoneInfo("Asia/Shanghai"))
            today = now.strftime("%Y%m%d")
            due = (
                _is_trading_day(now, pipeline.trade_dates)
                and (now.hour, now.minute) >= (16, 30)
                and last_done_date != today
            )
            if due:
                count = await pipeline.fetch_and_store_close(today)
                if now.weekday() == 4:  # 周五：同一任务内串行追加相关性分析
                    await pipeline.run_weekly_correlation(today)
                last_done_date = today
                logger.info("Stock close fetch done: date=%s rows=%d", today, count)
        except Exception:
            logger.warning("Stock close fetch failed", exc_info=True)
        await asyncio.sleep(600)  # 10 分钟粒度轮询，窗口内必有多次机会
```

> 写库依赖复合主键 `INSERT OR REPLACE`，重复执行幂等；`last_done_date` 只是节流，进程重启后由"due 判定 + 幂等写"兜底（重启当天最多多跑一次，无害）。跨天历史缺口由 `admin/refresh` 回填（见 Task 5）。

### 5.4 并发与反爬

- 单次调度内**串行**调用各 fetcher（不并发），fetcher 之间 sleep 1–2 秒
- 单 fetcher 失败重试最多 2 次、间隔 5 秒；失败仅 log warning，不中断当日流程
- 连续 3 日失败 → log error（项目无告警通道）

### 5.5 与现有 lifespan 的集成

按接缝 4 挂接；`yield` 后追加两个 task 的 `cancel()`（与现有 4 个 task 的清理方式一致）。

---

## 6. 业务边界

### 6.1 与新闻深度研判的区分

| 维度 | 新闻深度研判 | 股市复盘 |
|------|-------------|----------|
| 数据源 | 新闻热点（后端抓取缓存） | akshare A 股数据（SQLite 缓存） |
| 方法论 | 事实核查（来源可信度） | 情绪周期（趋势曲线） |
| 输出 | 证据卡片 + 未核实线索 | Markdown 复盘文 |
| 会话模式 | `news_analysis_locked`（锁定） | **不锁定**（按需触发） |
| 触发方式 | 用户点击热点"深度研判" | 用户在 /stock 页面点击"生成复盘" |

**为什么 stock 不锁定会话**：复盘是单次生成（7 步思维链一次性产出），不需要多轮追问；存档后独立查看。

### 6.2 菜单层级

`NavSidebar.tsx` 加独立菜单项"股市复盘"（与"新闻来源审核"同级），路由 `/stock`。不复用"深度研判"入口。

### 6.3 复盘文存档与查询

- **存档**：`review_reports` 表 `UNIQUE(user_id, trade_date)`，重新生成**覆盖**旧存档并刷新 `created_at`；`status` 区分 final/degraded/no_data
- **查询**：列表**仅本人**（owner 过滤）；详情跨用户 → 404
- **对话内引用**：用户在对话问"今天的复盘"时云合调取最新报告——**后续优化，本期不做**

---

## 7. Task 列表

每个 Task 严格遵循四步骤："先写失败测试 → 写最小实现 → 运行测试验证 → **提交 commit**（§3 提交纪律）"。

依赖关系：Task 1 → Task 2 → Task 3 → Task 4 → Task 5 → Task 6 → Task 7 → Task 8 → Task 9

---

### Task 1: 迁移 v021 — 8 张股票数据表

**目标**：新建 `v021_025.py` 版本组，创建 8 张表 + 索引，更新 `registry.py`。

**依赖**：无

**Files:**
- Create: `infrastructure/persistence/migrations/v021_025.py`
- Modify: `infrastructure/persistence/migrations/registry.py`（仅追加）
- Create: `tests/integration/stock/__init__.py`
- Create: `tests/integration/stock/conftest.py`（`tmp_db` fixture，复用既有模式）
- Create: `tests/integration/stock/test_migration_v021.py`

#### 步骤 1：先写失败测试

`tests/integration/stock/conftest.py`（模式照搬 [`test_news_migration_20.py:28-36`](../../../tests/integration/test_news_migration_20.py#L28)）：

```python
"""stock 集成测试公共 fixture。"""
from __future__ import annotations

import os

import pytest

from infrastructure.persistence.database import reset_connection


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """隔离 SQLite 库：劫持 database_path 并重置连接缓存。"""
    db_path = tmp_path / "test_stock.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    yield db_path
    reset_connection()
    if db_path.exists():
        os.unlink(db_path)
```

`tests/integration/stock/test_migration_v021.py`：

```python
"""Task 1 失败测试：迁移 v021 必须创建 8 张表 + 索引。

运行前 v021_025.py 不存在，本测试应全部失败。
"""
from __future__ import annotations

from infrastructure.persistence.database import get_connection, init_db
from infrastructure.persistence.migrations.runner import downgrade

EXPECTED_TABLES = [
    "market_index_daily", "stock_daily", "limit_stocks_daily",
    "board_ladder_daily", "sector_daily", "emotion_daily",
    "watchlist_stocks", "review_reports",
]


def _table_exists(conn, table: str) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,),
    )
    return cur.fetchone() is not None


def test_migration_v021_creates_all_tables(tmp_db):
    """迁移到 v021 后，8 张表必须存在。"""
    init_db(tmp_db)  # 位置参数；签名为 init_db(db_path=None)
    conn = get_connection(tmp_db)
    for table in EXPECTED_TABLES:
        assert _table_exists(conn, table), f"表 {table} 未创建"


def test_review_reports_unique_user_date(tmp_db):
    """review_reports 必须有 UNIQUE(user_id, trade_date)（upsert 语义）。"""
    init_db(tmp_db)
    conn = get_connection(tmp_db)
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='review_reports'"
    ).fetchone()
    assert "UNIQUE" in row[0].upper() and "user_id" in row[0]


def test_migration_v021_downgrade_drops_tables(tmp_db):
    """downgrade(20) 后 8 张表必须消失，再 init_db 可重建。"""
    init_db(tmp_db)
    downgrade(target_version=20, conn=get_connection(tmp_db))
    conn = get_connection(tmp_db)
    for table in EXPECTED_TABLES:
        assert not _table_exists(conn, table), f"表 {table} 未被删除"
    init_db(tmp_db)  # 重建验证幂等
    for table in EXPECTED_TABLES:
        assert _table_exists(conn, table)


def test_registry_validates_1_to_21():
    """registry 必须包含 1..21 连续版本。"""
    from infrastructure.persistence.migrations.registry import MIGRATIONS
    versions = [m.version for m in MIGRATIONS]
    assert versions == list(range(1, 22)), f"版本不连续: {versions}"
```

**运行测试**（应全部失败，因为 v021_025.py 不存在）：

```powershell
python -m pytest tests/integration/stock/test_migration_v021.py -v
```

#### 步骤 2：写最小实现

`infrastructure/persistence/migrations/v021_025.py`（**8 张表完整 DDL，不转引**）：

```python
"""迁移 v021：股票复盘数据表（8 张）。

设计要点：
- 所有表 IF NOT EXISTS，复合主键防止重复抓取
- review_reports 含 status 列（final/degraded/no_data）与 UNIQUE(user_id, trade_date)
- 时间用 ISO 8601 TEXT；索引按 trade_date DESC 优化近期查询
"""
from __future__ import annotations

from infrastructure.persistence.migrations.types import Migration

_UP_SQL = """
CREATE TABLE IF NOT EXISTS market_index_daily (
    trade_date TEXT NOT NULL,
    index_code TEXT NOT NULL,            -- sh000001 / sz399001 / sz399006
    open REAL, close REAL, high REAL, low REAL,
    volume REAL, pct_chg REAL,
    PRIMARY KEY (trade_date, index_code)
);
CREATE INDEX IF NOT EXISTS idx_market_index_date
    ON market_index_daily(trade_date DESC);

CREATE TABLE IF NOT EXISTS stock_daily (
    trade_date TEXT NOT NULL,
    stock_code TEXT NOT NULL,
    stock_name TEXT,
    open REAL, close REAL, high REAL, low REAL,
    volume REAL, pct_chg REAL, turnover REAL,
    PRIMARY KEY (trade_date, stock_code)
);
CREATE INDEX IF NOT EXISTS idx_stock_daily_code_date
    ON stock_daily(stock_code, trade_date DESC);

CREATE TABLE IF NOT EXISTS limit_stocks_daily (
    trade_date TEXT NOT NULL,
    stock_code TEXT NOT NULL,
    stock_name TEXT,
    limit_type TEXT NOT NULL,            -- up / down / broken
    consecutive_boards INTEGER DEFAULT 1,
    first_limit_time TEXT,               -- HH:MM:SS
    last_limit_time TEXT,
    open_count INTEGER DEFAULT 0,        -- 炸板次数
    is_valid_limit_up INTEGER,           -- 0/1: 一次性封死判定
    PRIMARY KEY (trade_date, stock_code, limit_type)
);
CREATE INDEX IF NOT EXISTS idx_limit_stocks_date_type
    ON limit_stocks_daily(trade_date DESC, limit_type);

CREATE TABLE IF NOT EXISTS board_ladder_daily (
    trade_date TEXT NOT NULL,
    board_level INTEGER NOT NULL,        -- 几连板
    stock_count INTEGER,
    stock_codes TEXT,                    -- 逗号分隔
    PRIMARY KEY (trade_date, board_level)
);

CREATE TABLE IF NOT EXISTS sector_daily (
    trade_date TEXT NOT NULL,
    sector_code TEXT NOT NULL,
    sector_name TEXT,
    pct_chg REAL, volume REAL,
    leader_stock TEXT,
    large_cap_boards INTEGER DEFAULT 0,  -- 板块内 ≥600亿大市值涨停数
    PRIMARY KEY (trade_date, sector_code)
);
CREATE INDEX IF NOT EXISTS idx_sector_daily_date
    ON sector_daily(trade_date DESC);

CREATE TABLE IF NOT EXISTS emotion_daily (
    trade_date TEXT PRIMARY KEY,
    limit_up_count INTEGER,
    limit_down_count INTEGER,
    valid_limit_up_count INTEGER,
    broken_limit_ratio REAL,
    max_consecutive_boards INTEGER,
    yesterday_limit_up_today_premium REAL,
    total_volume REAL,
    volume_change_pct REAL,
    phase TEXT,                          -- 由复盘服务 LLM 判定后回填
    phase_confidence TEXT,               -- high / medium / low
    phase_reason TEXT
);

CREATE TABLE IF NOT EXISTS watchlist_stocks (
    stock_code TEXT NOT NULL,
    stock_name TEXT,
    entry_date TEXT NOT NULL,
    entry_reason TEXT NOT NULL,          -- resistant / breakout / sector_divergence / sector_resistant_leader
    entry_price REAL,
    entry_index_level REAL,
    sector_code_at_entry TEXT,
    current_price REAL,
    cumulative_pct REAL,
    ma_distance_pct REAL,
    status TEXT DEFAULT 'active',        -- active / weak / removed
    removed_date TEXT,
    removed_reason TEXT,
    validation_status TEXT,              -- verified / failed / pending
    validation_date TEXT,
    updated_at TEXT,
    PRIMARY KEY (stock_code, entry_date)
);
CREATE INDEX IF NOT EXISTS idx_watchlist_status ON watchlist_stocks(status);

CREATE TABLE IF NOT EXISTS review_reports (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'final',  -- final / degraded / no_data
    emotion_phase TEXT,
    title TEXT,
    content TEXT NOT NULL,               -- Markdown 全文
    watchlist_snapshot TEXT,             -- JSON 快照
    market_snapshot_json TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (user_id, trade_date)         -- 重新生成覆盖旧存档
);
CREATE INDEX IF NOT EXISTS idx_review_reports_user_date
    ON review_reports(user_id, trade_date DESC);
"""

_DOWN_SQL = """
DROP TABLE IF EXISTS review_reports;
DROP TABLE IF EXISTS watchlist_stocks;
DROP TABLE IF EXISTS emotion_daily;
DROP TABLE IF EXISTS sector_daily;
DROP TABLE IF EXISTS board_ladder_daily;
DROP TABLE IF EXISTS limit_stocks_daily;
DROP TABLE IF EXISTS stock_daily;
DROP TABLE IF EXISTS market_index_daily;
"""


def _upgrade_v021(conn) -> None:
    """创建 8 张股票数据表。"""
    conn.executescript(_UP_SQL)


def _downgrade_v021(conn) -> None:
    """按依赖倒序删除 8 张表。"""
    conn.executescript(_DOWN_SQL)


MIGRATIONS = (
    Migration(
        version=21,
        description="stock review tables (8)",
        upgrade=_upgrade_v021,
        downgrade=_downgrade_v021,
    ),
)
```

`registry.py` 修改：见接缝 5（仅追加 `_v021_025` 一项）。

#### 步骤 3：运行测试验证

```powershell
python -m pytest tests/integration/stock/test_migration_v021.py -v
python -m pytest tests/unit/test_migration_registry.py -v   # 既有注册表测试不破坏
python scripts/check_architecture.py
```

**验收**：4 个测试全绿；`MIGRATIONS` 长度 21 且连续；架构检查零违规。

#### 步骤 4：提交

```
feat(stock): task1 迁移 v021 — 8 张股票数据表

- 新增 v021_025 版本组（8 表 + 索引 + review_reports UNIQUE/status）
- registry 追加 _v021_025（1..21 连续，自检通过）
- 集成测试 4 项全绿（建表/UNIQUE/downgrade 重建/注册表连续性）

本提交含迁移改动（AGENTS.md §8.7 声明事项）。
```

---

### Task 2: domain 模型/端口/启发式 + akshare 客户端 + 依赖入账

**目标**：在 `domain/stock/` 定义模型、端口与纯函数启发式；infrastructure 薄包装 akshare；akshare 依赖入账。

**依赖**：Task 1

**Files:**
- Create: `domain/stock/__init__.py`
- Create: `domain/stock/models.py`
- Create: `domain/stock/ports.py`
- Create: `domain/stock/heuristics.py`
- Create: `infrastructure/stock/__init__.py`
- Create: `infrastructure/stock/akshare_client.py`
- Modify: `requirements.lock`（akshare 及传递依赖入账，**本 Task 第一步**）
- Create: `tests/unit/stock/__init__.py`
- Create: `tests/unit/stock/test_akshare_client.py`
- Create: `tests/unit/stock/test_heuristics.py`
- Create: `tests/fixtures/__init__.py`
- Create: `tests/fixtures/stock.py`（`FakeStockDataSource` + 样本数据）

**依赖入账**：将 `akshare` 加入依赖并重新生成 `requirements.lock`；`python -m pip_audit -r requirements.lock` 必须通过，否则不得继续。

#### 步骤 1：先写失败测试

`tests/unit/stock/test_heuristics.py`：

```python
"""Task 2 失败测试：启发式纯函数（domain 层，无 I/O）。"""

def test_is_valid_limit_up_one_shot_seal():
    """一次性封死（炸板次数=0 且 首封=末封时间）→ 有效涨停。"""
    from domain.stock.heuristics import is_valid_limit_up
    assert is_valid_limit_up(open_count=0, first_time="09:30:00", last_time="09:30:00") is True


def test_is_valid_limit_up_broken_and_resealed():
    """炸板后回封（首封≠末封）→ 无效涨停。"""
    from domain.stock.heuristics import is_valid_limit_up
    assert is_valid_limit_up(open_count=1, first_time="09:30:00", last_time="14:20:00") is False


def test_is_valid_limit_up_none_time():
    """缺封板时间 → 无法判定一次性封死 → False。"""
    from domain.stock.heuristics import is_valid_limit_up
    assert is_valid_limit_up(open_count=0, first_time=None, last_time=None) is False


def test_is_evenly_distributed():
    """有效涨停首封时间分布在 ≥2 个时段 → 发酵均匀。"""
    from domain.stock.heuristics import is_evenly_distributed, time_slot_of
    assert time_slot_of("09:45:00") != time_slot_of("13:30:00")
    assert is_evenly_distributed(["09:45:00", "13:30:00"]) is True
    assert is_evenly_distributed(["09:45:00", "09:50:00"]) is False
```

`tests/unit/stock/test_akshare_client.py`：

```python
"""Task 2 失败测试：akshare 薄包装。不访问真实网络——全部 mock。"""

def test_fetch_zt_pool_converts_dataframe_to_dto():
    """fetch_zt_pool 必须把 akshare DataFrame 转换为 LimitStock 列表。"""
    import pandas as pd
    from unittest.mock import patch
    fake_df = pd.DataFrame([{
        "代码": "000001", "名称": "平安银行", "涨跌幅": 10.0,
        "最新价": 15.0, "首次封板时间": "093000",
        "最后封板时间": "093000", "炸板次数": 0, "连板数": 1,
    }])
    with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
        mock_ak.stock_zt_pool_em.return_value = fake_df
        from infrastructure.stock.akshare_client import fetch_zt_pool
        result = fetch_zt_pool("20260728")
        assert len(result) == 1
        assert result[0].stock_code == "000001"
        assert result[0].is_valid_limit_up is True


def test_fetch_zt_pool_error_preserves_chain():
    """akshare 抛具体异常时必须包装为 AkshareFetchError 并保留异常链。"""
    from unittest.mock import patch
    import pytest
    with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
        mock_ak.stock_zt_pool_em.side_effect = ValueError("parse error")
        from infrastructure.stock.akshare_client import AkshareFetchError, fetch_zt_pool
        with pytest.raises(AkshareFetchError) as exc_info:
            fetch_zt_pool("20260728")
        assert isinstance(exc_info.value.__cause__, ValueError)


def test_fetch_zt_pool_empty_returns_empty_list():
    """空数据（非交易日）→ 空列表，不抛异常。"""
    import pandas as pd
    from unittest.mock import patch
    with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
        mock_ak.stock_zt_pool_em.return_value = pd.DataFrame()
        from infrastructure.stock.akshare_client import fetch_zt_pool
        assert fetch_zt_pool("20260726") == []


def test_stock_data_source_protocol_method_set():
    """StockDataSource 协议方法集必须与 openai.yaml 15 个工具一致。"""
    from domain.stock.ports import StockDataSource
    methods = {m for m in vars(StockDataSource) if m.startswith("get_")}
    assert len(methods) == 15
    assert "get_emotion_indicators_trend" in methods
    assert "get_correlation" in methods  # 仅周复盘会话注册
```

#### 步骤 2：写最小实现

`domain/stock/models.py`（端口 I/O 类型由 domain 定义，§8.1）：

```python
"""股票复盘领域模型。Pydantic v2 + ConfigDict(extra="forbid")，公共类有 docstring。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class LimitStock(BaseModel):
    """涨/跌停股票。"""
    model_config = ConfigDict(extra="forbid")
    trade_date: str
    stock_code: str
    stock_name: str
    limit_type: str          # up / down / broken
    consecutive_boards: int
    first_limit_time: str | None
    last_limit_time: str | None
    open_count: int
    is_valid_limit_up: bool


class MarketSnapshot(BaseModel):
    """大盘快照。"""
    model_config = ConfigDict(extra="forbid")
    trade_date: str
    sh_index_pct: float
    sz_index_pct: float
    cyb_index_pct: float
    total_volume: float
    volume_change_pct: float | None
    consecutive_decline_days: int


class EmotionIndicators(BaseModel):
    """单日情绪指标（截面）。"""
    model_config = ConfigDict(extra="forbid")
    trade_date: str
    limit_up_count: int
    limit_down_count: int
    valid_limit_up_count: int
    broken_limit_ratio: float
    max_consecutive_boards: int
    yesterday_limit_up_today_premium: float | None
    total_volume: float
    volume_change_pct: float | None
    phase: str | None
    phase_confidence: str | None
    phase_reason: str | None


class StockDailyRow(BaseModel):
    """个股单日行情。"""
    model_config = ConfigDict(extra="forbid")
    trade_date: str
    stock_code: str
    close: float
    pct_chg: float
    volume: float
    turnover: float | None


class WatchlistStock(BaseModel):
    """观察池条目（日线经组合 DTO 挂载，见 application 层）。"""
    model_config = ConfigDict(extra="forbid")
    stock_code: str
    stock_name: str
    entry_date: str
    entry_reason: str
    entry_price: float
    current_price: float
    cumulative_pct: float
    ma_distance_pct: float
    status: str
    sector_code_at_entry: str | None
    validation_status: str | None


class ReviewReport(BaseModel):
    """复盘文存档。status: final / degraded / no_data。"""
    model_config = ConfigDict(extra="forbid")
    id: str
    user_id: str
    trade_date: str
    status: str
    emotion_phase: str | None
    title: str | None
    content: str
    watchlist_snapshot: str | None
    market_snapshot_json: str | None
    created_at: str


class CorrelationResult(BaseModel):
    """庄股/抱团股识别结果（仅周频，进程内存，不持久化）。"""
    model_config = ConfigDict(extra="forbid")
    computed_at: str
    window_days: int
    zombie_candidates: list[str]      # 与指数/板块相关性 < 0.3
    huddled_groups: list[list[str]]   # 相互相关性 > 0.7 的股票群

# SectorRow / SectorRotation / HeatDistribution / LeaderCandidate /
# DivergenceRow / WatchlistTrendRow / SignalScanResult 同风格补全（均 forbid + docstring）
```

`domain/stock/heuristics.py`（纯函数，无 I/O，可直接单测）：

```python
"""股票复盘启发式纯函数（经验性参考，非硬规则）。"""


def is_valid_limit_up(open_count: int, first_time: str | None, last_time: str | None) -> bool:
    """有效涨停 = 一次性封死（炸板次数=0 且 首封时间=末封时间）。"""
    if first_time is None or last_time is None:
        return False
    return open_count == 0 and first_time == last_time


def time_slot_of(ts: str) -> str:
    """把 HH:MM:SS 映射到 morning_early / morning_late / afternoon / late 时段。"""
    ...


def is_evenly_distributed(valid_limit_times: list[str]) -> bool:
    """有效涨停首封时间分布在 ≥2 个时段 → 发酵均匀（板块高潮判定用）。"""
    return len({time_slot_of(t) for t in valid_limit_times}) >= 2
```

`domain/stock/ports.py`（15 个方法，与 `agents/openai.yaml` 15 个工具一一对应）：

```python
"""股票数据读侧端口。唯一真实实现：infrastructure/stock/sqlite_data_source.py。"""
from __future__ import annotations

from typing import Protocol

from domain.stock.models import (
    CorrelationResult, DivergenceRow, EmotionIndicators, HeatDistribution,
    LeaderCandidate, MarketSnapshot, SectorRotation, SectorRow,
    SignalScanResult, StockDailyRow, WatchlistStock, WatchlistTrendRow,
)


class StockDataSource(Protocol):
    """股票数据源端口（只读 SQLite 缓存；禁止触达实时接口）。"""

    async def get_market_snapshot(self, date: str) -> MarketSnapshot: ...
    async def get_emotion_indicators(self, date: str) -> EmotionIndicators: ...
    async def get_emotion_indicators_trend(self, end_date: str, days: int) -> list[EmotionIndicators]: ...
    async def get_strong_repair_leaders(self, date: str) -> list[SectorRow]: ...
    async def get_sector_rotation(self, date: str) -> SectorRotation: ...
    async def get_sector_heat_distribution(self, sector_code: str, date: str) -> HeatDistribution: ...
    async def get_resistant_sectors(self, date: str) -> list[SectorRow]: ...
    async def get_sector_leaders(self, sector_code: str, date: str) -> list[LeaderCandidate]: ...
    async def get_sector_divergence(self, date: str) -> list[DivergenceRow]: ...
    async def get_sector_rotation_trend(self, end_date: str, days: int) -> list[SectorRotation]: ...
    async def get_watchlist(self) -> list[WatchlistStock]: ...
    async def get_watchlist_trend(self, end_date: str, days: int) -> list[WatchlistTrendRow]: ...
    async def get_stock_daily(self, code: str, days: int) -> list[StockDailyRow]: ...
    async def get_signal_stocks(self, date: str) -> SignalScanResult: ...
    async def get_correlation(self, end_date: str, days: int) -> CorrelationResult: ...  # 仅周复盘会话注册
```

`infrastructure/stock/akshare_client.py`（**只 import domain，不 import application**）：

```python
"""akshare 薄包装层（仅写路径使用：fetcher/pipeline）。

职责：包装 akshare 调用，转换 DataFrame → domain DTO；
捕获具体异常并保留异常链；不做缓存（缓存由 cache_repository 负责）。
"""
from __future__ import annotations

import json
import logging

import akshare as ak
import requests

from domain.stock.heuristics import is_valid_limit_up
from domain.stock.models import LimitStock

logger = logging.getLogger(__name__)

# akshare 无公开统一异常基类；其失败来自 requests 传输层与解析层。
# 捕获具体异常类型，包装后保留异常链（AGENTS.md §5）。
_FETCH_ERRORS = (requests.RequestException, ValueError, KeyError, json.JSONDecodeError)


class AkshareFetchError(Exception):
    """akshare 抓取失败的统一封装（__cause__ 保留原始异常）。"""


def fetch_zt_pool(date: str) -> list[LimitStock]:
    """抓取涨停股池。失败抛 AkshareFetchError；空数据返回空列表。"""
    try:
        df = ak.stock_zt_pool_em(date=date)
    except _FETCH_ERRORS as e:
        raise AkshareFetchError(f"fetch_zt_pool failed for {date}") from e
    if df is None or df.empty:
        return []
    result: list[LimitStock] = []
    for _, row in df.iterrows():
        first_time = str(row.get("首次封板时间", "")) or None
        last_time = str(row.get("最后封板时间", "")) or None
        open_count = int(row.get("炸板次数", 0))
        result.append(LimitStock(
            trade_date=date,
            stock_code=str(row["代码"]),
            stock_name=str(row["名称"]),
            limit_type="up",
            consecutive_boards=int(row.get("连板数", 1)),
            first_limit_time=first_time,
            last_limit_time=last_time,
            open_count=open_count,
            is_valid_limit_up=is_valid_limit_up(open_count, first_time, last_time),
        ))
    return result

# fetch_zt_pool_dtgc / fetch_zt_pool_zbgc / fetch_index_hist /
# fetch_sector_hist / fetch_market_snapshot 同模式实现
```

`tests/fixtures/stock.py`：`FakeStockDataSource`（实现全部 15 个端口方法，返回确定性数据，另提供 `.empty()` 空数据变体）+ `REVIEW_MARKDOWN_OK` + `REVIEW_MARKDOWN_MISSING_SECTION`（样本见附录 A）。

#### 步骤 3：运行测试验证

```powershell
python -m pytest tests/unit/stock/ -v
python -m ruff check domain/stock/ infrastructure/stock/
python -m mypy domain/stock/ infrastructure/stock/
python scripts/check_architecture.py
python -m pip_audit -r requirements.lock
```

**验收**：测试全绿；ruff/mypy 通过；架构检查零违规（`domain/stock/` 无 infrastructure / I/O SDK import）；pip_audit 通过。

#### 步骤 4：提交

```
feat(stock): task2 domain 端口/模型/启发式 + akshare 客户端

- domain/stock/{models,ports,heuristics}（15 方法端口，纯函数启发式）
- infrastructure/stock/akshare_client（具体异常包装 + 异常链）
- akshare 入账 requirements.lock，pip_audit 通过
- 单测 8 项全绿；架构检查零违规
```

---

### Task 3: 7 个数据模块 + 缓存仓储 + 读侧数据源

**目标**：写路径（7 个模块：4 fetcher + 聚合器 + 扫描器 + 相关性分析器）+ `cache_repository.py`（写）+ `sqlite_data_source.py`（读，端口唯一真实实现）。

**依赖**：Task 1（表）+ Task 2（client/DTO/端口）

**Files:**
- Create: `infrastructure/stock/index_fetcher.py`
- Create: `infrastructure/stock/limit_fetcher.py`
- Create: `infrastructure/stock/sector_fetcher.py`
- Create: `infrastructure/stock/market_snapshot_fetcher.py`
- Create: `infrastructure/stock/emotion_aggregator.py`
- Create: `infrastructure/stock/watchlist_scanner.py`
- Create: `infrastructure/stock/correlation_analyzer.py`
- Create: `infrastructure/stock/cache_repository.py`
- Create: `infrastructure/stock/sqlite_data_source.py`
- Test: `tests/unit/stock/test_fetchers.py`
- Test: `tests/unit/stock/test_emotion_aggregator.py`
- Test: `tests/unit/stock/test_watchlist_scanner.py`
- Test: `tests/unit/stock/test_cache_repository.py`
- Test: `tests/integration/stock/test_sqlite_data_source.py`（真实实现集成测试，§8.7）

#### 步骤 1：先写失败测试（关键样本）

`tests/unit/stock/test_emotion_aggregator.py`：

```python
"""Task 3 失败测试：情绪指标聚合逻辑。"""

def test_broken_limit_ratio_calculation():
    """炸板率 = 炸板数 / (涨停数 + 炸板数)。"""
    from infrastructure.stock.emotion_aggregator import calculate_broken_limit_ratio
    assert calculate_broken_limit_ratio(limit_up_count=50, broken_count=10) == 10 / 60


def test_broken_limit_ratio_zero_division():
    """涨停+炸板均为 0 → 0.0（不抛 ZeroDivisionError）。"""
    from infrastructure.stock.emotion_aggregator import calculate_broken_limit_ratio
    assert calculate_broken_limit_ratio(limit_up_count=0, broken_count=0) == 0.0


def test_max_consecutive_boards():
    """最高连板 = consecutive_boards 最大值。"""
    from infrastructure.stock.emotion_aggregator import calculate_max_consecutive_boards
    from domain.stock.models import LimitStock
    stocks = [
        LimitStock(trade_date="20260728", stock_code="001", stock_name="A",
                   limit_type="up", consecutive_boards=3, first_limit_time="09:30:00",
                   last_limit_time="09:30:00", open_count=0, is_valid_limit_up=True),
        LimitStock(trade_date="20260728", stock_code="002", stock_name="B",
                   limit_type="up", consecutive_boards=5, first_limit_time="10:00:00",
                   last_limit_time="10:00:00", open_count=0, is_valid_limit_up=True),
    ]
    assert calculate_max_consecutive_boards(stocks) == 5
```

`tests/unit/stock/test_cache_repository.py`：

```python
"""Task 3 失败测试：缓存仓储白名单与参数化。"""

def test_table_name_whitelist():
    """动态表名不在白名单时必须拒绝（AGENTS.md §4）。"""
    from infrastructure.stock.cache_repository import ALLOWED_TABLES
    assert "market_index_daily" in ALLOWED_TABLES
    assert "evil_table" not in ALLOWED_TABLES


def test_parameterized_sql_prevents_injection(tmp_db):
    """恶意输入作为参数值写入，不得改变 SQL 结构。"""
    from infrastructure.persistence.database import get_connection, init_db
    from infrastructure.stock.cache_repository import StockCacheRepository
    init_db(tmp_db)
    repo = StockCacheRepository(get_connection(tmp_db))
    malicious = "'; DROP TABLE market_index_daily; --"
    repo.upsert_index_daily(trade_date=malicious, index_code="sh000001",
                            open=1.0, close=1.0, high=1.0, low=1.0,
                            volume=1.0, pct_chg=0.0)
    conn = get_connection(tmp_db)
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='market_index_daily'"
    ).fetchone() is not None
```

`tests/integration/stock/test_sqlite_data_source.py`：真实 SQLite（`tmp_db`）seed 数据 → 验证 15 个方法返回与端口契约一致；`get_correlation` 在 analyzer 缓存为空时抛 `CorrelationNotReadyError`。

#### 步骤 2：写最小实现

fetcher 统一模式（以 `limit_fetcher.py` 为例）：

```python
"""涨停数据 fetcher：调用 akshare_client + 写入 SQLite。"""
from __future__ import annotations

import logging

from infrastructure.stock.akshare_client import AkshareFetchError, fetch_zt_pool
from infrastructure.stock.cache_repository import StockCacheRepository

logger = logging.getLogger(__name__)


async def run(trade_date: str, repo: StockCacheRepository) -> int:
    """抓取涨停数据并写入缓存。返回写入条数；失败 log warning 返回 0。"""
    try:
        stocks = fetch_zt_pool(trade_date)
    except AkshareFetchError as e:
        logger.warning("limit_fetcher failed: date=%s err=%s", trade_date, e)
        return 0
    if not stocks:  # 非交易日/数据缺失：跳过写入，不覆盖已有数据
        logger.info("limit_fetcher: no data for %s, skip", trade_date)
        return 0
    repo.upsert_limit_stocks(trade_date, stocks)
    return len(stocks)
```

`cache_repository.py` 关键设计：

```python
"""缓存仓储（写侧）——所有 SQL 参数化，表名白名单（AGENTS.md §4）。"""
from __future__ import annotations

ALLOWED_TABLES = frozenset({
    "market_index_daily", "stock_daily", "limit_stocks_daily",
    "board_ladder_daily", "sector_daily", "emotion_daily",
    "watchlist_stocks", "review_reports",
})


class StockCacheRepository:
    """参数化 upsert（INSERT OR REPLACE，依赖复合主键幂等）。"""

    def __init__(self, conn) -> None:
        self._conn = conn

    def upsert_limit_stocks(self, trade_date: str, stocks: list[LimitStock]) -> None:
        """参数化批量 INSERT OR REPLACE。"""
        for s in stocks:
            self._conn.execute(
                "INSERT OR REPLACE INTO limit_stocks_daily "
                "(trade_date, stock_code, stock_name, limit_type,"
                " consecutive_boards, first_limit_time, last_limit_time,"
                " open_count, is_valid_limit_up) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (s.trade_date, s.stock_code, s.stock_name, s.limit_type,
                 s.consecutive_boards, s.first_limit_time, s.last_limit_time,
                 s.open_count, int(s.is_valid_limit_up)),
            )
        self._conn.commit()
```

`sqlite_data_source.py`（读侧，端口唯一真实实现）：

```python
"""StockDataSource 的 SQLite 实现——复盘链路唯一数据入口（只读缓存）。"""
from __future__ import annotations

from domain.stock.models import CorrelationResult, EmotionIndicators
from infrastructure.stock.correlation_analyzer import CorrelationAnalyzer


class SqliteStockDataSource:
    """全部参数化 SELECT；数据缺失返回空，不抛异常。"""

    def __init__(self, conn, correlation_analyzer: CorrelationAnalyzer) -> None:
        self._conn = conn
        self._correlation = correlation_analyzer

    async def get_emotion_indicators_trend(self, end_date: str, days: int) -> list[EmotionIndicators]:
        """返回 end_date 之前（含）最近 days 个交易日的情绪序列，按日期升序。"""
        rows = self._conn.execute(
            "SELECT * FROM emotion_daily WHERE trade_date <= ? "
            "ORDER BY trade_date DESC LIMIT ?",
            (end_date, days),
        ).fetchall()
        return [self._to_emotion(r) for r in reversed(rows)]

    async def get_correlation(self, end_date: str, days: int) -> CorrelationResult:
        """读 analyzer 进程内存缓存；未就绪抛 CorrelationNotReadyError。"""
        return self._correlation.latest()

    # 其余 13 个方法同模式：参数化 SELECT + DTO 装配 + 空数据返回空
```

`correlation_analyzer.py`（仅周频）：计算 pearson 相关性（<0.3 候选庄股、>0.7 抱团群），结果存实例属性（进程内存），`latest()` 空缓存抛 `CorrelationNotReadyError`；**不持久化**。

#### 步骤 3：运行测试验证

```powershell
python -m pytest tests/unit/stock/ tests/integration/stock/test_sqlite_data_source.py -v
python -m bandit -r infrastructure/stock/ -lll
python scripts/check_architecture.py
```

**验收**：全部测试绿；bandit 无高危；SQL 注入测试通过；读侧集成测试覆盖 15 方法。

#### 步骤 4：提交

```
feat(stock): task3 数据抓取写路径 + SQLite 读侧数据源

- 7 个数据模块（4 fetcher + 聚合器 + 扫描器 + 相关性分析器）
- cache_repository（参数化 + 白名单）与 sqlite_data_source（15 方法读侧）
- 单测 + 读侧集成测试全绿；bandit 无高危；SQL 注入防护验证
```

---

### Task 4: Application 服务层（复盘 + 观察池 + 存档 + 任务注册表）

**目标**：`StockReviewService` 编排 7 步思维链（含观察池入/出池），`ReviewTaskRegistry` 管理异步任务，`ReportService` 管存档与所有权，`StockPipelineService` 作为抓取门面。

**依赖**：Task 1-3

**Files:**
- Create: `application/stock/__init__.py`
- Create: `application/stock/dto.py`（组合 DTO）
- Create: `application/stock/review_service.py`
- Create: `application/stock/watchlist_service.py`
- Create: `application/stock/report_service.py`
- Create: `application/stock/correlation_service.py`
- Create: `application/stock/review_tasks.py`
- Create: `application/stock/pipeline.py`（抓取管线门面 + `get/set_default_pipeline`，供调度器与 admin/refresh 使用）
- Test: `tests/unit/stock/test_review_service.py`
- Test: `tests/unit/stock/test_review_tasks.py`
- Test: `tests/unit/stock/test_watchlist_service.py`
- Test: `tests/integration/stock/test_review_pipeline.py`

#### 步骤 1：先写失败测试（关键）

`tests/integration/stock/test_review_pipeline.py`：

```python
"""Task 4 失败测试：完整 7 步思维链跑通（fake data_source + mock LLM）。"""
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from tests.fixtures.stock import (
    REVIEW_MARKDOWN_MISSING_SECTION, REVIEW_MARKDOWN_OK, FakeStockDataSource,
)


@pytest.mark.asyncio
async def test_pipeline_final_report(tmp_db, mock_llm):
    """正常路径：复盘文含 9 章节，status='final'，已存档。"""
    from application.stock.review_service import StockReviewService

    mock_llm.generate = AsyncMock(return_value=REVIEW_MARKDOWN_OK)
    service = StockReviewService(
        data_source=FakeStockDataSource(),
        llm=mock_llm,
        watchlist_service=...,
        report_service=...,
        skill_md_path=Path("infrastructure/skills/builtin/stock-review/SKILL.md"),
    )
    report = await service.generate_review(user_id="user1", trade_date="20260728")
    assert report.status == "final"
    assert "## 一、周期定位" in report.content
    assert "## 九、方法论说明" in report.content
    assert "不构成投资建议" in report.content


@pytest.mark.asyncio
async def test_pipeline_degraded_after_single_retry(tmp_db, mock_llm):
    """缺章节 → 补全重试恰好 1 次 → 仍缺则 status='degraded' 存档。"""
    mock_llm.generate = AsyncMock(side_effect=[
        REVIEW_MARKDOWN_MISSING_SECTION,
        REVIEW_MARKDOWN_MISSING_SECTION,
    ])
    service = ...
    report = await service.generate_review(user_id="user1", trade_date="20260728")
    assert report.status == "degraded"
    assert mock_llm.generate.await_count == 2  # 初次 + 恰好 1 次重试


@pytest.mark.asyncio
async def test_pipeline_no_data_skips_llm(tmp_db, mock_llm):
    """缓存全空 → status='no_data' 占位存档，不调用 LLM。"""
    mock_llm.generate = AsyncMock(side_effect=AssertionError("不应调用 LLM"))
    service = ...(data_source=FakeStockDataSource.empty())
    report = await service.generate_review(user_id="user1", trade_date="20260728")
    assert report.status == "no_data"


@pytest.mark.asyncio
async def test_pipeline_upsert_same_day(tmp_db, mock_llm):
    """同一用户同一交易日重新生成 → 覆盖旧存档（仅 1 行）。"""
    ...


@pytest.mark.asyncio
async def test_watchlist_exit_and_entry_called(tmp_db, mock_llm):
    """思维链第 5/6 步必须调用观察池出池与入池判定。"""
    ...
```

`tests/unit/stock/test_review_tasks.py`：

```python
"""Task 4 失败测试：任务注册表。"""

def test_create_idempotent_same_user():
    """同一用户已有进行中任务 → 返回同一 task_id（幂等限流）。"""
    from application.stock.review_tasks import ReviewTaskRegistry
    reg = ReviewTaskRegistry()
    t1 = reg.create(user_id="u1", trade_date="20260728")
    t2 = reg.create(user_id="u1", trade_date="20260729")
    assert t1 == t2  # 同一用户至多 1 个进行中任务


def test_done_and_failed_transitions():
    """mark_done 携带 report_id；mark_failed 携带 error_code。"""
    ...


def test_unknown_task_returns_none():
    """未知/过期 task_id → None（API 层映射 404）。"""
    ...
```

#### 步骤 2：写最小实现

`application/stock/dto.py`（组合 DTO——**禁止**在 `extra="forbid"` 模型上动态挂属性，那会抛 ValueError）：

```python
"""application 层组合 DTO。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from domain.stock.models import LeaderCandidate, SectorRow, StockDailyRow, WatchlistStock


class WatchlistEntryWithDaily(BaseModel):
    """观察池条目 + 多日日线（prompt 组装与出池判定用）。"""
    model_config = ConfigDict(extra="forbid")
    entry: WatchlistStock
    daily: list[StockDailyRow]


class SectorWithLeaders(BaseModel):
    """抗跌板块 + 龙头候选。"""
    model_config = ConfigDict(extra="forbid")
    sector: SectorRow
    leaders: list[LeaderCandidate]
```

`application/stock/review_service.py`（7 步思维链，步骤 5/6 含观察池出/入池）：

```python
"""股票周期复盘服务：编排 7 步思维链，调用 LLM 产复盘文。

设计要点：
- 全部依赖构造函数注入（domain 端口），不 import infrastructure
- 7 步思维链严格对应 SKILL.md；第 5/6 步执行观察池出池/入池判定
- 章节校验 9 章 + 声明；L2 重试恰好 1 次；所有结局存档（final/degraded/no_data）
- 不预测具体涨跌，概率性表达（SKILL.md 红线）
"""
from __future__ import annotations

import logging
from pathlib import Path

from application.stock.dto import SectorWithLeaders, WatchlistEntryWithDaily
from application.stock.report_service import ReportService
from application.stock.watchlist_service import WatchlistService
from domain.shared.llm.ports import LLMPort
from domain.stock.models import ReviewReport
from domain.stock.ports import StockDataSource

logger = logging.getLogger(__name__)

REQUIRED_SECTIONS = [
    "## 一、周期定位", "## 二、大盘与量能", "## 三、情绪指标详解",
    "## 四、板块轮动", "## 五、观察池复盘", "## 六、新信号扫描",
    "## 七、明日条件预判", "## 八、风险提示", "## 九、方法论说明",
    "不构成投资建议",
]


class ReviewValidationError(Exception):
    """复盘文章节校验失败。"""


class StockReviewService:
    """股票周期复盘服务。"""

    def __init__(
        self,
        data_source: StockDataSource,
        llm: LLMPort,
        watchlist_service: WatchlistService,
        report_service: ReportService,
        skill_md_path: Path,
    ) -> None:
        self._data = data_source
        self._llm = llm
        self._watchlist = watchlist_service
        self._reports = report_service
        self._skill_md_path = skill_md_path

    async def generate_review(self, user_id: str, trade_date: str) -> ReviewReport:
        """生成复盘文（7 步思维链 + LLM + 校验降级 + upsert 存档）。"""
        # 1. 系统性风险评估（大盘维度）
        market = await self._data.get_market_snapshot(trade_date)
        # 2. 情绪阶段（多日趋势）
        emotion_trend = await self._data.get_emotion_indicators_trend(trade_date, days=10)
        # 3. 与前一交易日对比（读 emotion_daily 中 < trade_date 的最近一行）
        yesterday = await self._data.get_emotion_indicators_before(trade_date)
        # 4. 板块轮动 + 强修复领涨 + 高潮判定
        sector_rotation = await self._data.get_sector_rotation(trade_date)
        sector_trend = await self._data.get_sector_rotation_trend(trade_date, days=5)
        repair_leaders = await self._data.get_strong_repair_leaders(trade_date)

        # 5. 观察池复盘：组合 DTO 挂日线 → 出池判定（启发式）
        watchlist = await self._data.get_watchlist()
        entries = [
            WatchlistEntryWithDaily(
                entry=w,
                daily=await self._data.get_stock_daily(w.stock_code, days=10),
            )
            for w in watchlist
        ]
        await self._watchlist.evaluate_exits(entries)

        # 6. 新信号扫描 → 入池判定
        signals = await self._data.get_signal_stocks(trade_date)
        resistant = [
            SectorWithLeaders(
                sector=s,
                leaders=await self._data.get_sector_leaders(s.sector_code, trade_date),
            )
            for s in await self._data.get_resistant_sectors(trade_date)
        ]
        divergence = await self._data.get_sector_divergence(trade_date)
        await self._watchlist.add_new_entries(signals, resistant, divergence, trade_date)

        # L0：缓存全空 → 占位存档，不调 LLM
        if not emotion_trend and not watchlist:
            return await self._reports.save_no_data(user_id, trade_date)

        # 7. LLM 产文（SKILL.md 注入 system prompt）
        system_prompt = self._load_skill_prompt()
        user_prompt = self._build_user_prompt(
            market, emotion_trend, yesterday, sector_rotation, sector_trend,
            repair_leaders, entries, signals, resistant, divergence,
        )
        markdown = await self._llm.generate(
            system=system_prompt, user=user_prompt, temperature=0.3, max_tokens=4000,
        )

        # 校验 → L2 重试恰好 1 次 → L3 降级存档
        try:
            self._validate_markdown(markdown)
            status = "final"
        except ReviewValidationError as first_error:
            retry_prompt = (
                f"{user_prompt}\n\n上次输出缺失必需内容：{first_error}。"
                "请补全后重新输出完整复盘文。"
            )
            markdown = await self._llm.generate(
                system=system_prompt, user=retry_prompt, temperature=0.3, max_tokens=4000,
            )
            try:
                self._validate_markdown(markdown)
                status = "final"
            except ReviewValidationError as second_error:
                logger.warning("review degraded: %s", second_error)
                status = "degraded"
                markdown = f"> 降级说明：{second_error}\n\n" + markdown

        # 8. 情绪阶段回填 + upsert 存档（同一交易日覆盖）
        report = await self._reports.save(
            user_id=user_id, trade_date=trade_date, status=status, content=markdown,
        )
        return report

    def _load_skill_prompt(self) -> str:
        """加载 SKILL.md 全文作为 system prompt（超限降级见文档 §4.2）。"""
        return self._skill_md_path.read_text(encoding="utf-8")

    def _validate_markdown(self, markdown: str) -> None:
        """校验 9 章节 + 免责声明齐全，缺失抛 ReviewValidationError。"""
        missing = [s for s in REQUIRED_SECTIONS if s not in markdown]
        if missing:
            raise ReviewValidationError(f"复盘文缺失章节: {missing}")
```

**其余服务要点**：
- `watchlist_service.py`：`evaluate_exits(entries)`（多日走势 + 均线偏离，天数参数化）、`add_new_entries(...)`（分类别写入）、入池次日验证逻辑
- `report_service.py`：`save()`（`INSERT OR REPLACE` by `UNIQUE(user_id, trade_date)`，刷新 `created_at`）、`save_no_data()`（占位存档）、`list_mine(user_id, page)`（**仅本人**）、`get_owned(report_id, user_id)`（非 owner 返回 None → API 404）
- `correlation_service.py`：委托 `data_source.get_correlation`；`CorrelationNotReadyError` 由 API 层映射 409
- `review_tasks.py`：`create`（幂等，同人 1 个进行中任务）、`get`（running/done/failed + report_id + error_code）、TTL 1 小时惰性清理；进程重启丢失（前端 404 重试）
- `pipeline.py`：`StockPipelineService.fetch_and_store_morning/close(date)`（串行调 7 个数据模块 + 反爬 sleep）、`run_weekly_correlation(date)`、`admin_refresh(start, end)`（日期范围回填，默认最近 60 个交易日）、持有 `trade_dates` 交易日历缓存；模块级 `set_default_pipeline()/get_default_pipeline()`（镜像 hotspot 的 `get_default_service` 模式）

#### 步骤 3：运行测试验证

```powershell
python -m pytest tests/unit/stock/ tests/integration/stock/test_review_pipeline.py -v
python -m mypy application/stock/
python scripts/check_architecture.py
```

**验收**：集成测试 5 项全绿（final/degraded/no_data/upsert/观察池调用）；任务注册表单测全绿；application 层零 infrastructure import。

#### 步骤 4：提交

```
feat(stock): task4 复盘/观察池/存档/任务注册应用服务

- StockReviewService 7 步思维链（含观察池出/入池）+ L0-L3 降级存档
- ReviewTaskRegistry（幂等 + TTL）、ReportService（upsert + 所有权）
- StockPipelineService 抓取门面 + 默认实例注册（供调度器）
- 集成测试 5 项 + 单测全绿；架构检查零违规
```

---

### Task 5: API 层（13 端点，单文件）

**目标**：实现 13 个 REST 端点 + DTO + 授权 + 失败场景，单文件 `api/v1/stock.py`（与既有平铺约定一致，见接缝 2）。

**依赖**：Task 4

**Files:**
- Create: `api/v1/stock.py`
- Modify: `api/v1/__init__.py`（注册路由）
- Modify: `app.py`（组合根装配 + AppContainer 字段，见接缝 1）
- Modify: `api/server.py`（app.state 绑定，见接缝 3）
- Test: `tests/integration/stock/test_stock_api.py`

#### 端点清单（13 个）

| 端点 | 方法 | 用途 | 授权 |
|------|------|------|------|
| `/api/v1/stock/market/snapshot` | GET | 大盘快照 | 登录用户 |
| `/api/v1/stock/charts/emotion` | GET | 情绪多日曲线（AI 用的趋势数据） | 登录用户 |
| `/api/v1/stock/charts/sector` | GET | 板块轮动多日曲线 | 登录用户 |
| `/api/v1/stock/charts/watchlist` | GET | 观察池多日表现 | 登录用户 |
| `/api/v1/stock/watchlist` | GET | 当前观察池 | 登录用户 |
| `/api/v1/stock/review` | POST | 触发复盘（异步，幂等） | 登录用户 |
| `/api/v1/stock/review/task/{task_id}` | GET | 查任务状态（轮询） | owner |
| `/api/v1/stock/reports` | GET | 复盘文列表（**仅本人**） | 登录用户 |
| `/api/v1/stock/reports/{id}` | GET | 复盘文详情 | owner（否则 404） |
| `/api/v1/stock/sectors/rotation` | GET | 板块轮动 | 登录用户 |
| `/api/v1/stock/sectors/{code}/stocks` | GET | 板块内股票 | 登录用户 |
| `/api/v1/stock/correlation` | GET | 庄股/抱团股识别（读周五任务缓存） | 登录用户 |
| `/api/v1/stock/admin/refresh` | POST | 手动触发抓取/历史回填 | 管理员 |

**失败场景**：401 未登录；403 非管理员调 admin；404 报告不存在/跨用户/任务不存在或过期；409 `CORRELATION_NOT_READY`；422 参数错误（Pydantic 自动）；503 akshare/LLM 失败。错误响应 `{"code": "...", "message": "..."}`，不暴露堆栈。

**admin/refresh 语义**（兼作首次部署历史回填入口）：
- 请求体 `{"start_date": "YYYY-MM-DD"?, "end_date": "YYYY-MM-DD"?}`；缺省回填**最近 60 个交易日**
- 幂等（`INSERT OR REPLACE`）；返回 `{"refreshed": <写入条数>}`
- **首次部署后必须手动触发一次回填**，否则趋势曲线为空（前端空态兜底）

#### 步骤 1：先写失败测试

`tests/integration/stock/test_stock_api.py`（认证 fixture 复用既有模式：经注册端点拿真实 token——参考 [`test_token_security.py`](../../../tests/integration/test_token_security.py)，本地定义 `_token(client, username)` 辅助函数；GET 用 cookie，POST 用 Bearer 或 cookie+CSRF）：

```python
"""Task 5 失败测试：API 契约 + 授权 + 失败场景。"""

async def test_reports_list_only_mine(client):
    """列表仅含本人复盘文。"""
    token_a = await _token(client, "user_a")
    token_b = await _token(client, "user_b")
    # seed：A、B 各有 1 篇报告
    resp = await client.get("/api/v1/stock/reports", cookies={"auth_token": token_a})
    assert resp.status_code == 200
    assert all(r["user_id"] == "user_a" for r in resp.json())


async def test_get_report_cross_user_404(client):
    """跨用户访问详情 → 404（对象级未授权，不是 403）。"""
    ...
    resp = await client.get(f"/api/v1/stock/reports/{report_id}",
                            cookies={"auth_token": token_b})
    assert resp.status_code == 404


async def test_correlation_not_ready_409(client):
    """周五任务未跑（缓存空）→ 409 CORRELATION_NOT_READY。"""
    resp = await client.get("/api/v1/stock/correlation",
                            cookies={"auth_token": await _token(client, "u")})
    assert resp.status_code == 409
    assert resp.json()["code"] == "CORRELATION_NOT_READY"


async def test_trigger_review_idempotent(client):
    """重复触发（进行中）→ 返回同一 task_id。"""
    ...


async def test_admin_refresh_requires_admin(client):
    """非管理员 → 403。"""
    ...


async def test_unauthenticated_401(client):
    """无凭据 → 401。"""
    resp = await client.get("/api/v1/stock/market/snapshot")
    assert resp.status_code == 401
```

#### 步骤 2：写最小实现

`api/v1/stock.py`（关键片段；路由从 `request.app.state` 取服务，不 `new` 任何东西）：

```python
"""股市复盘 API：13 端点，单文件（与 api/v1/ 平铺约定一致）。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict

router = APIRouter()


class EmotionChartResponse(BaseModel):
    """情绪多日曲线响应。"""
    model_config = ConfigDict(extra="forbid")
    series: list[EmotionIndicatorsDto]
    window_days: int


@router.get("/charts/emotion", response_model=EmotionChartResponse)
async def get_emotion_chart(
    request: Request,
    end_date: str,
    days: int = Query(10, ge=1, le=60),
) -> EmotionChartResponse:
    """返回情绪指标多日序列（前端 ECharts + AI 趋势数据）。不返回 ECharts option。"""
    _require_user(request)
    data_source = request.app.state.stock_review_service.data_source
    series = await data_source.get_emotion_indicators_trend(end_date, days=days)
    return EmotionChartResponse(series=series, window_days=days)


@router.post("/review", status_code=202)
async def trigger_review(request: Request, body: TriggerReviewRequest) -> dict[str, str]:
    """触发复盘：登记任务并后台执行。幂等——进行中任务返回同一 task_id。"""
    user_id = _require_user(request)
    tasks = request.app.state.stock_review_tasks
    task_id = tasks.create(user_id=user_id, trade_date=body.trade_date)
    tasks.launch_background(task_id)  # asyncio.create_task 跑 service.generate_review
    return {"task_id": task_id}


@router.get("/review/task/{task_id}")
async def get_review_task(task_id: str, request: Request) -> ReviewTaskStatusDto:
    """查询任务状态（前端轮询）。非 owner / 不存在 / 过期 → 404。"""
    user_id = _require_user(request)
    task = request.app.state.stock_review_tasks.get(task_id)
    if task is None or task.user_id != user_id:
        raise HTTPException(status_code=404)
    return task


@router.get("/reports/{report_id}")
async def get_report(report_id: str, request: Request) -> ReviewReportDto:
    """复盘文详情。跨用户 → 404。"""
    user_id = _require_user(request)
    report = await request.app.state.stock_review_service.get_owned_report(
        report_id=report_id, user_id=user_id,
    )
    if report is None:
        raise HTTPException(status_code=404)
    return report


@router.get("/correlation")
async def get_correlation(request: Request) -> CorrelationResultDto:
    """庄股/抱团股识别（读周五任务进程内存缓存）。未就绪 → 409。"""
    _require_user(request)
    try:
        return await request.app.state.stock_review_service.get_correlation()
    except CorrelationNotReadyError as e:
        raise HTTPException(
            status_code=409,
            detail={"code": "CORRELATION_NOT_READY",
                    "message": "庄股/抱团股识别结果尚未生成（每周五收盘后计算）"},
        ) from e
```

> 说明：现有 chat 的 SSE 是单请求 `StreamingResponse`，无常驻推送通道；本特性 MVP **用轮询**（`GET /review/task/{task_id}`），不引入 SSE。如需推送后续单独立项。

`app.py` / `api/server.py` / `api/v1/__init__.py` 修改：分别见接缝 1 / 接缝 3 / 接缝 2。

#### 步骤 3：运行测试验证

```powershell
python -m pytest tests/integration/stock/test_stock_api.py -v
python -m ruff check api/v1/stock.py
python -m mypy api/v1/stock.py
python scripts/check_architecture.py
```

**验收**：13 端点契约测试全绿；401/403/404/409 行为正确；api 层零 infrastructure import。

#### 步骤 4：提交

```
feat(stock): task5 /api/v1/stock 13 端点 + 组合根装配

- 单文件路由（平铺约定）：13 端点 + 失败场景（401/403/404/409/422/503）
- 任务幂等触发 + 轮询查询；correlation 缓存未就绪 409
- admin/refresh 历史回填（缺省 60 交易日，幂等）
- API 契约测试全绿；架构检查零违规

本提交含组合根改动（app.py AppContainer/装配，AGENTS.md §8.7 声明事项）。
```

---

### Task 6: 调度器注册

**目标**：`application/scheduler.py` 追加 stock 调度函数（含防漏补抓），挂到 `lifespan`。

**依赖**：Task 3（fetcher）+ Task 4（pipeline）

**Files:**
- Modify: `application/scheduler.py`（追加 `run_stock_morning_fetch` / `run_stock_close_fetch` / `_is_trading_day`）
- Modify: `api/server.py`（lifespan create_task + cancel）
- Test: `tests/integration/stock/test_scheduler.py`

#### 步骤 1：先写失败测试

```python
"""Task 6 失败测试：调度触发与防漏。"""

def test_close_fetch_runs_after_1630_on_trading_day(...):
    """交易日 16:30 后唤醒 → 执行收盘管线。"""
    ...

def test_close_fetch_catchup_after_restart(...):
    """进程 17:00 重启（错过窗口）→ 唤醒后 due 判定仍触发当日补抓。"""
    ...

def test_close_fetch_idempotent_same_day(...):
    """当日已完成后再次唤醒 → 不重复执行（last_done_date 节流）。"""
    ...

def test_correlation_only_on_friday(...):
    """仅周五在收盘管线后串行追加相关性分析。"""
    ...

def test_non_trading_day_skips(...):
    """非交易日（周末/节假日）→ 跳过，不写库。"""
    ...

def test_fetch_failure_does_not_raise(...):
    """akshare 失败 → 仅 log warning，任务不抛异常。"""
    ...
```

#### 步骤 2：写最小实现

按 §5.3 的 `run_stock_close_fetch` 完整实现（含 `last_done_date` + due 判定 + 10 分钟轮询 + 周五串行追加）；`run_stock_morning_fetch` 同构（11:30 窗口，不含相关性分析）。依赖一律 `from application.stock.pipeline import get_default_pipeline` 函数内惰性取用（接缝 4）。

#### 步骤 3：运行测试验证

```powershell
python -m pytest tests/integration/stock/test_scheduler.py -v
python scripts/check_architecture.py
```

**验收**：6 项测试全绿；lifespan 注册/清理与现有 4 个 task 一致。

#### 步骤 4：提交

```
feat(stock): task6 后台调度（交易日 11:30/16:30，周五链式相关性）

- run_stock_morning/close_fetch：due 判定 + 当日节流 + 重启补抓
- 交易日历内存缓存；非交易日跳过；失败不抛异常
- lifespan 挂接与清理；调度测试 6 项全绿

本提交含组合根/lifespan 改动（AGENTS.md §8.7 声明事项）。
```

---

### Task 7: 前端 features/stock/ + ECharts + 轮询

**目标**：前端页面 + ECharts 图表 + API 客户端 + 任务轮询。

**依赖**：Task 5

**Files:**
- Create: `frontend/src/features/stock/api.ts`
- Create: `frontend/src/features/stock/types.ts`
- Create: `frontend/src/features/stock/MarketOverview.tsx`
- Create: `frontend/src/features/stock/EmotionChart.tsx`
- Create: `frontend/src/features/stock/SectorRotation.tsx`
- Create: `frontend/src/features/stock/Watchlist.tsx`
- Create: `frontend/src/features/stock/ReviewReport.tsx`
- Create: `frontend/src/features/stock/ReviewTrigger.tsx`
- Create: `frontend/src/features/stock/index.tsx`
- Create: `frontend/src/features/stock/__tests__/api.test.ts`
- Create: `frontend/src/features/stock/__tests__/EmotionChart.test.tsx`
- Create: `frontend/src/features/stock/__tests__/ReviewTrigger.test.tsx`
- Modify: `frontend/src/components/NavSidebar.tsx`（加菜单，见接缝 7）
- Modify: `frontend/src/App.tsx`（加路由 `/stock`）
- Modify: `frontend/package.json` + `package-lock.json`（`npm install echarts echarts-for-react`，锁文件同步入账）

#### 步骤 1：先写失败测试

`__tests__/api.test.ts`：

```typescript
import { describe, expect, it, vi } from 'vitest';
import { stockApi } from '../api';

describe('stockApi', () => {
  it('getEmotionChart 调用正确端点', async () => {
    const mockGet = vi.fn().mockResolvedValue({ series: [], window_days: 10 });
    vi.mock('../../auth/client', () => ({ client: { get: mockGet } }));
    await stockApi.getEmotionChart('20260728', 10);
    expect(mockGet).toHaveBeenCalledWith(
      '/api/v1/stock/charts/emotion?end_date=20260728&days=10',
    );
  });
});
```

`__tests__/EmotionChart.test.tsx`：空 `series` → 显示"暂无数据"。

`__tests__/ReviewTrigger.test.tsx`：轮询三分支——`done` → 跳转报告页；`failed` → 错误文案 + 可重试；轮询 404 → 提示重新触发。

#### 步骤 2：写最小实现

`api.ts`（走 `features/auth/client.ts`，§8.6）：

```typescript
import { client } from '../auth/client';
import type {
  CorrelationResult, EmotionChartResponse, MarketSnapshot, ReviewReport,
  ReviewTaskStatus, SectorRotation, WatchlistStock,
} from './types';

export const stockApi = {
  getMarketSnapshot: () => client.get<MarketSnapshot>('/api/v1/stock/market/snapshot'),
  getEmotionChart: (endDate: string, days: number) =>
    client.get<EmotionChartResponse>(`/api/v1/stock/charts/emotion?end_date=${endDate}&days=${days}`),
  getSectorRotation: (date: string) => client.get<SectorRotation>(`/api/v1/stock/sectors/rotation?date=${date}`),
  getWatchlist: () => client.get<WatchlistStock[]>('/api/v1/stock/watchlist'),
  triggerReview: (tradeDate: string) =>
    client.post<{ task_id: string }>('/api/v1/stock/review', { trade_date: tradeDate }),
  getReviewTask: (taskId: string) =>
    client.get<ReviewTaskStatus>(`/api/v1/stock/review/task/${taskId}`),
  listReports: (page: number) => client.get<ReviewReport[]>(`/api/v1/stock/reports?page=${page}`),
  getReport: (id: string) => client.get<ReviewReport>(`/api/v1/stock/reports/${id}`),
  getCorrelation: () => client.get<CorrelationResult>('/api/v1/stock/correlation'),
  adminRefresh: (range?: { start_date?: string; end_date?: string }) =>
    client.post<{ refreshed: number }>('/api/v1/stock/admin/refresh', range ?? {}),
};
```

`types.ts`（strict，禁 any；与后端 DTO 一一对应）：

```typescript
export interface ReviewTaskStatus {
  status: 'running' | 'done' | 'failed';
  report_id?: string;
  error_code?: string;
}

export interface EmotionChartResponse {
  series: EmotionIndicators[];
  window_days: number;
}
// MarketSnapshot / EmotionIndicators / WatchlistStock / ReviewReport /
// SectorRotation / CorrelationResult 与 domain/stock/models.py 字段一一对应
```

**任务轮询**（`ReviewTrigger`）：
- `triggerReview` 后每 3s 轮询 `getReviewTask`
- `done` → 跳转 `/stock/reports/{report_id}`；`failed` → 按 `error_code` 展示文案并允许重试
- 轮询 404（任务过期/进程重启）→ 视为失败，提示重新触发
- 组件卸载清理定时器

**ECharts**：涨停数/炸板率/连板高度/溢价曲线 + 板块轮动桑基图；观察窗口 5/10/20/60 日切换；空数据显示"暂无数据"（不臆测）；图表容器 `aria-label` + 键盘可达的窗口切换控件。

#### 步骤 3：运行测试验证

```powershell
npm --prefix frontend run lint
npm --prefix frontend run check
npm --prefix frontend run test
npm --prefix frontend run build
```

**验收**：四项全绿；空数据/轮询三分支测试通过。

#### 步骤 4：提交

```
feat(stock): task7 前端 /stock 页面 + ECharts 趋势曲线 + 任务轮询

- features/stock 八个组件 + api.ts/types.ts（auth client 走 Cookie+CSRF）
- 轮询 done/failed/404 三分支；空数据"暂无数据"；窗口 5/10/20/60 日
- echarts 依赖入账（package-lock 同步）
- lint/check/test/build 全绿
```

---

### Task 8: Agent 配置 + 章节校验 + 工具注册边界

**目标**：核实 `agents/openai.yaml` 15 工具与端口一致；确认 skill 被加载；`get_correlation` 仅周复盘会话注册。

**依赖**：Task 2-5

**Files:**
- Verify: `infrastructure/skills/builtin/stock-review/agents/openai.yaml`
- Verify: `infrastructure/skills/builtin/stock-review/SKILL.md`
- Modify: Agent 工具装配处（日复盘会话剔除 `get_correlation`；具体位置按现有 skill 工具装配实现确定，通常在 orchestrator/skill 加载层）
- Test: `tests/unit/stock/test_skill_loaded.py`

#### 步骤 1：先写失败测试

```python
"""Task 8 失败测试：skill 加载与工具边界。"""

def test_stock_skill_loaded_by_provider():
    """FileSkillProvider 必须加载 stock-review skill。"""
    from config import settings
    from infrastructure.skills.provider import FileSkillProvider
    provider = FileSkillProvider(skills_dir=settings.skills_dir)
    skill = provider.get_skill("stock-review")
    assert skill is not None


def test_yaml_tools_match_port_methods():
    """yaml 15 个工具名必须与 StockDataSource 端口方法一一对应。"""
    import yaml
    from domain.stock.ports import StockDataSource
    tools = set(yaml.safe_load(open(
        "infrastructure/skills/builtin/stock-review/agents/openai.yaml",
        encoding="utf-8",
    ))["interface"]["tools"])
    methods = {m for m in vars(StockDataSource) if m.startswith("get_")}
    assert tools == methods
    assert len(tools) == 15


def test_daily_session_excludes_correlation_tool():
    """日复盘会话的工具清单不得包含 get_correlation；周复盘会话包含。"""
    daily_tools = build_stock_tools(session_mode="daily")
    weekly_tools = build_stock_tools(session_mode="weekly")
    assert "get_correlation" not in {t.name for t in daily_tools}
    assert "get_correlation" in {t.name for t in weekly_tools}
```

#### 步骤 2：写最小实现

- 工具装配处按 `session_mode` 过滤：`daily` → 剔除 `get_correlation`；`weekly` → 全量 15 个
- 确认 yaml 与 SKILL.md 内容（v4 软化版）无需改动；若方法论有调整必须同步 SKILL.md

#### 步骤 3：运行测试验证

```powershell
python -m pytest tests/unit/stock/test_skill_loaded.py -v
```

**验收**：3 项测试全绿。

#### 步骤 4：提交

```
feat(stock): task8 Agent 工具清单校验与周复盘边界

- yaml 15 工具 ↔ 端口方法一致性测试
- get_correlation 仅周复盘会话注册（装配层强制）
- skill 加载验证；3 项测试全绿
```

---

### Task 9: 测试与 CI 全量验证

**目标**：E2E 测试 + 全量 CI（零容忍），修复所有违规，覆盖率达标。

**Files:**
- Create: `tests/e2e/stock/__init__.py`
- Create: `tests/e2e/stock/test_e2e_review.py`

#### 步骤 1：E2E 测试（轮询，无 SSE）

```python
"""Task 9：端到端——触发复盘 → 轮询完成 → 查看复盘文。"""

async def test_e2e_trigger_review_and_view(client):
    """完整链路：注册登录 → POST /review → 轮询 task 至 done → GET 报告 → 9 章节。"""
    token = await _token(client, "e2e_user")
    # 1. admin/refresh 回填（或直接 seed 缓存数据）
    # 2. POST /api/v1/stock/review → task_id
    resp = await client.post(
        "/api/v1/stock/review",
        json={"trade_date": "20260728"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 202
    task_id = resp.json()["task_id"]
    # 3. 轮询至 done（超时保护）
    report_id = await _poll_until_done(client, token, task_id, timeout_s=30)
    # 4. GET /reports/{id} → 含 9 章节 + 声明
    report = await client.get(f"/api/v1/stock/reports/{report_id}",
                              cookies={"auth_token": token})
    assert report.status_code == 200
    body = report.json()
    assert body["status"] == "final"
    assert "不构成投资建议" in body["content"]
```

#### 步骤 2：全量 CI（必须贴实际输出）

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

> 架构检查器**零容忍，无 baseline 参数**（AGENTS.md §8.5）。发现违规只能改代码消除。

#### 步骤 3：修复违规并复跑

- 架构违规 → 改 import 消除（不存在"更新基线"这个选项）
- 覆盖率不足 → 补测试
- mypy/ruff 错误 → 修类型/风格

**验收**：全部命令全绿；实际输出贴在 PR 描述里（不是"我跑过"）。

#### 步骤 4：提交

```
test(stock): task9 e2e 复盘链路 + 全量 CI 验证

- e2e：触发 → 轮询 → 查看（9 章节 + status=final）
- CI 全绿（架构/ruff/mypy/bandit/pytest≥70%/pip_audit + 前端四项）
- 实际输出已贴 PR 描述
```

---

## 8. 验收清单

- [ ] Task 1 迁移 v021：8 张表 + 索引 + `UNIQUE(user_id, trade_date)` + status 列 + up/down 通过
- [ ] Task 2 akshare 入账 `requirements.lock` 且 pip_audit 通过；domain 端口 15 方法 + 启发式纯函数单测
- [ ] Task 3 七个数据模块 + 读侧数据源测试全绿；bandit 无高危；SQL 注入防护验证
- [ ] Task 4 思维链集成测试 5 项全绿（final/degraded/no_data/upsert/观察池出入池）；任务注册表幂等 + TTL
- [ ] Task 5 十三端点契约测试全绿；401/403/404/409 正确；`/reports` 仅本人
- [ ] Task 6 调度测试 6 项全绿；交易日触发 + 非交易日跳过 + 重启补抓 + 周五链式 + 失败不抛异常
- [ ] Task 7 前端 lint/check/test/build 全绿；空数据"暂无数据"；轮询三分支
- [ ] Task 8 yaml 15 工具 ↔ 端口一致；日复盘会话**不含** `get_correlation`
- [ ] Task 9 e2e 全链路通过；CI 全绿；覆盖率 ≥ 70%；实际输出已贴
- [ ] 复盘文含 9 章节 + "不构成投资建议"；缺章节重试恰好 1 次，降级存档可重生成
- [ ] 跨用户访问 `/reports/{id}` → 404；缓存未就绪 `/correlation` → 409 `CORRELATION_NOT_READY`
- [ ] 架构守卫：`python scripts/check_architecture.py` 零违规（无 baseline）
- [ ] **提交纪律：9 个 Task 各自独立 commit，message 符合 §3 第 16-20 条，历史可逐 Task 回溯**

---

## 9. 风险与应对

| 风险 | 应对 |
|------|------|
| akshare 接口挂 | 缓存缺数据 → 复盘文标注"该维度数据缺失"，不臆测（§4.5） |
| akshare 无统一异常基类 | 包装层捕获 requests/解析层具体异常，`raise AkshareFetchError from e` |
| akshare 反爬封 IP | fetcher 串行 + 1-2 秒 sleep + 最多重试 2 次（§5.4） |
| 首次部署无历史数据 | `admin/refresh` 缺省回填 60 交易日；未回填时前端空态"暂无数据" |
| 调度窗口漏抓 | due 判定 + 当日节流 + 重启补抓（§5.3）；跨天缺口 admin/refresh 补 |
| 任务状态进程内存 | 重启丢失；前端轮询 404 → 提示重新触发（MVP 可接受） |
| LLM 输出缺章节 | L2 重试 1 次 → L3 降级存档（§4.3） |
| LLM context 超限 | SKILL.md 按 3 万 token 上限预算 + 核心章节降级注入 + 数据裁剪（§4.2） |
| 复盘文被过度依赖 | 末尾强制声明"不构成投资建议" |
| 历史迁移被误改 | 新版本组纯追加；`_validate_registry()` 连续性自检兜底 |
| 架构违规蔓延 | CI 阻断 + 检查器零容忍（无 baseline/豁免） |
| 时区/节假日错误 | `ZoneInfo("Asia/Shanghai")` + 交易日历缓存查表（§5.1） |

---

## 10. 实施顺序与提交计划

```
Task 1 (迁移)        ──commit──> feat(stock): task1
Task 2 (domain+客户端)──commit──> feat(stock): task2
Task 3 (数据模块+读侧)──commit──> feat(stock): task3
Task 4 (应用服务)     ──commit──> feat(stock): task4
Task 5 (API+组合根)   ──commit──> feat(stock): task5（含组合根声明）
Task 6 (调度器)       ──commit──> feat(stock): task6（含 lifespan 声明）
Task 7 (前端)         ──commit──> feat(stock): task7
Task 8 (Agent 边界)   ──commit──> feat(stock): task8
Task 9 (e2e+CI)       ──commit──> test(stock): task9
```

每个 Task 完成后自审（AGENTS.md §7）：
- 业务边界（无预测/推荐/目标价）
- 端口归属（端口在 domain；application 不 import infrastructure）
- 授权（所有权 404；列表仅本人）
- 敏感数据（凭据/用户隐私不进日志）
- 迁移（不修改历史）
- 测试（fake/mock 严格；新端口同步 fake + 集成测试）
- 前端（TypeScript strict + 无 any）
- 提交（独立 commit + 门禁全绿 + 清单勾选）

---

## 附录 A：测试夹具

`tests/fixtures/stock.py` 提供：
- `FakeStockDataSource`：实现 `StockDataSource` 全部 15 方法的测试替身（确定性数据）；`.empty()` 返回全空变体（no_data 路径用）
- `REVIEW_MARKDOWN_OK`：含 9 章节 + "不构成投资建议"的样本复盘文
- `REVIEW_MARKDOWN_MISSING_SECTION`：缺章节样本（降级测试用）
- `mock_llm` fixture：AsyncMock 包装的 `LLMPort`

`REVIEW_MARKDOWN_OK` 样本：

```markdown
# 2026-07-28 A股周期复盘
## 一、周期定位
今日情绪阶段：弱修复
## 二、大盘与量能
上证 +0.5%
## 三、情绪指标详解
涨停 40 家
## 四、板块轮动
领涨：半导体
## 五、观察池复盘
[列表]
## 六、新信号扫描
无
## 七、明日条件预判
基准情景：弱修复延续
## 八、风险提示
数据缺失风险
## 九、方法论说明
本内容仅为数据复盘推演，不构成投资建议。
```

---

**文档版本**：v2.1，2026-07-28
**业务基线**：SKILL.md v4（软化版）
**规范基线**：AGENTS.md v3.1
