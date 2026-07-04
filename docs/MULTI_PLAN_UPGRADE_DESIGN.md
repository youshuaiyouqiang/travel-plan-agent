# 行程规划智能体——多方案对比 & 商用化升级设计文档

> 版本: v1.1（评审修复版）  
> 日期: 2026-07-04  
> 作者: 产品 & 技术设计  
> 状态: 评审修复完成，待实施  
> 修订说明: v1.1 修复了 v1.0 评审中提出的 4 项硬伤 + 5 项重要问题 + 5 项文档质量问题

---

## 目录

1. [现状分析与问题诊断](#1-现状分析与问题诊断)
2. [核心改造目标](#2-核心改造目标)
3. [整体交互流程设计](#3-整体交互流程设计)
4. [后端改造方案](#4-后端改造方案)
   - 4.1 Prompt 工程重构
   - 4.2 和风天气 Skill 接入
   - 4.3 自驾费用预估工具
   - 4.4 多方案 itinerary 数据模型扩展
   - 4.5 方案选择与锁定机制
   - 4.6 方案修改策略（缓存复用 & 修改分类）★ 核心
     - 4.6.1 模型看的 vs 用户看的（分层架构）
     - 4.6.2 修改三层分类（纯局部 / 半局部 / 核心变更）
     - 4.6.3 识别机制：三层判断
     - 4.6.4 费用预估策略
     - 4.6.5 多方案指代消解
     - 4.6.6 修改后的输出规范
5. [前端改造方案](#5-前端改造方案)
   - 5.1 双按钮 UI 设计
   - 5.2 方案卡片展示
   - 5.3 按钮锁定与禁用逻辑
6. [实施路线图](#6-实施路线图)
7. [风险评估与应对](#7-风险评估与应对)

---

## 1. 现状分析与问题诊断

### 1.1 当前产品能力

| 维度 | 现状 | 评价 |
|------|------|------|
| 方案数量 | 仅生成 **1 版** 行程 | ❌ 没有选择空间，不够商用 |
| 交通对比 | 飞猪返回机票+高铁，Prompt 要求对比 | ⚠️ 有对比但没有结构化表格展示 |
| 自驾方案 | 完全缺失 | ❌ 缺口 |
| 天气信息 | 高德天气 (`amap_get_weather`)，和风天气 skill 未接入 | ⚠️ 高德天气不够专业，应禁用，改用和风天气 |
| 住宿推荐 | 飞猪搜索酒店，LLM 推荐 | ⚠️ 飞猪只返回一个酒店价格，推荐较随意 |
| 费用汇总 | LLM 自行计算汇总 | ⚠️ 不够结构化；除交通/酒店有 API 价格外，餐饮/门票/市内交通允许模型预估但需标注 |
| 方案类型 | 不分类型，一刀切 | ❌ 没有"打卡型"vs"经济型"区分 |
| 用户修改 | 支持简单修改（换酒店/景点） | ⚠️ 只能单方案修改，不能跨方案比较 \\
| 确认按钮 | 只有 **1 个**"满意，生成概览"按钮 | ❌ 多方案下无法选择确认哪个 |
| 方案锁定 | 无锁定机制 | ❌ 用户确认 A 方案后，B 方案按钮仍然可能被点击 |

### 1.2 核心问题总结

```
用户: "帮我规划去成都玩3天"
系统: → 搜机票、搜高铁、搜酒店、搜景点 → 生成 1 套方案 → 用户只能接受或修改

问题链:
  ① 用户看到 1 套方案，不知道这个方案"好在哪里"
  ② 没有对比就没有说服力——和谁比？比什么？
  ③ 用户想省钱，但没有"经济型方案"可选
  ④ 用户想自驾去，但没有这个选项
  ⑤ 费用是一笔糊涂账（LLM 口算，没有结构化的费用明细表）
  ⑥ 用户对方案 A 的酒店不满意，想看看方案 B，但系统只能改当前方案
```

---

## 2. 核心改造目标

### 2.1 一句话目标

> 让行程规划从"给你一套方案，爱要不要"变成"给你三套出行方式 × 两种方案风格，数据驱动的对比，你选一个，我来落地"。

### 2.2 量化目标

| 能力 | 当前 | 目标 |
|------|------|------|
| 出行方式对比 | 2 种（飞机 vs 高铁） | **3 种**（飞机 vs 高铁 vs 自驾） |
| 方案风格 | 1 种通用型 | **2 种**（景点打卡型 / 经济实惠型） |
| 费用对比 | LLM 口算 | **结构化表格**（交通+住宿+餐饮+门票+其他=总价） |
| 确认按钮 | 1 个 | **2 个**（方案一生成概览 / 方案二生成概览） |
| 方案锁定 | 无 | **确认后另一方案按钮禁用** |
| 修改灵活性 | 只支持单方案修改 | **跨方案修改**（"第一个方案酒店换便宜的"） |
| 天气数据 | 仅高德天气 | **高德 + 和风天气双源** |

---

## 3. 整体交互流程设计

```
┌─────────────────────────────────────────────────────────────────┐
│                    用户: "帮我规划去成都玩3天"                        │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 1: 并行调用数据源                                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │ 飞猪机票  │  │ 飞猪高铁  │  │ 高德路线  │  │ 和风天气  │        │
│  │(价格+时间)│  │(价格+时间)│  │(过路费+距 │  │(出行日期  │        │
│  │          │  │          │  │离+耗时)  │  │天气预报) │        │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │
│  ┌──────────┐  ┌──────────┐                                     │
│  │ 飞猪酒店  │  │ 高德景点  │                                     │
│  └──────────┘  └──────────┘                                     │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 2: LLM 生成"出行方式对比表"（结构化）                          │
│                                                                   │
│  ┌──────────┬──────────┬──────────┬──────────┐                   │
│  │   维度    │  ✈️ 飞机  │ 🚄 高铁  │ 🚗 自驾  │                   │
│  ├──────────┼──────────┼──────────┼──────────┤                   │
│  │   耗时    │  2.5h    │   8h     │  15h     │                   │
│  │   费用    │  ¥780    │  ¥550   │  ¥900*   │                   │
│  │   舒适度  │  ⭐⭐⭐⭐  │  ⭐⭐⭐   │  ⭐⭐     │                   │
│  │   灵活度  │  ⭐⭐     │  ⭐⭐⭐   │  ⭐⭐⭐⭐⭐ │                   │
│  │ 天气影响 │  小       │   小     │ 中(雨天) │                   │
│  └──────────┴──────────┴──────────┴──────────┘                   │
│  *自驾费用 = 过路费¥400(高德) + 油费¥300 + 餐饮途中¥200             │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 3: LLM 分别生成两套方案                                       │
│                                                                   │
│  ┌─────────────────────┐  ┌─────────────────────┐                │
│  │   方案一：景点打卡型   │  │  方案二：经济实惠型    │                │
│  │   (最大化游览体验)    │  │   (最小化总花费)      │                │
│  ├─────────────────────┤  ├─────────────────────┤                │
│  │ 交通: 飞机 ¥780      │  │ 交通: 高铁 ¥550      │                │
│  │ 酒店: 春熙路某酒店    │  │ 酒店: 某经济连锁      │                │
│  │  ¥350/晚 ×2 = ¥700  │  │  ¥150/晚 ×2 = ¥300  │                │
│  │ Day1: 宽窄巷子→锦里  │  │ Day1: 免费景点+小吃街 │                │
│  │ Day2: 都江堰+青城山  │  │ Day2: 熊猫基地¥55    │                │
│  │ Day3: 大熊猫基地     │  │ Day3: 武侯祠¥50      │                │
│  │ 总预算: ¥2100        │  │ 总预算: ¥1100        │                │
│  └─────────────────────┘  └─────────────────────┘                │
│                                                                   │
│  [为方案一生成行程概览]   [为方案二生成行程概览]                      │
└─────────────────────────────────────────────────────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    ▼                         ▼
          ┌──────────────┐          ┌──────────────┐
          │ 用户选方案一  │          │ 用户选方案二  │
          │ → 生成概览    │          │ → 生成概览    │
          └──────┬───────┘          └──────┬───────┘
                 │                         │
                 └──────────┬──────────────┘
                            ▼
          ┌──────────────────────────────────────────┐
          │  ⚠️ 会话级锁定：一旦任一方案被确认，          │
          │  本次会话内所有方案的确认按钮全部禁用         │
          │  → 方案一按钮：灰色 "已选择方案二"            │
          │  → 方案二按钮：灰色 "已选择方案一"            │
          │  → 仅保留已确认方案的跳转卡片入口             │
          └──────────────────────────────────────────┘
                            │
                            ▼
          ┌──────────────────────────────────────────┐
          │  用户不满意？自然语言修改：                    │
          │  "第一个方案的酒店能不能便宜点"                │
          │  → 理解"第一个方案"=方案一                    │
          │  → 重新搜索酒店→更新方案一                    │
          │  → 重新展示对比→更新总价                      │
          │  "第二个方案能坐飞机去吗"                      │
          │  → 方案二的交通改为飞机                       │
          │  → 重新计算总价                              │
          └──────────────────────────────────────────┘
```

---

## 4. 后端改造方案

### 4.1 Prompt 工程重构

#### 4.1.1 当前 Prompt 结构

```python
# domain/travel/prompting.py - 当前
def _build_optimization_section(self) -> str:
    # 交通优化：同时搜索机票和高铁
    # 住宿优化：推荐 2-3 个酒店
    # 行程优化：景点相近安排
    # 预算优化：计算总预算
```

**问题**：Prompt 只要求生成 1 套方案，没有"两套方案"的生成指令。

#### 4.1.2 新 Prompt 结构

需要在 `_build_optimization_section()` 和 `_build_execution_rules_section()` 中新增一个独立 section：**Multi-Plan Generation Strategy**。

```python
# domain/travel/prompting.py - 新增方法
def _build_multi_plan_section(self) -> str:
    return "\n".join([
        "## Multi-Plan Generation Strategy（多方案生成策略）",
        "",
        "你必须同时生成两套完整的行程方案。这是商用产品的核心能力，不是可选功能。",
        "",
        "### 方案一：景点打卡型（体验优先）",
        "- 目标：在有限时间内让用户打卡尽可能多的经典景点",
        "- 交通策略：选择最快的交通方式（通常飞机优先），减少路途时间",
        "- 住宿策略：选择景点密集区的中高端酒店（每晚300-500元），减少通勤时间",
        "- 行程策略：每天安排3-4个经典景点，路线紧凑高效",
        "- 预算策略：不刻意省钱，但也不铺张浪费，注重体验/价格比",
        "- 适用人群：第一次去该目的地、想多逛景点的用户",
        "",
        "### 方案二：经济实惠型（预算优先）",
        "- 目标：最低总花费完成旅行",
        "- 交通策略：选择最便宜的交通方式（高铁/火车优先），接受较长路途时间",
        "- 住宿策略：选择性价比高的经济型酒店/民宿（每晚100-200元），位置可稍偏但交通便利",
        "- 行程策略：每天安排2-3个景点，优先选择免费/低价景点，穿插当地小吃街",
        "- 预算策略：每项花费都选最低档，但保留1-2个核心体验",
        "- 适用人群：学生党、预算敏感型用户",
        "",
        "### 方案差异由数据驱动，不硬造差异",
        "两套方案的本质区别是**策略**，不是强制换出行方式或酒店。一切以 API 返回的真实数据为准：",
        "",
        "- **出行方式**：方案一选最优体验（综合考虑耗时+舒适度，不排斥贵的），方案二选最低价格。",
        "  如果飞机恰好比高铁还便宜 → 两个方案都选飞机，这是数据驱动的合理结果，不是 bug。",
        "  如果只有一种交通方式可达 → 两个方案都用同一种，无需硬造差异。",
        "- **酒店**：方案一选评分高/位置好的（哪怕贵），方案二选单价最低的。",
        "  如果飞猪返回的酒店只有一个价位 → 方案一用它，方案二也用同一个价格但 LLM 可推荐一个更便宜的替代（标注为预估）。",
        "- **景点**：方案一每天3-4个经典景点全打卡，方案二每天2-3个优先选免费/低价的，去掉高门票项目。",
        "- 两套方案都需要包含**完整的每日行程 + 费用明细表**",
        "",
        "### 输出结构要求",
        "你的回复必须按以下结构组织：",
        "",
        "## 🚗 出行方式对比",
        "| 维度 | ✈️ 飞机 | 🚄 高铁 | 🚗 自驾 |",
        "|------|---------|---------|---------|",
        "| 耗时 | Xh | Xh | Xh |",
        "| 费用 | ¥XXX | ¥XXX | ¥XXX |",
        "| 舒适度 | ... | ... | ... |",
        "| 天气影响 | ... | ... | ... |",
        "",
        "自驾费用说明：过路费¥XX(高德地图数据) + 油费¥XX(由 estimate_drive_cost 工具计算) + 其他费用¥XX",
        "",
        "## 🏨 住宿选项",
        "列出3-4个不同价位/位置的酒店，标注推荐原因",
        "",
        "## 📋 方案一：景点打卡型",
        "### 出行方式：✈️ 飞机（推荐原因...）",
        "### 住宿：XX酒店（推荐原因...）",
        "### Day 1: ...",
        "### Day 2: ...",
        "### 💰 方案一费用明细：",
        "| 项目 | 费用 | 数据来源 | 说明 |",
        "|------|------|----------|------|",
        "| 往返交通 | ¥XX | 🟢 API | 飞猪机票/高铁往返价 |",
        "| 住宿 | ¥XX | 🟢 API | 飞猪酒店单价 × 晚数 |",
        "| 景点门票 | ¥XX | 🟡 预估 | 基于模型知识，以实际为准 |",
        "| 餐饮 | ¥XX | 🟡 预估 | 按150元/天(一线)或100元/天(其他) |",
        "| 市内交通 | ¥XX | 🟡 预估 | 打车/地铁，约30-50元/天 |",
        "| **总计** | **约 ¥XX** | — | 其中 ¥XX 为 API 价格，¥XX 为预估值 |",
        "",
        "⚠️ 费用标注规则：API 返回的价格不标注；LLM 预估价格必须标注 [预估] 或 🟡 预估",
        "⚠️ 餐饮预估标准：一线城市(北上广深)150元/人/天，二线(成都杭州等)120元/人/天，其他100元/人/天",
        "",
        "## 📋 方案二：经济实惠型",
        "（同上结构）",
        "",
        "## 🏆 推荐方案",
        "根据你的情况，我推荐方案X，原因是：...",
        "",
        "### 结构化锚点注入（★ 关键：前端依赖此标记渲染按钮）",
        "在回复的**最末尾**，你必须注入一行 HTML 注释格式的结构化锚点，",
        "前端通过解析此锚点来渲染双按钮，**不通过正则扫描正文**：",
        "",
        "<!--MULTI_PLAN:plan1=sightseeing,plan2=budget-->",
        "",
        "规则：",
        "- 锚点必须是 HTML 注释格式，独占一行，放在回复最末尾",
        "- plan1 恒为 sightseeing（景点打卡型），plan2 恒为 budget（经济实惠型）",
        "- 如果因降级只生成了单方案，注入：<!--MULTI_PLAN:plan1=sightseeing-->（只有 plan1）",
        "- 如果是修改后的方案更新，在锚点中加 version：",
        "  <!--MULTI_PLAN:plan1=sightseeing:v2,plan2=budget:v1-->",
        "- 锚点之外不得有其他 HTML 注释，避免前端解析歧义",
        "",
        "### 确认环节",
        "在锚点之前加入确认询问语：",
        "「您更倾向于哪个方案？我可以为任一方案生成完整的行程概览卡片，或者告诉我需要调整的地方」",
    ])
```

> **★ 结构化锚点协议说明（前后端契约）**
>
> 之所以用 HTML 注释而非 JSON，是因为 LLM 回复直接渲染为 Markdown/HTML，HTML 注释不会在用户界面上可见，但前端可以在渲染前通过 DOM 解析器或正则 `<!--MULTI_PLAN:(.*?)-->` 精确提取。这比扫描正文匹配"方案一"可靠得多——LLM 正文措辞可能千变万化，但锚点格式是硬约束。
>
> 前端解析伪代码：
> ```typescript
> const ANCHOR_RE = /<!--MULTI_PLAN:(.*?)-->/
> function parseMultiPlanAnchor(content: string): MultiPlanAnchor | null {
>   const m = content.match(ANCHOR_RE)
>   if (!m) return null
>   // 解析 "plan1=sightseeing:v2,plan2=budget:v1" → 结构化对象
>   const plans: Record<string, PlanMeta> = {}
>   for (const part of m[1].split(',')) {
>     const [key, val] = part.split('=')
>     const [type, version] = val.split(':')
>     plans[key] = { type, version: version || 'v1' }
>   }
>   return { plans }
> }
> ```
```

#### 4.1.3 修改 `build_react_system()`

在 `build_react_system()` 中调用新增的 `_build_multi_plan_section()`：

```python
def build_react_system(self, ctx: PromptContext) -> str:
    sections = [
        self._build_identity_section(),
        self._build_optimization_section(),
        self._build_multi_plan_section(),  # ★ 新增
        self._build_execution_rules_section(),
        self._build_task_section(ctx),
        self._build_tools_section(ctx),
        self._build_session_section(ctx),
    ]
    return "\n\n".join(section for section in sections if section.strip())
```

#### 4.1.4 更新执行规则 (Execution Rules)

在 `_build_execution_rules_section()` 中补充多方案执行的步骤：

```python
# 步骤 2-5 需要扩展
"2. **搜索交通**：同时调用 fliggy_search_flight、fliggy_search_train、" 
"以及 amap_plan_route（用于自驾路线+过路费），三者并行调用",
"2.5. **计算自驾费用**：根据 amap_plan_route 返回的距离/过路费，" 
"调用 estimate_drive_cost 工具计算自驾总费用（含车型差异化油费 + 途中餐饮），不要自行口算",
"3. **搜索住宿**：调用 fliggy_search_hotel，获取至少 4-5 个不同价位的酒店选项",
"5. **查询天气**：调用 qweather_forecast 查询出行期间的逐日天气（含温度、降水概率）",
# 确认询问语也需要改
"「您更倾向于哪个方案？比如'选方案一''要方案二'，或者告诉我需要调整的地方」",
```

---

### 4.2 和风天气 Skill 接入（替代高德天气）

#### 4.2.1 为什么不用高德天气

| 对比维度 | 高德天气 `amap_get_weather` | 和风天气 `qweather_forecast` |
|----------|---------------------------|------------------------------|
| 数据粒度 | 粗略（仅"晴/雨/多云"） | 精细（温度范围、降水概率%、风力等级、湿度） |
| 预报天数 | 4天 | 3/7/10/15/30天可选 |
| 小时预报 | 不支持 | 24/72/168小时可选 |
| 专业度 | 地图公司的附属功能 | 专业气象服务商 |
| 行程规划场景 | ⚠️ 只能判断"会不会下雨" | ✅ 可评估"哪天适合户外景点、哪天可能有暴雨影响自驾" |

**决策：高德天气工具 `amap_get_weather` 在旅行规划中禁用，全面使用和风天气。**

> 注意：`amap_get_weather` 工具 spec 保留在 ToolRegistry 中（其他智能体可能用到），但 Prompt 中不引导 LLM 调用它。如果 LLM 意外调用了，也能工作，不做强硬拦截。

#### 4.2.2 当前状态

- `infrastructure/skills/builtin/q-weather/` 已存在，包含完整的 `qweather_tool.py`
- 支持：城市查询(lookup)、实时天气(now)、逐日预报(daily 3/7/10/15/30天)、逐小时预报(hourly)
- **未接入**到 ToolRegistry 和 travel.yaml 的技能列表

#### 4.2.3 接入步骤

**Step 1: 创建和风天气 Tool Adapter**

新建文件 `infrastructure/tools/adapters/qweather.py`：

```python
from __future__ import annotations

import json
import logging
import os
import re
import subprocess

from infrastructure.tools.base import ToolHandler, ToolSpec
from config import settings

logger = logging.getLogger(__name__)

QWEATHER_KEY = os.environ.get("WEATHER_API_KEY", "")
_SCRIPT = str(settings.skills_dir / "q-weather" / "scripts" / "qweather_tool.py")

# ★ 输入校验：城市名只允许中文/英文/数字/连字符，防止命令注入
_LOCATION_RE = re.compile(r"^[\u4e00-\u9fa5a-zA-Z0-9\-]+$")


def _validate_location(location: str) -> str | None:
    """校验城市名输入，返回错误信息或 None（通过）"""
    if not location:
        return "missing location"
    if len(location) > 50:
        return "location too long (max 50 chars)"
    if not _LOCATION_RE.match(location):
        return "location contains invalid characters"
    return None


def _check_qweather_key() -> str | None:
    """KEY 校验（启动时 & 调用时均可调用）"""
    if not QWEATHER_KEY:
        return "WEATHER_API_KEY 环境变量未设置，和风天气工具不可用"
    return None


def _run_qweather(args: list[str]) -> dict:
    # ★ 调用时再次校验 KEY
    key_err = _check_qweather_key()
    if key_err:
        return {"is_error": True, "content": key_err}

    cmd = ["python", _SCRIPT] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                                env={**os.environ, "WEATHER_API_KEY": QWEATHER_KEY})
        if result.returncode != 0:
            return {"is_error": True, "content": f"和风天气调用失败: {result.stderr[:500]}"}
        try:
            data = json.loads(result.stdout)
            return {"is_error": False, "content": json.dumps(data, ensure_ascii=False, indent=2)}
        except json.JSONDecodeError:
            return {"is_error": False, "content": result.stdout[:3000]}
    except subprocess.TimeoutExpired:
        return {"is_error": True, "content": "和风天气请求超时"}
    except Exception as e:
        return {"is_error": True, "content": f"和风天气调用异常: {e}"}


async def _qweather_city_lookup(arguments: dict) -> dict:
    location = str(arguments.get("location", "")).strip()
    err = _validate_location(location)
    if err:
        return {"is_error": True, "content": err}
    return _run_qweather(["lookup", location])


async def _qweather_now(arguments: dict) -> dict:
    location = str(arguments.get("location", "")).strip()
    err = _validate_location(location)
    if err:
        return {"is_error": True, "content": err}
    return _run_qweather(["now", location])


async def _qweather_forecast(arguments: dict) -> dict:
    """逐日天气预报（核心工具）"""
    location = str(arguments.get("location", "")).strip()
    err = _validate_location(location)
    if err:
        return {"is_error": True, "content": err}
    days = int(arguments.get("days", 7))
    if days not in [3, 7, 10, 15, 30]:
        days = 7
    return _run_qweather(["daily", location, "--days", str(days)])


async def _qweather_hourly(arguments: dict) -> dict:
    location = str(arguments.get("location", "")).strip()
    err = _validate_location(location)
    if err:
        return {"is_error": True, "content": err}
    hours = int(arguments.get("hours", 24))
    if hours not in [24, 72, 168]:
        hours = 24
    return _run_qweather(["hourly", location, "--hours", str(hours)])


def get_qweather_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="qweather_forecast",
            description="查询目的地未来多日天气预报（温度、天气现象、风力、降水概率），用于行程规划中的天气评估",
            category="Web",
            parameters={
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "城市名称或地点ID，如'北京'"},
                    "days": {"type": "integer", "description": "预报天数: 3/7/10/15/30, 默认7"},
                },
                "required": ["location"],
            },
        ),
        ToolSpec(
            name="qweather_now",
            description="查询城市实时天气",
            category="Web",
            parameters={
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "城市名称"},
                },
                "required": ["location"],
            },
        ),
    ]


