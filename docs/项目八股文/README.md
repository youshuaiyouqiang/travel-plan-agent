# 云合项目面试八股文 · 总纲

> **目标岗位：** AI 智能体开发工程师（后端方向）
> **项目载体：** 云合（FastAPI + DDD 分层 + 多 Agent 编排 + SQLite）
> **创建日期：** 2026-08-02
> **使用方式：** 本文件是系列文档的"宪法"。后续每一章问答文档（无论由谁/哪个 AI 执笔）都必须先读本文件，严格遵守「写作铁律」。

---

## 一、定位与设计原则

1. **岗位定向。** 面试目标是 AI 智能体开发岗，因此全系列向三个方向倾斜：
   - **LLM/Agent 通用八股**（Prompt、Function Calling、ReAct、记忆、MCP、稳定性工程）是主战场，篇幅最重；
   - **项目深挖**（云合的编排、推理、工具、记忆、会话五大系统）是定级别的关键，必须最细；
   - Python/Web/数据库/安全是门槛，要求"必拿分"，不追求偏怪难。
2. **不做前端问答。** 前端（React/TS/Vite）不单独成章。仅在项目深挖篇涉及"前后端契约"（Cookie + CSRF、SSE 事件协议）时以后端视角提及。
3. **真实代码锚定，拒绝空谈。** 这是本系列与网上八股的根本区别：每道题的概念都必须落到云合仓库里**真实存在的代码**。面试时的标准叙事是"概念 → 我项目里怎么做的 → 代码在哪 → 踩过什么坑"。
4. **追问链结构。** 项目深挖题不是 `Q→A`，而是模拟大厂面试官连续拷打的**链式追问**（L1→L7 层层递进），提前把每条链挖到面试官可能到达的最深处。

---

## 二、系列目录

### 基础篇（八股 · 门槛分）

| 章 | 文件 | 核心内容 | 难度 | 状态 |
|---|---|---|---|---|
| 01 | `基础篇/第01章-Python基础.md` | 数据类型、可变/不可变、函数传参、闭包装饰器、迭代器生成器、OOP、异常、类型注解 | ⭐~⭐⭐⭐ | 已完成 |
| 02 | `基础篇/第02章-Python进阶.md` | GIL、装饰器进阶、描述符、元类、内存管理、dataclass、Protocol | ⭐⭐⭐~⭐⭐⭐⭐ | 待写 |
| 03 | `基础篇/第03章-并发与异步编程.md` | 线程/进程/协程选型、asyncio 事件循环、`asyncio.to_thread` 桥接同步阻塞库 | ⭐⭐⭐⭐ | 待写 |
| 04 | `基础篇/第04章-FastAPI与Web后端.md` | 路由、依赖注入、中间件执行顺序、生命周期/lifespan、Pydantic v2、SSE 流式响应 | ⭐⭐⭐~⭐⭐⭐⭐ | 待写 |
| 05 | `基础篇/第05章-数据库与持久化.md` | SQL、索引、事务隔离、SQLite 特性与局限、参数化查询、版本化迁移 | ⭐⭐⭐~⭐⭐⭐⭐ | 待写 |
| 06 | `基础篇/第06章-网络与安全.md` | HTTP、Cookie/Session、CSRF/XSS/SQL 注入、鉴权方案对比、限流、CORS | ⭐⭐⭐~⭐⭐⭐⭐ | 待写 |
| 07 | `基础篇/第07章-LLM应用基础.md` | 大模型 API 核心参数、Prompt 工程、结构化输出/JSON mode、上下文窗口管理 | ⭐⭐⭐ | 待写 |
| 08 | `基础篇/第08章-FunctionCalling与工具使用.md` | 工具 schema 设计、参数校验、并行调用、工具错误处理与重试 | ⭐⭐⭐⭐ | 待写 |
| 09 | `基础篇/第09章-Agent模式与编排.md` | ReAct、Plan-Execute、Router/委派、多智能体协作、人机回环、Agent 状态机 | ⭐⭐⭐⭐~⭐⭐⭐⭐⭐ | 待写 |
| 10 | `基础篇/第10章-RAG与记忆系统.md` | Embedding、向量检索、chunking、混合检索、短期/长期记忆分层、记忆蒸馏 | ⭐⭐⭐⭐ | 待写 |
| 11 | `基础篇/第11章-LLM稳定性与成本工程.md` | Fallback 降级链、重试与超时、限流、Token 成本核算、LLM 输出评估与观测 | ⭐⭐⭐⭐ | 待写 |
| 12 | `基础篇/第12章-MCP协议与工具生态.md` | MCP 协议原理、server/client 架构、工具发现与鉴权、与 Function Calling 的关系 | ⭐⭐⭐⭐ | 待写 |
| 13 | `基础篇/第13章-测试与质量保障.md` | pytest、mock/fake/stub 区别、覆盖率门禁、CI 阻断式检查、TDD 实践 | ⭐⭐⭐ | 待写 |
| 14 | `基础篇/第14章-系统设计方法论.md` | 开放设计题答题框架（需求澄清→容量估算→API→数据模型→权衡） | ⭐⭐⭐⭐⭐ | 待写 |