def get_qweather_handlers() -> dict[str, ToolHandler]:
    return {
        "qweather_forecast": _qweather_forecast,
        "qweather_now": _qweather_now,
    }
```

**Step 2: 注册到 ToolRegistry**

修改 `infrastructure/tools/registry.py`（或者在初始化处注册），把 `qweather` 的 specs 和 handlers 注册进去。

**Step 3: 添加到 travel.yaml 技能列表**

```yaml
# application/builtin_agents/travel.yaml
skills:
  - amap-maps
  - fliggy-travel
  - q-weather    # ★ 新增，替代 amap_get_weather
```

**Step 4: Prompt 中废弃 `amap_get_weather`**

在 `prompting.py` 的工具使用边界 section 中修改天气相关指令，引导 LLM 使用 `qweather_forecast` 而非 `amap_get_weather`：

```
- 天气查询 → 调用 qweather_forecast（和风天气，支持逐日预报+降水概率）",
- 不要使用 amap_get_weather（数据较简，仅作降级备选）
```

---

### 4.3 自驾费用预估工具

#### 4.3.1 设计思路

自驾费用 = **高德过路费** + **油费/电费预估** + **途中消费预估** + **天气风险评估**

- 过路费：`amap_plan_route` 返回的 `tolls` 字段
- 油费/电费：距离 × 单位油耗/电耗单价，**按车型差异化计算**（不再用统一 0.6 元/km）
- 途中餐饮：按 100 元/天/人 × 路程天数
- 天气风险：从 `qweather_forecast` 获取，评估雨天/雾天对自驾的影响

> **★ 为什么不用方案 A（Prompt 内 LLM 计算）**
>
> 0.6 元/km 的统一系数误差可达 ±40%（SUV 0.8-1.0 元/km，电车 0.1 元/km，油价地区差可达 1 元/L）。商用产品中用户自驾 1500km 往返，误差可达 ¥900，足以影响方案选择。LLM 虽然能做乘法，但无法区分用户车型和出发地油价。因此**直接采用方案 B（专用工具）**，参数化车型和油价，保证准确性。

#### 4.3.2 实现：新增 `estimate_drive_cost` 工具

```python
async def _estimate_drive_cost(arguments: dict) -> dict:
    """
    接收 amap_plan_route 返回的结果 + 人数 + 车型，计算自驾总费用。
    车型差异化和油价参数化，保证商用级精度。
    """
    distance_km = float(arguments.get("distance_km", 0))
    toll_yuan = float(arguments.get("toll_yuan", 0))
    people_count = int(arguments.get("people_count", 1))
    days_on_road = int(arguments.get("days_on_road", 1))
    car_type = str(arguments.get("car_type", "sedan")).strip()
    # 油价元/L，默认7.8（全国均值），可按出发地调整
    fuel_price = float(arguments.get("fuel_price", 7.8))

    # ★ 车型油耗系数表（元/km，已含油价换算）
    FUEL_RATE = {
        "sedan":   0.07,   # 轿车 ~7L/100km × 7.8元/L ≈ 0.55元/km
        "suv":     0.09,   # SUV ~9L/100km ≈ 0.70元/km
        "ev":      0.015,  # 电动车 ~15kWh/100km × 0.6元/kWh ≈ 0.09元/km
    }
    rate = FUEL_RATE.get(car_type, FUEL_RATE["sedan"])
    fuel_cost = distance_km * rate * fuel_price / 7.8  # 按实际油价比例缩放

    meal_cost = days_on_road * 100 * people_count  # 途中餐饮

    total = toll_yuan + fuel_cost + meal_cost

    return {
        "is_error": False,
        "content": json.dumps({
            "total_cost": round(total, 0),
            "breakdown": {
                "toll": round(toll_yuan, 0),
                "fuel": round(fuel_cost, 0),
                "meals_on_road": round(meal_cost, 0),
            },
            "distance_km": distance_km,
            "car_type": car_type,
            "fuel_rate_per_km": round(rate * fuel_price / 7.8, 3),
            "note": f"车型={car_type}, 油价={fuel_price}元/L, 油耗系数={rate}L/km; "
                    f"实际费用根据路况和驾驶习惯浮动±10%"
        }, ensure_ascii=False)
    }
```

**ToolSpec 定义**：

```python
ToolSpec(
    name="estimate_drive_cost",
    description="根据高德路线距离/过路费 + 车型 + 人数，计算自驾总费用（含过路费、油费、途中餐饮）",
    category="Web",
    parameters={
        "type": "object",
        "properties": {
            "distance_km": {"type": "number", "description": "单程距离(km)，来自 amap_plan_route"},
            "toll_yuan": {"type": "number", "description": "单程过路费(元)，来自 amap_plan_route"},
            "people_count": {"type": "integer", "description": "出行人数", "default": 1},
            "days_on_road": {"type": "integer", "description": "单程路途天数", "default": 1},
            "car_type": {"type": "string", "enum": ["sedan", "suv", "ev"],
                         "description": "车型: sedan(轿车)/suv(越野)/ev(电动)", "default": "sedan"},
            "fuel_price": {"type": "number", "description": "当地油价(元/L)，默认7.8", "default": 7.8},
        },
        "required": ["distance_km", "toll_yuan"],
    },
)
```

**Prompt 中引导 LLM 调用此工具**（而非自行口算）：

```
自驾费用计算：
- 调用 amap_plan_route 获取距离和过路费后，必须调用 estimate_drive_cost 工具计算自驾总费用
- 不要自行用 0.6元/km 口算油费，必须通过工具获得准确值
- 如果用户未说明车型，默认 sedan（轿车）
- 自驾费用为往返，工具返回的是单程费用，最终展示时 ×2
```

---

### 4.4 多方案 Itinerary 数据模型扩展

#### 4.4.1 当前数据模型

```python
# domain/travel/itinerary/schema.py
class Itinerary:
    id: str
    title: str
    destination: str
    days: list[DayPlan]   # 一套行程
    ...
```

**问题**：只能存一套方案。

#### 4.4.2 扩展方案

> **★ 统一模型策略（消除双轨制）**
>
> 不再维护 `Itinerary` 和 `MultiPlanItinerary` 两套模型。**统一收口到 `MultiPlanItinerary`**，旧 `Itinerary` 视为 `plans.length=1` 的特例。前端、后端、数据库只对接一套模型，避免长期维护成本。

```python
# domain/travel/itinerary/schema.py - 新增枚举 + 字段

class PlanType(str, Enum):
    SIGHTSEEING = "sightseeing"   # 景点打卡型
    BUDGET = "budget"             # 经济实惠型
    SINGLE = "single"             # 单方案（兼容旧数据/降级场景）

class TransportMode(str, Enum):
    FLIGHT = "flight"
    TRAIN = "train"
    DRIVE = "drive"

@dataclass
class CostBreakdown:
    """费用明细分项"""
    transport: float = 0      # 往返交通
    hotel: float = 0          # 住宿
    tickets: float = 0        # 景点门票
    meals: float = 0          # 餐饮
    local_transport: float = 0  # 市内交通
    other: float = 0          # 其他
    total: float = 0          # 总计

@dataclass
class TransportOption:
    """出行方式选项"""
    mode: TransportMode
    duration_hours: float
    cost_yuan: float
    detail: str = ""  # 如"CA1234 08:00-10:30"
    weather_risk: str = ""  # 天气影响评估

@dataclass
class Plan:
    """一套完整的出行方案"""
    plan_type: PlanType
    transport: TransportOption
    hotel_name: str
    hotel_cost_per_night: float
    hotel_reason: str = ""
    days: list[DayPlan]
    cost_breakdown: CostBreakdown
    version: int = 1  # ★ 修改版本号，每次更新递增

@dataclass
class MultiPlanItinerary:
    """统一行程模型（旧 Itinerary 等价于 plans=[单个Plan]）"""
    id: str
    session_id: str
    user_id: str
    destination: str
    start_date: str = ""
    end_date: str = ""
    plans: list[Plan] = field(default_factory=list)
    recommended_plan: PlanType | None = None  # LLM 推荐的方案
    confirmed_plan: PlanType | None = None    # 用户确认的方案
    confirmed_at: str = ""                     # 确认时间
    created_at: str = ""
```

#### 4.4.3 兼容与迁移策略

**核心原则：一套模型，两种用法。**

| 场景 | plans 内容 | confirmed_plan |
|------|-----------|----------------|
| 多方案（新流程） | `[Plan(SIGHTSEEING), Plan(BUDGET)]` | 用户选择后设置 |
| 单方案（旧数据/降级） | `[Plan(SINGLE)]` | 可直接设为 SINGLE |
| 降级场景（LLM 只生成一套） | `[Plan(SIGHTSEEING)]` | 用户确认后设置 |

**数据库迁移**（不新建表，在现有表上扩展）：

```sql
-- 1. itinerary 表新增字段
ALTER TABLE itinerary ADD COLUMN plans_json TEXT;        -- 存储 list[Plan] 的 JSON
ALTER TABLE itinerary ADD COLUMN confirmed_plan VARCHAR(32);
ALTER TABLE itinerary ADD COLUMN confirmed_at VARCHAR(32);
ALTER TABLE itinerary ADD COLUMN recommended_plan VARCHAR(32);

-- 2. 数据迁移：旧记录的 days 字段 → 转为 plans_json 中的单个 Plan
UPDATE itinerary SET plans_json = json_object(
    'plan_type', 'single',
    'days', days,
    ...
) WHERE plans_json IS NULL;