### 项目深挖篇（定级别 · 最细）

每篇对应云合的一条可深挖主线。写作前**必须先通读对应代码与文档**。

| 篇 | 文件 | 主线 | 关键代码锚点（写作前必读） | 状态 |
|---|---|---|---|---|
| 00 | `项目深挖篇/00-项目总述与自我介绍.md` | 30 秒/2 分钟/5 分钟电梯演讲；技术选型辩护；"最难的是什么" | `README.md`、`docs/superpowers/specs/2026-07-16-product-and-news-agent-design.md`、`AGENTS.md` | 待写 |
| 01 | `项目深挖篇/01-Agent编排深挖.md` | 云合调度员定位；快路径→Function Calling→委派三层决策；单轮委派后控制权回收；动态 Agent | `domain/agent/orchestrator.py`、`domain/agent/dynamic_agent.py`、`domain/agent/factory.py`、`application/builtin_agents/*.yaml` | 待写 |
| 02 | `项目深挖篇/02-推理引擎深挖.md` | ReAct 循环状态机；决策解析与 JSON 修复；工具选择；成本护栏；最大轮次兜底 | `domain/reasoning/engine.py`、`decision_parser.py`、`json_extract.py`、`tool_selector.py`、`cost_guard.py`、`message_builder.py`、`prompts.py` | 待写 |
| 03 | `项目深挖篇/03-LLM接入与稳定性工程.md` | OpenAI 兼容封装；多模型 Fallback 降级链；超时/重试；Token 成本 | `infrastructure/llm/openai.py`、`infrastructure/llm/fallback.py`、`domain/reasoning/cost_guard.py` | 待写 |
| 04 | `项目深挖篇/04-工具系统与MCP深挖.md` | 工具注册/编目/执行/策略四层；适配器隔离副作用；MCP 目录与处理器；技能系统 | `infrastructure/tools/registry.py`、`catalog.py`、`executor.py`、`policy.py`、`adapters/`、`infrastructure/mcp/`、`infrastructure/skills/` | 待写 |
| 05 | `项目深挖篇/05-记忆系统深挖.md` | 长期记忆提取与蒸馏；画像；记忆写入边界（草稿不进长期记忆） | `domain/memory/manager.py`、`memory_extractor.py`、`memory_distiller.py`、`ports.py` | 待写 |
| 06 | `项目深挖篇/06-会话管理与状态机深挖.md` | 会话模式（默认/锁定）；新闻会话只能服务端创建；计划确认服务 | `application/session/service.py`、`confirm_plan_service.py`、`api/v1/session.py`、`api/v1/chat.py` | 待写 |
| 07 | `项目深挖篇/07-业务深挖-新闻研判.md` | 热点定时抓取与双缓存；锚点字段裁剪；证据分级（verified/conflicted/未核实线索）；来源治理与 AI 评分 | `application/news/hotspot_service.py`、`analysis_service.py`、`source_rubric_scorer.py`、`source_candidate_scorer.py`、`application/scheduler.py`、`api/v1/news.py`、`api/v1/admin_news.py` | 待写 |
| 08 | `项目深挖篇/08-业务深挖-旅行行程.md` | 草稿/不可变存档状态机；`manual_edit_fields` 防 Agent 覆盖；"更新信息"才查外部数据的成本控制 | `application/travel/`、`domain/travel/`、`api/v1/itinerary.py`、`api/v1/travel.py` | 待写 |
| 09 | `项目深挖篇/09-业务深挖-股票复盘.md` | 异步任务+轮询（为什么不用 WebSocket）；user+trade_date 幂等；warmup 回填不阻塞 ready；`asyncio.to_thread` 桥接 akshare | `application/stock/pipeline.py`、`review_service.py`、`review_task_registry.py`、`warmup.py`、`infrastructure/stock/`、`api/v1/stock.py` | 待写 |
| 10 | `项目深挖篇/10-架构与依赖治理深挖.md` | DDD 四层；端口 Protocol 先于实现；唯一组合根；AST 架构守卫零容忍 | `app.py`（`build_container`）、`api/server.py`（`create_api`）、`scripts/check_architecture.py`、`domain/*/ports.py`、`AGENTS.md` §8 | 待写 |
| 11 | `项目深挖篇/11-认证与安全深挖.md` | HttpOnly Cookie + 双提交 CSRF；Bearer 双模式共存；对象级未授权返回 404；用户+IP 双维限流 | `api/middleware/auth.py`、`api/middleware/error_handler.py`、`api/v1/auth.py`、`infrastructure/security/` | 待写 |
| 12 | `项目深挖篇/12-数据层与迁移深挖.md` | SQLite 选型辩护（必被 challenge）；20 个版本化迁移与回滚；历史迁移不可改；并发写应对 | `infrastructure/persistence/`（`connection.py`/`schema.py`/`migrations/`）、`AGENTS.md` §8.6 | 待写 |
| 13 | `项目深挖篇/13-测试与CI深挖.md` | fake 端口单测不碰网络/SQLite；70% 覆盖率门禁；阻断式 CI 关卡；TDD 执行 | `tests/`（unit/integration/e2e）、`.github/workflows/ci.yml`、`pyproject.toml` | 待写 |
| 14 | `项目深挖篇/14-压力面与开放设计题.md` | SQLite 扛不住怎么办；SSE 多实例扩展；内存缓存多副本不一致；LLM 成本控制；重来做会改什么 | 综合全项目；先读 00~13 篇再写 | 待写 |