-- 3. 迁移完成后，days 字段保留但不再写入（向后兼容读取）
```

**代码兼容层**：

```python
# domain/travel/itinerary/schema.py
class MultiPlanItinerary:
    # ... 上面的字段 ...

    @property
    def is_multi_plan(self) -> bool:
        """是否为多方案（plans 长度 > 1）"""
        return len(self.plans) > 1

    @property
    def active_plan(self) -> Plan:
        """获取当前生效的方案（已确认的优先，否则取第一个）"""
        if self.confirmed_plan:
            return next(p for p in self.plans if p.plan_type == self.confirmed_plan)
        return self.plans[0]

    @classmethod
    def from_legacy_itinerary(cls, old: Itinerary) -> MultiPlanItinerary:
        """旧 Itinerary → MultiPlanItinerary 转换（plans=[单个Plan]）"""
        return cls(
            id=old.id,
            session_id=old.session_id,
            user_id=old.user_id,
            destination=old.destination,
            plans=[Plan(
                plan_type=PlanType.SINGLE,
                transport=TransportOption(...),  # 从旧数据填充
                hotel_name=old.hotel_name,
                days=old.days,
                cost_breakdown=CostBreakdown(...),
            )],
        )
```

**前端兼容**：前端首页行程列表统一读取 `MultiPlanItinerary`，通过 `is_multi_plan` 属性决定是否显示"多方案"标签。点击进入后，`active_plan` 自动定位到已确认方案或第一个方案。

---

### 4.5 方案选择与确认机制（★ 可撤销，非永久锁定）

> **核心规则修订（原"永久锁定"已废弃）**
>
> ~~一个会话只能确认一套方案，一旦确认永久锁定。~~ → **过于粗暴，商用产品中用户"确认后反悔"是高频场景。**
>
> **新规则：确认后默认锁定，但允许撤销重选（二次确认），且撤销不丢失已有上下文。** 这才符合真实用户行为。

#### 4.5.1 确认与撤销范围

| 操作 | 行为 | 限制 |
|------|------|------|
| 首次确认方案 A | 方案 A 生成概览，所有按钮进入锁定态 | — |
| **撤销确认** | 弹出二次确认弹窗"确定要更换方案吗？" → 确认后所有按钮恢复可点击 | 无次数限制 |
| 重新选择方案 B | 方案 B 生成概览，方案 A 概览标记为"已废弃"但保留可查看 | — |
| 新会话 | 不受影响 | — |

> **关键设计：撤销不丢失上下文**
>
> 撤销确认时，**不**清除 Raw API Results 缓存，**不**重新搜索数据。用户切换方案时，LLM 直接从已有缓存中读取另一套方案的数据（机票/酒店/景点/天气都已在首次生成时搜索过），只需重新生成格式化回复——延迟 < 3s，而非重新搜索的 15-20s。

#### 4.5.2 后端 API 新增端点（含并发幂等）

```
POST /api/session/{session_id}/confirm-plan
Body: { "plan_type": "sightseeing" | "budget", "itinerary_id": "xxx" }

POST /api/session/{session_id}/revoke-confirm
Body: { "itinerary_id": "xxx" }

GET  /api/session/{session_id}/confirm-status
Response: { "confirmed_plan": "sightseeing" | null, "confirmed_at": "...", "itinerary_id": "..." }
```

**确认逻辑（含并发幂等）**：

```python
# api/routes/session.py
from sqlalchemy.orm import with_for_update  # 行级锁

async def confirm_plan(session_id: str, plan_type: str, itinerary_id: str):
    """
    确认方案 —— 并发安全设计
    ★ 关键：数据库唯一约束 + 行级锁，防止双击竞态
    """
    async with db.transaction():
        # 1. 行级锁锁定 session 记录，防止并发请求穿透
        session = await db.execute(
            select(Session)
            .where(Session.id == session_id)
            .with_for_update()  # SELECT ... FOR UPDATE
        )
        session = session.scalar_one_or_none()
        if not session:
            return 404, {"error": "session not found"}

        # 2. 如果已确认同一个方案 → 幂等返回成功（双击防护）
        if session.confirmed_plan == plan_type:
            return 200, {"message": "already confirmed", "plan_type": plan_type}

        # 3. 如果已确认不同方案 → 返回 409，前端引导走撤销流程
        if session.confirmed_plan is not None:
            return 409, {
                "error": "已确认其他方案，如需更换请先撤销",
                "current_confirmed": session.confirmed_plan,
                "hint": "调用 POST /revoke-confirm 撤销后重新选择"
            }

        # 4. 更新确认状态
        session.confirmed_plan = plan_type
        session.confirmed_at = datetime.now().isoformat()
        await db.flush()

    return 200, {"confirmed_plan": plan_type, "itinerary_id": itinerary_id}


async def revoke_confirm(session_id: str, itinerary_id: str):
    """撤销确认 —— 恢复所有按钮为可点击态"""
    async with db.transaction():
        session = await db.execute(
            select(Session).where(Session.id == session_id).with_for_update()
        )
        session = session.scalar_one_or_none()
        if not session or session.confirmed_plan is None:
            return 404, {"error": "无确认记录可撤销"}

        session.confirmed_plan = None
        session.confirmed_at = ""
        await db.flush()

    return 200, {"message": "确认已撤销，可重新选择方案"}
```

**数据库约束（防并发穿透的最后防线）**：

```sql
-- ★ session 表上 confirmed_plan 最多只有一个非空值
-- 通过应用层 + 行级锁保证，但数据库层也加约束兜底
ALTER TABLE session ADD COLUMN confirmed_plan VARCHAR(32) DEFAULT NULL;
ALTER TABLE session ADD COLUMN confirmed_at VARCHAR(32) DEFAULT NULL;

-- 确保同一 session 的确认操作串行化（应用层行锁 + 以下约束兜底）
-- 注意：confirmed_plan 允许 NULL（未确认），但一旦有值则通过应用层行锁保证一致性
```

#### 4.5.3 前端如何感知确认状态

1. **前端 store** 中维护 `sessionConfirmedPlan: 'plan1' | 'plan2' | null`
2. 每次收到 API 返回的 `itinerary_id` 后，调用 `GET /api/session/{session_id}/confirm-status` 查询该 session 是否已确认
3. 如果 `sessionConfirmedPlan !== null`，该会话内**所有消息**的方案按钮渲染为锁定态，但**显示"撤销确认"按钮**
4. 用户点击"撤销确认" → 二次确认弹窗 → 调用 `POST /revoke-confirm` → 前端 `sessionConfirmedPlan = null` → 所有按钮恢复可点击
5. 刷新页面后，`sessionConfirmedPlan` 从后端恢复，状态不丢失

#### 4.5.4 工作流中新方案的操作

- `generate_itinerary_overview` 工具需要扩展，接收 `plan_type` 参数来指定生成哪个方案的概览
- 一个 `MultiPlanItinerary` 包含两套 Plan。用户确认时传 `plan_type`，session 标记为"已确认"
- **如果用户撤销后重新选择另一方案**：旧方案的概览标记为 `status=deprecated`（保留可查看），新方案生成新概览

```python
# domain/travel/tools/travel_tools.py - 扩展
async def _generate_multi_plan_overview(arguments: dict) -> dict:
    """
    新版行程概览生成：支持多方案
    """
    plan_type = str(arguments.get("plan_type", "sightseeing")).strip()
    # ... 解析对话内容中的对应方案 ...
    # ... 保存到 MultiPlanItinerary.plans 中对应 plan_type 的 Plan ...
    # ... 如果该 itinerary 已有其他方案的概览，将其标记为 deprecated ...
```

---

### 4.6 方案修改策略（缓存复用 & 修改分类）

> 这是整个升级中**最容易出 bug 的模块**，必须把修改类型、缓存策略、数据流向彻底捋清楚。

#### 4.6.1 核心架构：模型看的 vs 用户看的

很多人在设计时会把"模型内部数据"和"用户可见成品"混在一起存，导致存储爆炸。正确的分层是：

```
┌──────────────────────────────────────────────────────┐
│  第1层：Raw API Results（模型看的 "JSON"）             │
│  ──────────────────────────────────────               │
│  来源：飞猪/高德/和风天气的原始返回                      │
│  存储位置：TaskRecord.metadata["cached_tool_results"]  │
│  存储策略：按类别覆盖（flight/train/hotel/poi/weather/  │
│           route），每次同类更新替换旧值，不累积         │
│  最大体积：~6类别 × 4000字符 ≈ 24KB/会话，恒定          │
│                                                       │
│  这些数据是 LLM 每次生成方案的"原料"，不是用户看到的成品  │
└──────────────────────────────────────────────────────┘
                         │
                         ▼  LLM 读取原料，生成方案
┌──────────────────────────────────────────────────────┐
│  第2层：Formatted Reply（用户看的 "成品"）              │
│  ──────────────────────────────────────               │
│  来源：LLM 基于 Raw API Results 生成的自然语言回复      │
│  存储位置：session.turns（对话历史，assistant 消息）    │
│  存储策略：追加，每次方案修改产生一条新消息              │
│                                                       │
│  这是用户看到的东西：方案一/方案二、费用明细、推荐原因   │
└──────────────────────────────────────────────────────┘
```

**关键结论**：不需要为每次修改额外存 JSON。Raw API Results 覆盖存储、体积恒定；格式化的方案文本自然存在对话历史中。不存在"反复修改导致存储爆炸"的问题。

#### 4.6.2 修改三层分类（核心逻辑）

用户修改请求可以归为三类，每类的缓存策略和 API 策略不同：

```
                   用户说："xxx"
                        │
                        ▼
        ┌───────────────────────────────┐
        │   LLM 意图分类 + 兜底关键词     │
        │   （详见 4.6.3 识别机制）       │
        └───────────────────────────────┘
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
    ┌──────────┐  ┌──────────┐  ┌──────────┐
    │ 纯局部    │  │ 半局部    │  │ 核心变更  │
    │ (Tier 1) │  │ (Tier 2) │  │ (Tier 3) │
    └──────────┘  └──────────┘  └──────────┘
```

> **注意**：上表中的"识别关键词"列仅作为**人工参考和兜底**，实际分类由 LLM 意图分类器完成（详见 4.6.3）。关键词不参与主路径决策。

##### Tier 1: 纯局部修改（不调任何 API，纯 LLM 重排）

| 用户说法 | 识别关键词 | 缓存动作 | API 动作 |
|----------|-----------|---------|---------|
| "行程太赶了" | 太赶、太紧、太累 | 全部保留 | **不调任何 API** |
| "轻松一点" | 轻松、休闲 | 全部保留 | 不调 API |
| "第一天和第二天换一下" | 换一下、调一下、调整顺序 | 全部保留 | 不调 API |
| "少去一个景点" | 少去、去掉、不要 | 全部保留 | 不调 API |
| "多安排一点吃的" | 多安排、加一点 | 全部保留 | 不调 API（用模型知识补充美食） |

**逻辑**：LLM 从缓存中读取已有的酒店/景点/交通数据，仅重新排列组合，不调任何工具。

##### Tier 2: 半局部修改（部分 API 重新调用，局部缓存失效）

| 用户说法 | 识别关键词 | 缓存动作 | API 动作 |
|----------|-----------|---------|---------|
| "第一个酒店便宜点" | 酒店、便宜、换酒店 | 清除 `hotel` 缓存 | **仅重调** `fliggy_search_hotel` |
| "换个景点" | 换景点、景点不好 | 清除 `poi` 缓存 | **仅重调** `amap_search_poi` |
| "酒店离景点近一点" | 酒店+位置/近 | 清除 `hotel`+`route` | 重调 hotel + plan_route |
| "方案二能坐飞机去吗" | 坐飞机、改飞机、换交通 | 清除 `flight` 缓存（如已有则直接用） | **仅重调** `fliggy_search_flight` |
| "高铁换一个早点的" | 换高铁、早点的 | 清除 `train` 缓存 | **仅重调** `fliggy_search_train` |

**逻辑**：只重新调用被修改的那个类别的 API，其他类别（天气、另一个交通方式、未涉及的酒店等）全部复用缓存。

> ⚠️ **"方案二能坐飞机去吗"的边界说明**：如果首次生成时已经并行搜索了机票和高铁（多方案 Prompt 要求这么做），那 flight 数据已经在缓存中，此时甚至不需要重新调 API，LLM 直接从已有缓存中读取机票数据即可。只有当用户改变了日期等核心参数时，才需要重新搜索。

##### Tier 3: 核心参数变更（全量重新搜索）

| 用户说法 | 识别关键词 | 缓存动作 | API 动作 |
|----------|-----------|---------|---------|
| "改到下周出发" | 改日期、下周、改时间 | **全部清除** | **全部重调** |
| "不去成都了，去重庆" | 不去X了、改去X | **全部清除** | **全部重调** |
| "从北京出发不是上海" | 出发地、从哪、不是X | **全部清除** | **全部重调** |
| "玩5天不是3天" | 5天、多玩、延长 | **全部清除** | **全部重调** |
| "我们4个人" | 人数变了 | **全部清除** | **全部重调** |

**逻辑**：目的地、日期、出发地、天数、人数任何一个变了，所有之前的数据都不可信（酒店日期不对、机票航程不对、景点可能也不对），必须全量重搜。

#### 4.6.3 识别机制：LLM 意图分类（零关键词）

> **商用产品不用关键词/正则做决策。** 项目已有 `TravelIntentClassifier`，直接扩展它。

##### 现有架构

`TravelIntentClassifier.classify()` 的流程：

```
用户消息 → _keyword_classify() 快速匹配 → confidence ≥ 0.85 则返回
                                        → confidence < 0.85 → _llm.complete() LLM 分类
```

已有 `ITINERARY_ADJUST` 意图，LLM 可识别"用户想修改方案"——但**只识别了意图类型，没有识别修改范围**。

##### 扩展方案：意图分类时直接输出修改元数据

**Step 1: 扩展分类器的 System Prompt**

在 `_TRAVEL_CLASSIFY_SYSTEM` 中扩展 `itinerary_adjust` 的输出格式：

```
意图类型列表（扩展 itinerary_adjust）：
- itinerary_adjust: 用户对已生成的方案不满意，想修改。
  当 intent 为 itinerary_adjust 时，额外返回以下字段：
  {
    "intent": "itinerary_adjust",
    "modification_scope": "local_reorder" | "partial_research" | "full_research",
    "affected_categories": ["hotel"] 或 ["flight"] 或 [] 等,
    "target_plan": "plan1" | "plan2" | null,
    ...
  }

  modification_scope 判断规则：
  - "local_reorder": 仅调整行程安排，不需要重新搜索。
    例："太赶了""轻松一点""第一天和第二天换一下""少去一个景点"
  - "partial_research": 需要重新搜索特定类别（酒店/机票/景点等），但其他数据不变。
    例："第一个酒店便宜点"→ hotel / "换个景点"→ poi / "能坐飞机去吗"→ flight
  - "full_research": 核心参数变了（出发地/目的地/日期/天数/人数），所有数据需重搜。
    例："改到下周出发""不去成都了去重庆""玩5天不是3天""我们4个人"

  affected_categories 可选值：hotel, poi, flight, train, route, weather
  如果 modification_scope 为 "full_research"，affected_categories 可为空（代表全部）

  target_plan: 被修改的是哪个方案
  - "plan1": 方案一（景点打卡型）
  - "plan2": 方案二（经济实惠型）
  - null: 无法确定 / 两个都要改
```

**Step 2: 扩展 `TravelIntentResult`**

```python
# domain/travel/intent/travel_classifier.py

@dataclass
class TravelIntentResult:
    # ... 现有字段 ...
    modification_scope: str = ""          # "local_reorder" | "partial_research" | "full_research" | ""
    affected_categories: list[str] = field(default_factory=list)  # ["hotel", "poi"] 等
    target_plan: str = ""                 # "plan1" | "plan2" | ""
```

**Step 3: 替换 `_handle_cache_invalidation`**

```python
# domain/travel/core.py — 改造

def _handle_cache_invalidation(
    self, task: Any, message: str, ops_result: TravelIntentResult | None,
) -> None:
    """
    基于 LLM 意图分类结果决定缓存策略，不再使用关键词匹配。
    """
    if not ops_result or ops_result.intent != TravelIntentType.ITINERARY_ADJUST:
        return
    
    scope = ops_result.modification_scope
    categories = ops_result.affected_categories
    
    if scope == "full_research":
        task.invalidate_cache()  # 全部清除
        logger.info("Cache fully invalidated (LLM classified: full_research)")
    elif scope == "partial_research" and categories:
        for cat in categories:
            task.invalidate_cache(cat)
        logger.info("Cache partial invalidated: %s (LLM classified)", categories)
    elif scope == "local_reorder":
        # 缓存不动，LLM 纯重排
        logger.info("Cache kept (LLM classified: local_reorder)")
```

**Step 4: 兜底**

当 LLM 分类失败或返回异常时，退回到现有的 `_keyword_classify` 结果（它也会返回 `ITINERARY_ADJUST` 意图，只是没有 `modification_scope`）。此时按以下兜底策略：

```python
# 兜底：LLM 分类没有 modification_scope 时
if ops_result.intent == TravelIntentType.ITINERARY_ADJUST and not ops_result.modification_scope:
    # 走原来的关键词逻辑作为兜底（已有代码，不改）
    is_core_change = any(kw in message for kw in self._CORE_CHANGE_KEYWORDS)
    if is_core_change:
        task.invalidate_cache()
    # ... 其余兜底逻辑
```

**效果**：正常情况走 LLM 分类（准确），LLM 挂了走关键词兜底（可用），不会完全不可用。

**Step 5: ★ 分类准确率评测方案（上线门禁）**

> 意图分类的 `modification_scope` 直接决定缓存策略——如果把 "酒店便宜点"（应 `partial_research`）误判为 `local_reorder`，用户会看到**过期酒店价格**，这在旅行产品中是信任崩塌级事故。因此分类准确率**必须在上线前通过量化评测**。

**评测流程**：

1. **构建标注语料集**（`tests/fixtures/intent_classification_dataset.json`）：
   - 至少 **80 条**用户消息，覆盖三个 Tier 的典型表述
   - 每条标注 `expected_scope` + `expected_categories` + `expected_target_plan`
   - 包含 20% 的歧义/边界 case（如"能不能便宜点"——是酒店还是整体？）

```json
[
  {"message": "行程太赶了", "expected_scope": "local_reorder", "expected_categories": [], "expected_target_plan": null},
  {"message": "第一个方案的酒店换便宜的", "expected_scope": "partial_research", "expected_categories": ["hotel"], "expected_target_plan": "plan1"},
  {"message": "不去成都了改去重庆", "expected_scope": "full_research", "expected_categories": [], "expected_target_plan": null},
  {"message": "便宜的那个方案多加一个免费景点", "expected_scope": "partial_research", "expected_categories": ["poi"], "expected_target_plan": "plan2"},
  {"message": "能不能便宜点", "expected_scope": "partial_research", "expected_categories": ["hotel"], "expected_target_plan": null, "note": "歧义case，默认理解为酒店"}
]
```

2. **评测脚本**（`tests/test_intent_classification_accuracy.py`）：

```python
def test_modification_scope_accuracy(classifier, dataset):
    """分类准确率必须 ≥ 0.90 才允许上线"""
    correct = 0
    errors = []
    for item in dataset:
        result = classifier.classify(item["message"])
        if result.modification_scope == item["expected_scope"]:
            correct += 1
        else:
            errors.append({
                "message": item["message"],
                "expected": item["expected_scope"],
                "got": result.modification_scope,
            })
    accuracy = correct / len(dataset)
    assert accuracy >= 0.90, f"分类准确率 {accuracy:.2%} < 90%，不满足上线门禁。错误样本: {errors[:5]}"