---

## 三、写作铁律（后续每章必须遵守）

> 以下条款是约束"写文档的 AI/人"的。任何一章不符合铁律，视为半成品。

### 铁律 1：先读代码，再动笔

- 写任何一道**项目深挖题**之前，必须真实打开并通读「关键代码锚点」列出的文件，禁止凭本文件或记忆虚构实现细节。
- 写**基础篇**题目时，凡是云合项目里有对应实践的（如"为什么不能裸 except"对应 `AGENTS.md` §5、`asyncio.to_thread` 对应股票模块），必须先找到代码再写「项目关联」。

### 铁律 2：代码引用格式

- 引用格式：`文件相对路径` 的 `类名/函数名`，例如：`domain/reasoning/engine.py` 的 `ReasoningEngine.run()`。
- **禁止引用行号**（代码会演进，行号必漂移）。引用符号名（类/函数/常量）才稳定。
- 引用的符号必须真实存在；写完一章后自查：每个引用都能在仓库中搜到。

### 铁律 3：数字锚点必须核实

- 凡出现"N 个 API 端点 / N 个路由模块 / N 个内置 Agent / N 个迁移 / 覆盖率 N%"等数字，写之前用命令核实（如 `rg` 数路由、`ls` 数迁移目录），并在文末「本章数字来源」注明核实方式。
- 当前已知锚点（写作时仍需复核）：`api/v1/` 下 17 个路由模块；内置 Agent 定义在 `application/builtin_agents/*.yaml`；迁移固定 20 个版本；覆盖率门禁 70%。