```

3. **评测指标与门禁**：

| 指标 | 门禁阈值 | 不达标后果 |
|------|---------|-----------|
| `modification_scope` 准确率 | **≥ 90%** | 阻断上线 |
| `affected_categories` 精确率 | **≥ 85%** | 阻断上线 |
| `target_plan` 准确率 | **≥ 80%** | 警告但不阻断（可反问兜底） |
| `local_reorder` 误判为 `partial_research` | **≤ 5%** | 可接受（多清缓存，代价低） |
| `partial_research` 误判为 `local_reorder` | **≤ 3%** | **阻断上线**（过期数据露出，代价高） |
| `full_research` 误判为其他 | **0%** | **阻断上线**（核心参数变更必须全量重搜） |

4. **持续监控**：上线后每周采样 50 条真实用户消息，人工标注后回归评测，准确率低于 85% 触发告警 + Prompt 调优。

#### 4.6.4 费用预估策略

飞猪只能返回固定价格字段（机票¥XXX、高铁¥XXX、酒店¥XXX/晚）。其他费用需 LLM 预估：

| 费用项 | 数据来源 | 标注 |
|--------|---------|------|
| 往返交通 | 飞猪 API（精确） | 不标注 |
| 住宿 | 飞猪 API × 晚数（精确） | 不标注 |
| 过路费 | 高德 amap_plan_route（精确） | 不标注 |
| 油费 | ★ `estimate_drive_cost` 工具计算（车型差异化，非 0.6元/km 口算） | `[预估]` |
| 景点门票 | LLM 根据模型知识预估（如"故宫 ¥60"） | `[预估，以实际为准]` |
| 餐饮 | LLM 预估：一线(北上广深)¥150/天，二线(成都杭州等)¥120/天，其他¥100/天 | `[预估]` |
| 市内交通 | LLM 预估：¥30-50/天 | `[预估]` |
| 其他 | 购物/纪念品等，LLM 预估 | `[预估]` |

> **★ 餐饮标准统一**：4.1.2 Prompt 中与 4.6.4 本表的标准已对齐——一线 ¥150/天，二线 ¥120/天，其他 ¥100/天。二线城市清单：成都、杭州、武汉、南京、西安、重庆、苏州、天津、长沙、青岛、郑州、沈阳、大连、厦门、宁波、福州。

在 Prompt 的费用表格模板中明确规定标注规则：

```
费用明细表标注规则：
- 来自 API 返回的价格（机票、高铁、酒店单价、过路费）：正常展示，不标注
- LLM 根据知识预估的价格（门票、餐饮、市内交通、油费）：后面标注 [预估]
- 总计行标注 "约 ¥XXX（其中 ¥XXX 为预估值）"
```

#### 4.6.5 多方案指代消解

用户不会说"修改方案一的酒店"，需要 LLM 自行消解指代。

> **★ 关键修正（原文档从自然语言文本提取，已废弃）**
>
> ~~从最近的 assistant 回复中匹配方案特征~~ → 会话变长后方案可能已被修改多次，从文本反向解析会过时。
>
> **正确做法：从结构化的 `MultiPlanItinerary` 对象直接读取当前 plans 状态**，保证指代消解的准确性。

```python
def _build_multi_plan_context(self, session) -> str:
    """
    ★ 从结构化的 MultiPlanItinerary 对象读取当前方案状态，
    而非从对话文本反向解析。保证指代消解始终基于最新数据。
    """
    itinerary = session.get_latest_itinerary()  # MultiPlanItinerary 对象
    if not itinerary or not itinerary.plans:
        return ""  # 无方案历史，不需要注入

    lines = ["当前会话已有以下方案（从结构化数据读取，非文本提取）："]
    for plan in itinerary.plans:
        # 直接从 Plan 对象读取，不依赖对话文本
        transport_desc = f"{plan.transport.mode.value} ¥{plan.transport.cost_yuan:.0f}"
        hotel_desc = f"{plan.hotel_name} ¥{plan.hotel_cost_per_night:.0f}/晚"
        total = plan.cost_breakdown.total
        version_tag = f" v{plan.version}" if plan.version > 1 else ""
        lines.append(
            f"  【{plan.plan_type.value}】{transport_desc} + {hotel_desc} "
            f"→ 总价约 ¥{total:.0f}{version_tag}"
        )

    if itinerary.confirmed_plan:
        lines.append(f"  ⚠️ 用户已确认方案: {itinerary.confirmed_plan.value}")

    return "\n".join(lines)
```

同时在 Prompt 中加入指代消解规则：

```
## 方案指代消解规则
- "第一个"、"方案一"、"打卡的"、"贵的那套" → 方案一（景点打卡型 sightseeing）
- "第二个"、"方案二"、"经济的"、"便宜的那套" → 方案二（经济实惠型 budget）
- 无明确指代（如仅说"酒店便宜点"）→ 结合上下文判断，不确定时反问

注意：方案摘要从结构化数据注入（见 Context 中的"当前会话已有以下方案"），
      不要从对话正文中自行提取方案信息，以结构化数据为准。
```

#### 4.6.6 修改后的输出规范

修改后 LLM 必须重新输出版本号标记和全量方案，格式如下：

```
🔄 方案一已更新（v2）

### 修改内容
- 酒店：XX酒店 → YY酒店（¥350/晚 → ¥220/晚）
- 总价：¥2100 → ¥1890

### 更新后的方案一（景点打卡型）
（完整重新输出方案一的每日行程 + 费用明细）

---

### 当前两套方案对比

| 方案 | 出行 | 酒店 | 总价 | 状态 |
|------|------|------|------|------|
| 方案一·打卡型 v2 | ✈️ ¥780 | YY酒店 ¥220/晚 | ¥1890 | 已更新 |
| 方案二·经济型 v1 | 🚄 ¥550 | 如家 ¥150/晚 | ¥1100 | 未变 |

您更倾向于哪个方案？
```

---

## 5. 前端改造方案

### 5.1 双按钮 UI 设计

#### 5.1.1 按钮位置（推荐）

**位置：消息气泡下方，两个按钮并排**

```
┌─────────────────────────────────────────────┐
│  [AI 回复：方案一 + 方案二 + 对比表]          │
│                                              │
│  ┌────────────────┐  ┌────────────────────┐  │
│  │ ✨ 生成方案一    │  │ 💰 生成方案二       │  │
│  │ 行程概览        │  │ 行程概览           │  │
│  │ (景点打卡型)    │  │ (经济实惠型)       │  │
│  └────────────────┘  └────────────────────┘  │
│                                              │
│  或者：（两个按钮确认后合并为一个跳转卡片）    │
│                                              │
│  ┌──────────────────────────────────────────┐│
│  │ 🗺️  进入完整行程规划  →                  ││
│  └──────────────────────────────────────────┘│
└─────────────────────────────────────────────┘
```

**推荐理由**：
- 两个按钮并排，视觉上对称，用户一眼看出这是"二选一"
- 每个按钮有明确的标签（方案一/方案二），降低认知成本
- 按钮带有简短副标题（如"景点打卡型"、"经济实惠型"），帮助用户回忆
- 与当前单按钮设计保持风格一致，改动最小

#### 5.1.2 按钮状态流转（★ 可撤销，非永久锁定）

```
【初始态】该会话尚未确认任何方案：
    [为方案一生成概览] [为方案二生成概览]    ← 两个都可点击

    ↓ (用户点击方案一)

【过渡态】正在生成中：
    [⏳ 生成中...]     [请等待...]           ← 方案二也临时禁用，防止重复操作

    ↓ (生成完成，后端标记 session 已确认)

【已确认态】该会话已确认方案一，按钮锁定但可撤销：
    [✅ 已生成概览]    [已选择方案一]         ← 两个都灰色不可点击
    [🗺️ 进入完整行程规划 →]                  ← 仅方案一有跳转卡片
    [↩️ 撤销确认，重新选择]                  ← ★ 新增：撤销按钮

    ↓ (用户点击"撤销确认")

【撤销确认弹窗】
    "确定要更换方案吗？当前方案的概览将保留但标记为已废弃"
    [取消]  [确认撤销]

    ↓ (用户确认撤销)

【恢复初始态】所有按钮恢复可点击：
    [为方案一生成概览] [为方案二生成概览]    ← 重新可点击（复用缓存，无需重新搜索）

    ↓ (用户继续在这个会话里聊，如果再出现新的方案)

【后续消息】如果 session 已确认：
    [已确认方案X] [↩️ 撤销确认]             ← 统一提示 + 撤销入口
    如果未确认：正常渲染双按钮
```

**关键修正（原"永久锁定"已废弃）**：
- ~~一旦非 null，该会话内所有方案按钮全部 render 为 disabled，无法更改~~
- **新策略**：确认后按钮 disabled，但显示"撤销确认"入口。撤销后恢复可点击，且**不重新搜索数据**（复用 Raw API Results 缓存）

#### 5.1.3 前端实现要点（★ 结构化锚点解析，非正则扫描）

修改 `frontend/src/components/ChatWindow.tsx` 中的检测和按钮渲染逻辑：

> **★ 关键修正（原正则检测已废弃）**
>
> ~~用 `/方案一|景点打卡型/` 正则扫描正文~~ → LLM 措辞千变万化，正则极不可靠。
>
> **新策略**：解析 LLM 回复末尾的结构化锚点 `<!--MULTI_PLAN:...-->`（见 4.1.2 锚点协议），前端通过精确正则提取锚点，而非扫描正文。

```tsx
// ★ 统一从 useSessionStore 获取状态（文件名统一为 useSessionStore.ts）
const sessionConfirmedPlan = useSessionStore((s) => s.sessionConfirmedPlan)
const hasAnyConfirmed = sessionConfirmedPlan !== null

// ★ 结构化锚点解析（替代正则扫描正文）
const MULTI_PLAN_ANCHOR_RE = /<!--MULTI_PLAN:(.*?)-->/

interface PlanMeta {
  type: string       // "sightseeing" | "budget"
  version: string    // "v1" | "v2" ...
}

interface MultiPlanAnchor {
  plans: Record<string, PlanMeta>  // { plan1: {...}, plan2: {...} }
}

function parseMultiPlanAnchor(content: string): MultiPlanAnchor | null {
  const m = content.match(MULTI_PLAN_ANCHOR_RE)
  if (!m) return null
  const plans: Record<string, PlanMeta> = {}
  for (const part of m[1].split(',')) {
    const [key, val] = part.split('=')
    if (!key || !val) continue
    const [type, version] = val.split(':')
    plans[key] = { type, version: version || 'v1' }
  }
  return Object.keys(plans).length > 0 ? { plans } : null
}

// 按钮渲染（在消息气泡下方）
// ★ 关键：通过锚点解析判断是否为多方案回复，hasAnyConfirmed 是 session 级别
{msg.role === 'assistant' && !msg.isStreaming && (() => {
  const anchor = parseMultiPlanAnchor(msg.content)
  if (!anchor) return null  // 无锚点 → 非多方案消息，不渲染按钮

  return (
    <div className="mt-3 flex gap-3">
      {hasAnyConfirmed ? (
        <>
          {/* 会话已确认 → 显示锁定态 + 撤销入口 */}
          <div className="text-xs text-slate-400 bg-slate-50 rounded-xl px-4 py-2.5 border border-slate-200">
            {sessionConfirmedPlan === 'plan1'
              ? '✅ 方案一（景点打卡型）已确认，行程概览已生成'
              : '方案一（景点打卡型）——本次会话已选择方案二'}
          </div>
          {/* ★ 新增：撤销确认按钮 */}
          <button
            onClick={() => handleRevokeConfirm()}
            className="text-xs text-amber-600 hover:text-amber-700 underline"
          >
            ↩️ 撤销确认，重新选择
          </button>
        </>
      ) : (
        <>
          {/* 未确认 → 正常渲染双按钮 */}
          {anchor.plans.plan1 && (
            <button onClick={() => handleConfirm('plan1')} className="...">
              ✨ 为方案一生成概览
              <span className="text-xs">({anchor.plans.plan1.type})</span>
            </button>
          )}
          {anchor.plans.plan2 && (
            <button onClick={() => handleConfirm('plan2')} className="...">
              💰 为方案二生成概览
              <span className="text-xs">({anchor.plans.plan2.type})</span>
          )}
        </>
      )}
    </div>
  )
})()}
```

#### 5.1.4 方案确认后的状态管理（★ 统一 useSessionStore.ts）

> **文件名统一说明**：原文档在 5.1.4 写 `useSessionStore.ts`，在 6.2 又写 `useItineraryStore.ts`，造成歧义。**统一为 `useSessionStore.ts`**，所有会话级状态（含方案确认状态）归此 store 管理。

使用 Zustand store 管理确认状态（session 维度，非单条消息维度）：

```typescript
// frontend/src/hooks/useSessionStore.ts - 扩展（统一文件名）
interface SessionState {
  // ... 现有字段
  sessionConfirmedPlan: 'plan1' | 'plan2' | null  // ★ 会话级，非消息级
  isConfirming: boolean
  confirmPlan: (planType: 'plan1' | 'plan2', itineraryId: string) => Promise<void>
  revokeConfirm: (itineraryId: string) => Promise<void>  // ★ 新增：撤销确认
  syncConfirmStatus: (sessionId: string) => Promise<void>  // 从后端恢复状态
}

// 确认方案
confirmPlan: async (planType, itineraryId) => {
  set({ isConfirming: true })
  try {
    const res = await fetch(`/api/session/${sessionId}/confirm-plan`, {
      method: 'POST',
      body: JSON.stringify({ plan_type: planType, itinerary_id: itineraryId })
    })
    if (res.status === 409) {
      // 已确认其他方案 → 同步状态
      await get().syncConfirmStatus(sessionId)
      return
    }
    set({ sessionConfirmedPlan: planType })
  } finally {
    set({ isConfirming: false })
  }
}

// ★ 新增：撤销确认
revokeConfirm: async (itineraryId) => {
  const res = await fetch(`/api/session/${sessionId}/revoke-confirm`, {
    method: 'POST',
    body: JSON.stringify({ itinerary_id: itineraryId })
  })
  if (res.ok) {
    set({ sessionConfirmedPlan: null })
  }
}

// 初始化 & 切换会话时调用
syncConfirmStatus: async (sessionId: string) => {
  const res = await fetch(`/api/session/${sessionId}/confirm-status`)
  const data = await res.json()
  set({ sessionConfirmedPlan: data.confirmed_plan ?? null })
}
```

---

### 5.2 方案卡片展示

#### 5.2.1 出行方式对比卡片（新增组件）

在 AI 生成方案后，可以抽取对比表渲染为更美观的卡片：

```tsx
// frontend/src/components/TransportCompareCard.tsx
function TransportCompareCard({ data }: { data: TransportCompareData }) {
  return (
    <div className="bg-gradient-to-r from-slate-50 to-sky-50 rounded-2xl p-4 border border-slate-200">
      <h4 className="text-sm font-semibold text-slate-700 mb-3">🚗 出行方式对比</h4>
      <div className="grid grid-cols-3 gap-3">
        <TransportCard mode="flight" data={data.flight} />
        <TransportCard mode="train" data={data.train} />
        <TransportCard mode="drive" data={data.drive} />
      </div>
    </div>
  )
}
```

### 5.3 按钮锁定与禁用逻辑（★ 可撤销）

```
规则（按优先级）:
  1. 全局检查：渲染任何方案按钮前，先查 sessionConfirmedPlan
     → 如果 sessionConfirmedPlan !== null → 渲染为禁用态 + 撤销入口

  2. 初始状态（sessionConfirmedPlan === null）：
     → 两个按钮都可点击

  3. 用户点击任一按钮：
     → 两个按钮立刻进入 disabled 状态（防止重复点击）
     → 被点击的按钮：显示 "⏳ 生成中..."
     → 另一个按钮：显示 "请等待..."（半透明）

  4. 生成完成，后端返回 itinerary_id + session 已确认：
     → 前端设置 sessionConfirmedPlan = 'plan1' | 'plan2'
     → 此后该会话内【所有消息】的方案按钮渲染为禁用态 + 撤销入口：
       · 已确认方案：按钮变成 "✅ 已生成概览"（不可点击）+ 跳转卡片
       · 未确认方案：按钮变成 "已选择方案X"（不可点击）
       · ★ 显示 "↩️ 撤销确认，重新选择" 按钮（可点击）

  5. ★ 用户点击"撤销确认"：
     → 弹出二次确认弹窗
     → 确认后调用 POST /revoke-confirm
     → sessionConfirmedPlan = null
     → 所有按钮恢复可点击（复用缓存，不重新搜索）

  6. 刷新页面后：
     → 从后端 GET /api/session/{id}/confirm-status 恢复 sessionConfirmedPlan
     → 状态不丢失

  7. 如果后端 /confirm 返回 409（已确认其他方案）：
     → 前端同步设置 sessionConfirmedPlan，按钮进入禁用态 + 撤销入口