### 铁律 4：基础篇每题模板（8 段）

```markdown
#### 【面试题】问题原文
- **难度：** ⭐~⭐⭐⭐⭐⭐
- **一句话答案：** 面试时先抛的结论（≤3 句话）
- **考察点：** 面试官真正想验证什么
- **参考答案：** 展开讲解，必要处配最小代码示例（Python 3.11+ 风格：内置泛型、`X | None`）
- **记忆技巧：** 口诀 / 对比表格 / 生活类比，至少一种
- **面试官追问：** 2~4 个 follow-up，附简答
- **项目关联：** 云合项目中的对应代码场景（格式遵守铁律 2；无关联则写"无"，禁止硬凑）
```

### 铁律 5：项目深挖篇每题模板（8 段 · 追问链版）

```markdown
#### 【主线题】问题原文
- **难度：** ⭐⭐⭐~⭐⭐⭐⭐⭐
- **一句话答案：** 先抛结论（含数字锚点优先）
- **考察点：** 这条线面试官想挖什么能力
- **追问链：**
  - L1 问题 → 答案要点
  - L2 问题 → 答案要点
  - …（每条链 5~8 层，层层递进；标注【合格线】在 L3、【优秀线】在 L5）
- **埋雷点：** 面试官可能故意挖的坑 + 安全跳法
- **项目证据：** 真实代码位置（格式遵守铁律 2）+ 该代码体现了什么设计意图
- **记忆技巧：** 一页纸总结 / 决策树 / 口诀
```

### 铁律 6：追问链深度标准

- L1~L3：多数候选人能答，必须秒答且准确。
- L4~L5：拉开差距层，考察"为什么这么设计"而不只是"是什么"。
- L6~L8：探底层，答不出时给出标准话术："这层我没实践过，但我的思路是……"——文档里要提前写好这个思路。

### 铁律 7：叙事红线

- **前端归属：** 不声称前端是自己独立开发的。统一口径："我负责后端与架构，同时制定了前后端契约（Cookie + CSRF 客户端规范、SSE 事件协议、API 分层规范）"。深挖篇涉及前端时只讲契约与设计，不讲 React 实现细节。
- **AI 辅助开发：** 准备两套话术——「工程治理版」（强调 AGENTS.md 规范、架构守卫、质量门禁如何约束 AI 产出）与「淡化工具版」（只讲架构与结果）。按面试氛围选用。
- **不夸大：** 没有在代码里验证过的设计意图，不允许写成"我们就是这样做的"。

### 铁律 8：语言与风格

- 全部简体中文；代码、命令、文件路径保持 ASCII。
- 代码示例遵循云合项目规范：Python 3.11+ 内置泛型、`X | None`、具体异常捕获、不泄露密钥。
- 不写"众所周知""显而易见"等空话；能用表格对比的不用大段文字。

### 铁律 9：每章收尾

每章末尾必须包含：
1. **本章速查表**（所有题的一句话答案汇总，供面试前 30 分钟扫读）；
2. **自测清单**（合上文档能复述的关键点）；
3. **本章数字来源**（铁律 3 要求的核实记录，仅项目深挖篇）。

---

## 四、学习方法建议（文档使用者）

1. **三轮法：** 第一轮通读理解 → 第二轮只看"一句话答案"自测，答不出的回读 → 第三轮按「追问链」模拟对答，录音复盘。
2. **面试前一天：** 只刷每章「速查表」+ 深挖篇 00 的电梯演讲。
3. **答到边界的话术：** 被追到 L6+ 不会时，不硬编，用"这层我没实践过，但我的思路是……"把话题引回自己熟悉的层。

---

## 五、进度追踪

| 日期 | 完成内容 | 备注 |
|---|---|---|
| 2026-08-02 | 总纲 README 建立 | 确定双篇结构、写作铁律、岗位定向（AI 智能体后端） |
| 2026-08-02 | 基础篇第 01 章 Python 基础 | 25 题，6 层递进；项目关联锚点已逐一检索核实 |

> 每完成一章，在本表登记一行，并同步更新「系列目录」中对应状态为"已完成"。