```

> **store 设计已统一到 `useSessionStore.ts`，见 5.1.4**

---

## 6. 实施路线图

### Phase 1: 核心改造（预计 3-5 天）

| 序号 | 任务 | 涉及文件 | 优先级 |
|------|------|----------|--------|
| 1.1 | 和风天气 Skill 接入（含输入校验 + KEY 校验） | `infrastructure/tools/adapters/qweather.py`(新建), `travel.yaml`, ToolRegistry | 🔴 P0 |
| 1.2 | Prompt 重构：新增 Multi-Plan section + ★结构化锚点注入指令 | `domain/travel/prompting.py` | 🔴 P0 |
| 1.3 | Prompt 重构：更新 Execution Rules | `domain/travel/prompting.py` | 🔴 P0 |
| 1.4 | Prompt 重构：多方案修改规则 + 指代消解规则（从结构化对象读取） | `domain/travel/prompting.py` | 🔴 P0 |
| 1.5 | ★ 自驾费用工具 `estimate_drive_cost`（车型差异化，非 Prompt 口算） | `infrastructure/tools/adapters/drive_cost.py`(新建), ToolRegistry | 🔴 P0 |
| 1.6 | `generate_itinerary_overview` 支持 plan_type | `domain/travel/tools/travel_tools.py` | 🔴 P0 |

### Phase 2: 前端改造（预计 2-3 天）

| 序号 | 任务 | 涉及文件 | 优先级 |
|------|------|----------|--------|
| 2.1 | 双按钮 UI 组件 | `frontend/src/components/ChatWindow.tsx` | 🔴 P0 |
| 2.2 | ★ 按钮状态管理（统一 `useSessionStore.ts`，非 useItineraryStore） | `frontend/src/hooks/useSessionStore.ts` | 🔴 P0 |
| 2.3 | ★ 结构化锚点解析器 `parseMultiPlanAnchor`（替代正则扫描正文） | `frontend/src/components/ChatWindow.tsx` | 🔴 P0 |
| 2.4 | ★ 按钮锁定/禁用逻辑（可撤销：确认后显示"撤销确认"入口） | `frontend/src/components/ChatWindow.tsx` | 🔴 P0 |
| 2.5 | 确认后的行程跳转卡片 | `frontend/src/components/AgentActionCard.tsx` | 🟡 P1 |
| 2.6 | 出行方式对比卡片组件（可选） | `frontend/src/components/TransportCompareCard.tsx`(新建) | 🟢 P2 |
| 2.7 | `sessionConfirmedPlan` 持久化 & 跨消息同步 + 撤销确认 API 调用 | `frontend/src/hooks/useSessionStore.ts` | 🔴 P0 |

### Phase 3: 数据模型 & 后端 API（预计 2-3 天）

| 序号 | 任务 | 涉及文件 | 优先级 |
|------|------|----------|--------|
| 3.1 | ★ MultiPlanItinerary 统一模型（旧 Itinerary 作为 plans.length=1 特例） | `domain/travel/itinerary/schema.py` | 🔴 P0 |
| 3.2 | ★ 数据库迁移（扩展 itinerary 表 + `from_legacy_itinerary` 兼容层） | `infrastructure/persistence/` | 🔴 P0 |
| 3.3 | ★ 方案确认 API `POST /confirm-plan` + ★撤销 API `POST /revoke-confirm` + 查询 `GET /confirm-status`（含行级锁 + 幂等） | `api/routes/` | 🔴 P0 |
| 3.4 | ★ 数据库并发安全：session 表行级锁 + 唯一约束兜底 | `infrastructure/persistence/` | 🔴 P0 |
| 3.5 | 行程解析器支持多方案 | `domain/travel/itinerary/parser.py` | 🟡 P1 |
| 3.6 | TravelAgent 多方案 actions 提取 | `domain/travel/agent.py` | 🔴 P0 |

### Phase 4: 意图分类增强（预计 2-3 天）

| 序号 | 任务 | 涉及文件 | 优先级 |
|------|------|----------|--------|
| 4.1 | 扩展分类器 System Prompt：`itinerary_adjust` 输出 `modification_scope` + `affected_categories` + `target_plan` | `domain/travel/intent/travel_classifier.py` | 🔴 P0 |
| 4.2 | `TravelIntentResult` 新增 `modification_scope`/`affected_categories`/`target_plan` 字段 | `domain/travel/intent/travel_classifier.py` | 🔴 P0 |
| 4.3 | 改造 `_handle_cache_invalidation`：从关键词匹配 → 读取 LLM 分类结果 | `domain/travel/core.py` | 🔴 P0 |
| 4.4 | 保留关键词兜底（LLM 分类失败时降级） | `domain/travel/core.py` | 🟡 P1 |
| 4.5 | ★ 构建标注语料集（≥80 条，覆盖三 Tier + 歧义 case） | `tests/fixtures/intent_classification_dataset.json` | 🔴 P0 |
| 4.6 | ★ 分类准确率评测脚本 + 上线门禁（scope ≥ 90%，partial→local 误判 ≤ 3%） | `tests/test_intent_classification_accuracy.py` | 🔴 P0 |

### Phase 5: 测试 & 优化（预计 3-4 天）

| 序号 | 任务 | 优先级 |
|------|------|--------|
| 5.1 | 端到端测试：完整对话流程（生成→确认→撤销→重选→修改） | 🔴 P0 |
| 5.2 | ★ 锚点解析测试：LLM 输出含/不含锚点、单方案降级锚点、版本号锚点 | 🔴 P0 |
| 5.3 | ★ 并发测试：双击确认按钮、同时确认两个方案（行锁 + 唯一约束验证） | 🔴 P0 |
| 5.4 | ★ 分类器单元测试：80+ 条语料，scope/categories/plan 三维度准确率 | 🔴 P0 |
| 5.5 | ★ 缓存失效边界测试：Tier 1/2/3 各 10+ case，验证缓存清除范围正确 | 🔴 P0 |
| 5.6 | 边界情况测试：单方案降级、无自驾路线、飞猪返回空 | 🟡 P1 |
| 5.7 | ★ 降级路径测试：Token 超限降级单方案、LLM 分类失败走关键词兜底 | 🟡 P1 |
| 5.8 | UI/UX 走查 | 🟡 P1 |
| 5.9 | 对话质量评测（方案对比合理性） | 🟢 P2 |
| 5.10 | ★ 性能 SLA 测试：响应时间、方案生成成功率（见 7.8 SLA 定义） | 🟡 P1 |

---

## 7. 风险评估与应对

### 7.1 LLM 输出格式不稳定

**风险**：Prompt 要求输出两套方案 + 对比表，LLM 可能漏掉某个方案，或格式混乱。

**应对**：
- 在 `_build_execution_rules_section()` 中加入**结构化验证提示**："如果某类工具搜索失败（如自驾路线无结果），用你的知识补充估算值并标注【预估】"
- ★ 在 `_finalize_chat()` 后增加**结构化锚点检测**：检测回复末尾是否存在 `<!--MULTI_PLAN:...-->` 锚点，缺失则触发重试（不再用正则扫描正文匹配"方案一"关键词）
- 提供 fallback：如果 LLM 确实无法生成两套，降级为单方案模式 + 注入单方案锚点 `<!--MULTI_PLAN:plan1=sightseeing-->` + 提示用户

### 7.2 飞猪/高德 API 返回空

**风险**：搜索不到机票、酒店等情况。

**应对**（Prompt 中已有工具容错规则，需加强）：
```
## 工具容错（强化版）
- 机票搜索失败但有高铁数据 → 方案一用高铁，方案二用高铁（标注"暂无可选航班"）
- 酒店搜索失败 → 用你的知识推荐酒店并标注【基于本地知识，建议自行核实价格】
- 天气查询失败 → 标注"建议出行前查看天气预报"
- 自驾路线无法计算 → 用直线距离 ×1.3 估算，标注【距离为估算值】
- 至少保证有一套方案可用，不能因为部分数据缺失就放弃整个规划
```

### 7.3 LLM 分类延迟 & 误判

**风险**：扩展后的意图分类需要额外输出 `modification_scope`/`affected_categories`/`target_plan`，增加 LLM 调用 token 和延迟，小概率输出格式错误。

**应对**：
- **延迟可控**：扩展字段只增加约 50 token 输出，LLM 分类本身已经存在（现有流程每轮都会调），不是新增一轮调用
- **格式容错**：`_extract_json` 已有容错逻辑；新增字段全部有默认值（空字符串/空列表），LLM 没输出也不会崩
- **兜底路径**：如果 `modification_scope` 为空，走原有的关键词匹配兜底（`_CORE_CHANGE_KEYWORDS`），见 Step 4
- **设计原则**：宁可多清缓存多调一次 API，也不让用户看到过期数据。误判为 `full_research` 的代价只是一次额外 API 调用（~3秒），用户几乎无感知

### 7.4 飞猪酒店仅返回单一价格

**风险**：飞猪 `search-hotel` 可能只返回一个推荐酒店的价格，无法提供多个价位选项。

**应对**：
- 多方案 Prompt 要求 LLM 调用 `fliggy_search_hotel` 时获取尽可能多的结果
- 如果确实只有一个酒店价格 → 方案一用飞猪价格 + LLM 推荐另一个高端酒店（标注"价格需自行核实"），方案二用飞猪价格 + LLM 推荐一个经济型替代
- 酒店价格通常是旅费的大头，必须有 API 数据作为锚点，LLM 补充部分标注清楚即可

### 7.5 Token 消耗显著增加

**风险**：两套方案的输出长度是单方案的 2-2.5 倍，成本翻倍。

**应对**：
- 控制细节粒度：方案对比表用表格（token 高效），行程描述用精炼语言
- ★ **Token 预算与降级阈值**：
  - 多方案回复 token 上限：**4000 token**（含对比表 + 两套方案 + 费用明细）
  - 如果 LLM 输出接近上限（> 3500 token），Prompt 指示精简行程描述（每日景点用逗号分隔，不展开介绍）
  - 如果用户明确说"只要便宜的方案" / "只要一个方案" → 跳过双方案生成，只生成方案二（budget），注入单方案锚点
  - 如果连续 2 轮多方案生成均超 token 上限 → 自动降级为单方案模式，前端检测单方案锚点 `<!--MULTI_PLAN:plan1=sightseeing-->` 后只渲染单按钮
- 监控 token 用量，设置预算告警：单会话 token > 8000 时告警

### 7.6 用户不说"方案一/方案二"

**风险**：用户说"那个便宜的方案再加个景点吧"，需要正确映射到方案二。

**应对**：
- ★ 在 Prompt 的 Context 中注入方案特征摘要（见 4.6.5）——**从结构化 `MultiPlanItinerary` 对象读取**，而非从对话文本提取，保证数据不过时
- 用关键词匹配做第一步映射（"便宜" → budget, "贵" → sightseeing）
- 如果无法映射，反问用户确认

### 7.7 现有单方案模式的兼容

**风险**：新 Prompt 可能导致当前的"确认→生成概览→跳转"流程断裂。

**应对**：
- ★ 保留原有单方案的检测逻辑作为 fallback
- ★ 前端通过结构化锚点判断方案数量：锚点含 plan1+plan2 → 多方案双按钮；仅含 plan1 → 单方案单按钮；无锚点 → 走旧逻辑
- ★ 数据模型统一：旧 `Itinerary` 通过 `from_legacy_itinerary()` 转为 `MultiPlanItinerary`（plans.length=1），前端无需区分新旧数据
- 渐进式上线：先灰度一部分请求走多方案 Prompt

### 7.8 ★ 性能 SLA 定义（商用产品必备）

> 原文档缺少性能 SLA 定义，商用产品必须有可量化的服务质量目标。

| 指标 | SLA 目标 | 测量方式 | 不达标处理 |
|------|---------|---------|-----------|
| 多方案首次生成响应时间 | **P95 ≤ 25s** | 从用户发送到 LLM 回复完成 | 超时则降级单方案 |
| 方案修改（Tier 1 纯局部）响应时间 | **P95 ≤ 8s** | 不调 API，纯 LLM 重排 | — |
| 方案修改（Tier 2 半局部）响应时间 | **P95 ≤ 15s** | 部分重调 API | — |
| 方案修改（Tier 3 全量重搜）响应时间 | **P95 ≤ 30s** | 全量重调 API | — |
| 撤销确认 + 重选响应时间 | **P95 ≤ 5s** | 复用缓存，不重搜 | — |
| 方案生成成功率 | **≥ 95%** | 成功生成 ≥ 1 套方案 / 总请求 | 失败则降级单方案 + 提示 |
| 结构化锚点注入成功率 | **≥ 98%** | 锚点存在 / 多方案回复总数 | 缺失则触发重试 1 次 |
| 意图分类准确率 | **≥ 90%** | 采样人工标注评测 | 低于 85% 触发 Prompt 调优 |
| 和风天气 API 可用率 | **≥ 99%** | 成功调用 / 总调用 | 失败则降级标注"建议出行前查看天气" |
| 并发确认无穿透 | **100%** | 同一 session 不会产生两个确认 | 行锁 + 唯一约束保证 |

---

## 8. 总结

### 8.1 你的思路评价

你的想法**方向完全正确**，这正是从"玩具"到"商用产品"的关键一跃：

1. **三套出行方式对比** → ✅ 数据驱动决策，用户不用自己去携程/12306 分别查
2. **两种方案风格** → ✅ 覆盖两种核心用户画像（体验派 vs 省钱派）
3. **真实数据** → ✅ 飞猪+高德+和风天气，三大数据源全部结构化利用
4. **自然语言修改** → ✅ 这才是 AI 产品的差异化优势，不是填表单
5. **双按钮 + 锁定机制** → ✅ 符合用户心智模型，且防止误操作

### 8.2 核心改动清单

| 层 | 改动量 | 关键文件 |
|-----|--------|----------|
| Prompt | **大改** | `domain/travel/prompting.py` — 新增 Multi-Plan section + ★结构化锚点注入 |
| Skill | **新增** | `infrastructure/tools/adapters/qweather.py` — 和风天气接入（含输入校验） |
| Skill | **新增** | `infrastructure/tools/adapters/drive_cost.py` — ★自驾费用工具（车型差异化） |
| 数据模型 | **统一** | `domain/travel/itinerary/schema.py` — ★统一为 MultiPlanItinerary（旧 Itinerary 兼容） |
| 后端 API | **新增** | 确认 `/confirm-plan` + ★撤销 `/revoke-confirm` + 查询 `/confirm-status`（行锁+幂等） |
| 前端 UI | **中改** | `ChatWindow.tsx` — 双按钮 + ★锚点解析 + ★可撤销锁定 |
| 前端 Store | **扩展** | `useSessionStore.ts` — confirmedPlan 状态 + revokeConfirm 方法 |
| 意图分类 | **扩展** | `travel_classifier.py` — modification_scope + ★评测门禁（≥90%） |

### 8.3 一句话总结

> 本次升级的核心是：**把"LLM 口嗨出一个方案"变成"三数据源 × 两方案风格 = 结构化多方案对比"，让用户真正能够数据驱动地做旅行决策，而不是只能接受 AI 给的一个答案。**

---

*文档结束。请审阅后提出修改意见，确认后进入 Phase 1 实施。*

---

## 附录 A: v1.1 修复记录

> 本附录记录 v1.0 → v1.1 的所有修复项，供下一阶段实施 AI 参考。

### A.1 修复的 4 项硬伤（阻断实施级）

| 编号 | 硬伤 | 修复方案 | 修复位置 |
|------|------|---------|---------|
| H1 | 会话级永久锁定是"产品自残" | 改为可撤销策略：确认后显示"撤销确认"入口，撤销不丢失缓存，复用数据重新生成 | 4.5, 5.1.2, 5.3 |
| H2 | 前端正则检测多方案极脆弱 | 引入结构化锚点 `<!--MULTI_PLAN:...-->`，前端解析锚点而非扫描正文 | 4.1.2, 5.1.3, 7.1 |
| H3 | 意图分类准确率零验证 | 新增 Step 5 评测方案：80+条标注语料，scope ≥ 90% 上线门禁，partial→local 误判 ≤ 3% | 4.6.3 Step 5, Phase 4.5-4.6, Phase 5.4 |
| H4 | MultiPlanItinerary 与 Itinerary 双轨制 | 统一为 MultiPlanItinerary 单模型，旧 Itinerary 作为 plans.length=1 特例，含数据库迁移 + 兼容层 | 4.4.2, 4.4.3 |

### A.2 修复的 5 项重要问题

| 编号 | 问题 | 修复方案 | 修复位置 |
|------|------|---------|---------|
| P5 | 自驾费用 0.6 元/km 过于粗糙 | 直接采用方案 B 工具 `estimate_drive_cost`，车型差异化油耗系数（sedan/suv/ev）+ 油价参数化 | 4.3 |
| P6 | 指代消解从自然语言文本提取会过时 | 改为从结构化 `MultiPlanItinerary` 对象直接读取 plans 状态 | 4.6.5 |
| P7 | 并发与幂等性缺失 | API 增加 `SELECT FOR UPDATE` 行级锁 + 数据库约束兜底 + 幂等返回 | 4.5.2 |
| P8 | Token 翻倍应对停留在口号 | 补充具体阈值：4000 token 上限，3500 触发精简，连续超限自动降级单方案 | 7.5 |
| P9 | 测试章节过于宏观 | 细化为 10 项可执行测试任务，含锚点解析、并发、分类器、缓存边界、降级路径 | Phase 5 |

### A.3 修复的 5 项文档质量问题

| 编号 | 问题 | 修复 |
|------|------|------|
| Q1 | subprocess 传 location 未做输入校验 | 新增 `_validate_location()` + 正则白名单 |
| Q2 | QWEATHER_KEY 仅调用时报错 | 新增 `_check_qweather_key()` 函数 |
| Q3 | 餐饮标准矛盾（4.1.2 写 120，4.6.4 写 100） | 统一为一线 150/二线 120/其他 100，附二线城市清单 |
| Q4 | store 文件名不一致（useSessionStore vs useItineraryStore） | 统一为 `useSessionStore.ts` |
| Q5 | 缺性能 SLA 定义 | 新增 7.8 SLA 定义（10 项量化指标） |
