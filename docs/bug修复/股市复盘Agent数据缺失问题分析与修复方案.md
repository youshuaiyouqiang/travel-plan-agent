# 股市复盘 Agent 数据缺失问题分析与修复方案

> **文档版本：** v2.6.1，2026-08-02
> **变更说明：**
> - v2.6.1 自检修正：修正 7 处问题（维度 2/3 字段名错、E.6 矛盾、E.5 矛盾规则不全、E.9 工作量低估、E.8 第 3 步废弃错误、新增 E.10 周期段识别）
> - v2.6 重大重构：Task E 从"单一指标分位数"扩展为"6 维度情绪观察框架"
>   （高度/广度/强度/韧性/真实度/持续性），解决单维度（涨停数）判情绪的刻舟求剑问题；
>   代码不做"阶段判定"，但做"维度分类"（如强度=高/中/低），AI 基于分类组合受约束推理
> - v2.2 修正 Task E 设计方向：代码不做阶段判定（已废弃，因 LLM 自判易刻舟求剑）
> - v2.1 修正 Task E 算法（绝对阈值→相对分位数，已废弃）
> - v2.0 修正 v1.0 的 6 处技术错误、2 处架构问题、3 处遗漏
> **作者：** AI 开发助手
> **关联文档：**
> - [开发计划](../superpowers/plans/2026-07-26-stock-review-agent.md)
> - [SKILL 方法论](../../infrastructure/skills/builtin/stock-review/SKILL.md)
> - [AGENTS.md 规范 v3.2](../../AGENTS.md)
> **影响范围：** `infrastructure/stock/*_fetcher.py`、`infrastructure/stock/sqlite_data_source.py`、`application/stock/*`、`domain/stock/ports.py`、`domain/stock/models.py`、`domain/stock/heuristics.py`

---

## 一、问题背景

### 1.1 现象

用户在测试股市复盘 Agent 时，发现生成的复盘文中以下 4 大块内容全部标注"数据缺失"：

1. **两市成交额 / 量能环比**（无法判断放量缩量）
2. **情绪多日趋势曲线**（无法判断情绪所处阶段）
3. **板块轮动 / 抗跌板块 / 板块高潮分布**
4. **强势修复龙头候选、观察池、庄股/抱团股识别**

复盘文输出（[data/yunhe.db](../../data/yunhe.db) `review_reports` 表实测）：

```
# 今日 A股周期复盘（数据缺失）
## 一、周期定位
数据缺失，今日无可用截面/趋势数据，不进行判断。

## 二、大盘与量能
数据缺失，今日无可用截面/趋势...
```

### 1.2 触发链路

```
用户点击"生成复盘"
  ↓
review_service.generate_review(user_id, trade_date)
  ↓
data_source.get_market_snapshot(date)           ← 取到 None（emotion_daily 表 0 行）
data_source.get_emotion_indicators_trend(10)    ← 取到 []（表空）
data_source.get_watchlist()                     ← 取到 []（表空）
data_source.get_signal_stocks(date)             ← 端口直接 return []
data_source.get_sector_rotation(date)           ← 取到 []（表空）
  ↓
_build_user_prompt 收到全空数据 → 标注"数据缺失"
  ↓
LLM 输出"数据缺失"占位文 → 存档为 status="no_data"
```

### 1.3 影响

- 复盘文完全无价值，所有章节均为占位文本
- 用户无法依赖复盘文做决策参考
- 开发文档 Task 1-9 已宣称完成，但实际功能不可用

---

## 二、问题分析

### 2.1 数据库实测状态

直接查询 [data/yunhe.db](../../data/yunhe.db)（2026-08-01 实测）：

| 表 | 行数 | 状态 | 用途 |
|---|---|---|---|
| `limit_stocks_daily` | 820 行（11 个交易日） | ✅ 正常 | 涨停股池 |
| `market_index_daily` | 30 行（10 天 × 3 指数） | ⚠️ 有数据但 `pct_chg` 全 None | 大盘指数 |
| `emotion_daily` | **0 行** | ❌ 完全空 | 情绪指标 |
| `sector_daily` | **0 行** | ❌ 完全空 | 板块日线 |
| `stock_daily` | **0 行** | ❌ 完全空 | 个股 K 线 |
| `board_ladder_daily` | **0 行** | ❌ 一直空（无 fetcher） | 连板高度分层 |
| `watchlist_stocks` | **0 行** | ❌ 一直空（scanner 没人调） | 观察池 |
| `stock_fetch_log` | 787 行（全 `failed`） | ❌ 0 条 `success` | 抓取日志 |
| `review_reports` | 1 行（`no_data` 占位） | 复盘文为占位 | 复盘存档 |

`market_index_daily` 抽查：

```
20260731 sh000001: close=3832.262 pct_chg=None
20260730 sh000001: close=3804.693 pct_chg=None
20260729 sh000001: close=3828.469 pct_chg=None
```

### 2.2 日志证据

[data/logs/yunhe-2026-08-01.log](../../data/logs/yunhe-2026-08-01.log) 关键告警：

```
emotion_daily_fetcher.run: err=fetch_emotion_daily stock_zh_index_spot_em failed
sector_daily_fetcher.run: err=fetch_sector_daily stock_board_industry_name_em failed
stock_daily_fetcher.run: code=000001 err=fetch_stock_daily stock_zh_a_hist failed
review_pipeline no_data: user_id=... trade_date=20260728
review_validation_failed: missing required sections [...]
```

### 2.3 根因分类

经核查，问题由 **5 类根因** 叠加导致，不是单一原因：

#### 根因 A：fetcher 用错数据源（3 张表 0 行的直接原因）

当前所有 fetcher 都用东财 `_em` 后缀接口，而东财接口被反爬封禁：

| fetcher | 当前接口 | 实测状态 | 问题 |
|---|---|---|---|
| `emotion_daily_fetcher` | `stock_zh_index_spot_em`（成交额）+ `stock_market_activity_legu`（涨停数） | ⚠️ legu 稳定，spot_em 不稳定 | spot_em 不带日期参数 + 反爬 |
| `sector_daily_fetcher` | `stock_board_industry_name_em` | ❌ 反爬失败 | 接口不带日期参数 |
| `stock_daily_fetcher` | `stock_zh_a_hist` | ❌ 99 股失败 80 只 | 东财反爬严重 |

**关键发现**：同花顺 `_ths`、腾讯 `_tx`、乐股 `legu` 接口大部分可用：

```
✓ stock_market_activity_legu     返回当天上涨/涨停/跌停数（仅当日截面）
✓ stock_board_industry_name_ths  返回 90 个板块
✓ stock_board_industry_index_ths 返回板块历史 OHLCV+成交额（带日期参数）
✓ stock_zh_a_hist_tx             返回个股历史 OHLCV（带日期参数）
✓ stock_fund_flow_individual      返回 5197 只个股资金流
✓ stock_fund_flow_industry        返回 90 个板块资金流+领涨股
✓ stock_zt_pool_em               涨停池（一直能用）
✓ stock_zh_index_daily            指数历史 OHLCV（一直能用）
```

→ **结论**：fetcher 必须换数据源，从东财 `_em` 换到同花顺 `_ths` / 腾讯 `_tx` / 乐股 `legu`。

#### 根因 B：fetcher 字段映射 bug（pct_chg 全 None）

[infrastructure/stock/akshare_client.py](../../infrastructure/stock/akshare_client.py) 中 `fetch_market_index` 用 `r.get("pct_chg")` 取字段，但 `stock_zh_index_daily` 实际返回的列是：

```
['date', 'open', 'high', 'low', 'close', 'volume']  ← 没有 pct_chg
```

→ `r.get("pct_chg")` → `None` → 数据库 30 行 `pct_chg` 全是 `None`。

**修复**：自己算 `(close - prev_close) / prev_close * 100`（需读前日行）。

#### 根因 C：5 个端口是 stub 占位（衍生指标未实现）

[infrastructure/stock/sqlite_data_source.py:200-251](../../infrastructure/stock/sqlite_data_source.py) 有 6 个端口方法是空 stub，注释明说"未在 schema 内实现 → 返空"：

| 端口 | 行号 | 现状 | 对应能力 |
|---|---|---|---|
| `get_signal_stocks` | 201 | `return []` | 新信号扫描 |
| `get_sector_heat_distribution` | 217-221 | `return []` | 板块高潮分布 |
| `get_strong_repair_leaders` | 223-225 | `return []` | 强修复龙头候选 |
| `get_resistant_sectors` | 227-231 | `return []` | 抗跌板块 |
| `get_sector_leaders` | 233-237 | `return []` | 板块龙头 |
| `get_sector_divergence` | 239-243 | `return []` | 板块高潮后分歧 |
| `get_correlation` | 245-251 | 返空 result | 庄股/抱团股识别 |

#### 根因 D：计算模块根本未开发（开发计划未完成）

对照开发计划 [docs/superpowers/plans/2026-07-26-stock-review-agent.md](../superpowers/plans/2026-07-26-stock-review-agent.md) Task 3、Task 4，原计划应交付：

| 计划模块 | 实际状态 | 缺失内容 |
|---|---|---|
| `emotion_aggregator.py` | ⚠️ 已移至 `domain/stock/heuristics.py`，仅 3 个聚合函数 | 缺 `classify_emotion_phase`（6 阶段判定） |
| `watchlist_scanner.py` | ⚠️ 2 个纯函数已写，位于 infrastructure 层 | **pipeline 不调它** + **位置违反架构（应移到 domain 层）** |
| `watchlist_service.py` | ❌ **文件不存在** | Task 4 计划要建，未建 |
| `correlation_analyzer.py` | ❌ **文件不存在** | Task 3 计划要建，未建 |
| `correlation_service.py` | ⚠️ 70 行空壳 | 只调 stub 端口，无算法 |
| `app.py` 装配 | ❌ `correlation_analyzer=None` | 组合根未注入 |

**git log 证据**：

```
cac5897 build: 股票复盘 Task 3 — 9 个 fetcher + 缓存层
031d019 build: 股票复盘 Task 4 — Application DTO + 7 步思维链复盘 Service
```

commit message 宣称"9 个 fetcher"和"7 步思维链"，但实际只交付了**最小可跑通版本**——后续 Task 10-20 全在补 fetcher 数据链路（warmup/stock_fetch_log/has_xxx_daily/count_limit_stocks），**没有一个 Task 补计算指标**。

#### 根因 E：board_ladder_daily 表无 fetcher

`board_ladder_daily` 表（连板高度分层：1 板几只、2 板几只...）在 v021 迁移已建表，但**没有任何 fetcher 写入**，导致表一直 0 行。SKILL.md 方法论讲"连板高度"时会用到此表。

### 2.4 akshare 数据可行性核查（关键结论）

针对用户核心疑问"akshare 是否返回这些指标"，实测后分四档：

| 档 | 含义 | 指标 |
|---|---|---|
| 🟢 **能拿到** | akshare 接口直接返回 | 涨停股、大盘 OHLCV、板块涨跌幅（同花顺）、板块龙头（同花顺领涨股）、个股 OHLCV（腾讯）、板块多日趋势（同花顺）、当日两市涨跌停数（legu） |
| 🟡 **能拿但需换源** | 默认数据源失败，换源可用 | 三大表数据（sector/stock_daily 换源即可） |
| 🟠 **只能拿当日，无法回填历史** | 接口不带日期参数 | 两市成交额（`stock_zh_index_spot_em` 仅当日，历史无法回填） |
| 🔴 **akshare 不直接返回** | 必须自己计算 | 情绪阶段、板块高潮、板块分歧、抗跌板块、强修复龙头、庄股/抱团 |

#### 2.4.1 关键澄清：两市成交额的数据来源限制

实测 `stock_zh_index_daily` 的 `volume` 字段**不是两市成交额**：

```
新浪 沪 volume: 59752942700 (597.53 亿)
新浪 深 volume: 71939594436 (719.40 亿)
新浪 沪+深 合计: 1316.93 亿

对比日志中真实 total_volume=1.2 万亿 = 12000 亿
差距: 9.1 倍
```

`stock_zh_index_daily` 的 `volume` 是"指数成交量"（可能单位为"手"），**不是成交额**。两市成交额的真实来源只有 `stock_zh_index_spot_em` 的"成交额"字段，而该接口：
- 不带日期参数（只能取当天）
- 被反爬（成功率约 50%，不稳定）

腾讯 `stock_zh_index_daily_tx` 的 `amount` 字段同样**不是两市成交额**（实测差 911 倍）。

→ **两市成交额的历史数据无法回填**，这是真实的数据可行性限制。

#### 2.4.2 最终结论

- **真正"akshare 完全不返回"的只有 1 项**：板块分时涨停分布（无免费接口提供历史分时板块涨停数据）→ 可降级为"日级别"判定
- **"akshare 不返回衍生指标"6 项**：情绪阶段 / 板块高潮 / 板块分歧 / 抗跌板块 / 强修复龙头 / 庄股抱团 → **输入数据 akshare 都能提供，缺的是计算算法**
- **"fetcher 用错数据源"3 张表**：emotion_daily / sector_daily / stock_daily → 换同花顺/腾讯即可
- **"pct_chg 字段 None"是代码 bug**：自己算就能修
- **"两市成交额历史"无法回填**：只能从 fetcher 修复日起逐日累积，历史数据缺失需如实标注

→ **大部分指标"完成开发"可行**，但"两市成交额历史"受 akshare 接口限制无法回填，复盘文需如实标注"成交额历史数据缺失（自 X 日起新增）"。

---

## 三、解决方案

### 3.1 总体策略

分 **3 个阶段** 推进，每阶段独立 Task，每个 Task 严格遵循 AGENTS.md §6 "先写失败测试 → 最小实现 → 门禁 → 独立 commit"。

```
Phase 1: 修数据层（让 3 张表有数据 + 修 pct_chg bug + 补 board_ladder）
  Task A: market_index_fetcher 修 pct_chg 字段 bug
  Task B: emotion_daily_fetcher 保留 spot_em + 降级处理 + 边界修复
  Task C: sector_daily_fetcher 换 stock_board_industry_index_ths（同花顺）
  Task D: stock_daily_fetcher 换 stock_zh_a_hist_tx（腾讯）
  Task A2: board_ladder_daily 从 limit_stocks_daily 聚合写入

Phase 2: 补计算层（写衍生指标算法 + 架构修正）
  Task E: 6 维度情绪观察框架（高度/广度/强度/韧性/真实度/持续性）+ 迁移 v023
  Task F: sector_phase_analyzer 新建（高潮/分歧/抗跌 3 个算法）+ 迁移 v024
  Task G: watchlist_scanner 移到 domain 层 + watchlist_service 接入 pipeline
  Task H: correlation_analyzer 新建（庄股/抱团相关性聚类）+ 迁移 v025

Phase 3: 接入复盘文
  Task I: review_service 真实调端口拿数据（替换 stub）
```

### 3.2 依赖关系

```
Task A（pct_chg bug）          → 独立可做
Task B（emotion fetcher 修复） → 独立可做
Task C（sector fetcher 换源）  → 独立可做
Task D（stock_daily 换源）     → 独立可做
Task A2（board_ladder 聚合）   → 独立可做（仅依赖 limit_stocks_daily 已有数据）

Task E（6 维度情绪观察）       ← 依赖 Task B（基础情绪数据）+ Task D（stock_daily，用于韧性维度——断板反包 + 5 日累计涨幅）；代码做维度分类（高位/广度/强度等），AI 受约束推理，不判阶段
Task F（板块高潮/分歧算法）    ← 依赖 Task C（sector_daily 有数据）
Task G（观察池入池）           ← 依赖 Task D（stock_daily 有数据）+ 架构迁移
Task H（庄股/抱团算法）        ← 依赖 Task D（stock_daily 有数据）

Task I（接入复盘文）           ← 依赖 Task E/F/G/H 全部完成
```

**Task E 的特殊说明（v2.6 修正）**：情绪观察采用 6 维度框架（高度/广度/强度/韧性/真实度/持续性），详见 §3.3 Task E：
- 代码做**维度分类**（高位/中位/低位、普涨/偏广/平衡/偏窄/普跌等），阈值硬编码无 AI 发挥空间
- 代码做**市场风格识别**（题材股主导/趋势股主导/题材+趋势共振/弱势市场/混合）
- 代码**不做阶段判定**（不写 phase 字段），LLM 基于 6 维度分类受约束推理
- 解决 v2.0-v2.3 单维度（涨停数）判情绪的刻舟求剑问题
- 依赖 Task B + Task D（韧性维度需 stock_daily 数据）+ 迁移 v023（新增 18 个字段）

### 3.3 各 Task 详细方案

---

#### Task A: 修复 market_index_fetcher 的 pct_chg 字段 None bug

**问题**：[infrastructure/stock/akshare_client.py](../../infrastructure/stock/akshare_client.py) 中 `fetch_market_index` 用 `r.get("pct_chg")` 取字段，但 `stock_zh_index_daily` 不返回该字段。

**修复方案**：在写入时自己算 pct_chg。

```python
# 伪代码：fetch_market_index 改为
def fetch_market_index(index_code: str, end_date: str, days: int = 30) -> list[MarketIndexRow]:
    df = ak.stock_zh_index_daily(symbol=index_code)
    # 取最近 N 日
    df = df.tail(days)
    rows: list[MarketIndexRow] = []
    prev_close: float | None = None
    for _, r in df.iterrows():
        close = float(r["close"])
        pct_chg = ((close - prev_close) / prev_close * 100) if prev_close else None
        rows.append(MarketIndexRow(
            trade_date=str(r["date"]).replace("-", ""),
            index_code=index_code,
            open=float(r["open"]), high=float(r["high"]),
            low=float(r["low"]), close=close,
            volume=float(r["volume"]),
            pct_chg=pct_chg,
        ))
        prev_close = close
    return rows
```

**测试**：先写失败测试断言 `pct_chg is not None`，再实现。

**工作量**：~30 行代码 + 2 个单测。

**注意**：不使用腾讯 `stock_zh_index_daily_tx` 的 `amount` 字段（实测差 911 倍，不是成交额）。

---

#### Task B: emotion_daily_fetcher 保留 spot_em + 降级处理 + 边界修复

**问题**：
1. `stock_zh_index_spot_em` 不带日期参数 + 反爬不稳定（约 50% 成功率）
2. `stock_market_activity_legu` 稳定但只返回涨停数（不含成交额）
3. fetcher 在 `limit_stocks_daily` 该日无数据时跳过写入（[emotion_daily_fetcher.py:80-86](../../infrastructure/stock/emotion_daily_fetcher.py#L80-L86)）

**修复方案**：

**两市成交额处理**（关键修正：不换数据源，改为降级）：

```python
async def _fetch(trade_date: str) -> EmotionRawData:
    # 1. 涨停/跌停/炸板数：legu 稳定可用
    activity_df = await asyncio.to_thread(ak.stock_market_activity_legu)
    limit_up = _df_to_int(activity_df, "涨停")
    limit_down = _df_to_int(activity_df, "跌停")
    broken = _df_to_int(activity_df, "炸板")

    # 2. 两市成交额：spot_em 不稳定，失败时降级为 None
    total_volume: float | None = None
    try:
        spot_df = await asyncio.to_thread(ak.stock_zh_index_spot_em)
        total_volume = _extract_shanghai_total_volume(spot_df)
        if total_volume == 0.0:
            total_volume = None  # 明确区分"未抓到"和"成交额为0"
    except _AKSHARE_EXC as e:
        logger.warning(
            "fetch_emotion_daily spot_em failed date=%s err=%s",
            trade_date, e,
        )
        total_volume = None  # 降级：成交额缺失，其他字段照写

    # 3. 边界：无 limit_stocks 时也写入（但 valid_count/max_boards 留 0）
    #    修正原 fetcher 的"无 limit_stocks 就 skip"逻辑——
    #    涨停数为 0 也是有效数据（冰点期），不应跳过
    return EmotionRawData(
        trade_date=trade_date,
        limit_up_count=limit_up,
        limit_down_count=limit_down,
        broken_count=broken,
        total_volume=total_volume,  # 可能为 None
    )
```

**EmotionRawData 模型改动**：`total_volume: float | None`（原为 `float`，需放宽）。

**volume_change_pct 处理**：
- 当日或前日 `total_volume` 为 None 时，`volume_change_pct = None`
- 复盘文 LLM 看到None 时标注"成交额数据缺失"

**历史数据限制说明**：
- spot_em 只返回当天数据，**历史无法回填**
- 修复后只能从当天起逐日累积
- 复盘文对历史日期应标注"成交额数据缺失（接口限制）"

**测试**：
1. mock spot_em 成功 → 断言 total_volume 非空
2. mock spot_em 失败 → 断言 total_volume=None，其他字段正常写入
3. mock limit_stocks 为空 → 断言 emotion_daily 仍写入（valid_count=0）

**工作量**：~80 行代码 + 3 个单测。

---

#### Task C: sector_daily_fetcher 换同花顺数据源

**问题**：当前用 `stock_board_industry_name_em`（东财反爬失败）。

**修复方案**：换同花顺 `stock_board_industry_index_ths`。

```python
async def run(trade_date: str, repo: CacheRepository) -> int:
    # 1. 取 90 个板块列表（同花顺）
    sectors = await asyncio.to_thread(ak.stock_board_industry_name_ths)  # cols: name, code

    # 2. 逐板块取当日涨跌幅
    rows: list[SectorDailyRow] = []
    for _, sector in sectors.iterrows():
        name = sector["name"]
        # stock_board_industry_index_ths 返回 OHLCV+成交额，带日期参数
        hist = await asyncio.to_thread(
            ak.stock_board_industry_index_ths,
            symbol=name, start_date=trade_date, end_date=trade_date,
        )
        if len(hist) == 0:
            continue
        today = hist.iloc[-1]
        prev_close = hist.iloc[-2]["收盘价"] if len(hist) >= 2 else today["开盘价"]
        pct_chg = (today["收盘价"] / prev_close - 1) * 100 if prev_close else None

        rows.append(SectorDailyRow(
            trade_date=trade_date,
            sector_code=sector["code"],
            sector_name=name,
            pct_chg=pct_chg,
            limit_up_count=0,  # 板块涨停数需另外从 limit_stocks_daily 聚合
            leading_stock_codes=[],  # Task F 填
        ))

    repo.upsert_sector_daily(trade_date=trade_date, rows=rows)
    return len(rows)
```

**性能考量（修正）**：90 个板块串行调接口，单次约 2-3 秒，**总耗时约 180-270 秒（3-4.5 分钟）**。作为后台任务（已用 `asyncio.create_task`）不影响登录，但需加 1 秒 sleep 防反爬。

**测试**：mock akshare，断言 sector_daily 表写入 ≥ 80 行。

**工作量**：~100 行代码 + 3 个单测。

---

#### Task D: stock_daily_fetcher 换腾讯数据源

**问题**：当前用 `stock_zh_a_hist`（东财反爬，99 股失败 80 只）。

**修复方案**：换腾讯 `stock_zh_a_hist_tx`。

```python
async def run(trade_date: str, repo: CacheRepository) -> int:
    # 1. 从 limit_stocks_daily 取当日涨停股列表
    limit_stocks = repo.select_limit_stocks(trade_date)

    # 2. 逐股取 K 线（腾讯数据源）
    written = 0
    for stock in limit_stocks:
        code = stock.stock_code
        # 腾讯接口需要 sh/sz 前缀
        prefix = "sh" if code.startswith("6") else "sz"
        symbol = f"{prefix}{code}"

        try:
            df = await asyncio.to_thread(
                ak.stock_zh_a_hist_tx,
                symbol=symbol,
                start_date=trade_date,
                end_date=trade_date,
            )
            if len(df) == 0:
                continue
            row = df.iloc[-1]
            repo.upsert_stock_daily(
                trade_date=trade_date,
                stock_code=code,
                open=float(row["open"]),
                close=float(row["close"]),
                high=float(row["high"]),
                low=float(row["low"]),
                volume=float(row["volume"]),
                pct_chg=...,  # 自己算
                turnover=float(row.get("turnover", 0)),
            )
            written += 1
        except Exception as e:
            log warning f"fetch_stock_daily failed code={code} date={trade_date}"
            continue

    return written
```

**关键改动**：
- 接口从 `stock_zh_a_hist` 换到 `stock_zh_a_hist_tx`（腾讯成功率高）
- 仍用 `asyncio.to_thread` 包装（不阻塞事件循环）
- 失败的股记录到 stock_fetch_log（Task 20 已有表）

**性能考量（修正）**：99 只涨停股串行调腾讯接口，单次约 2-3 秒，**总耗时约 200-300 秒（3-5 分钟）**。作为后台任务可接受。

**测试**：mock akshare，断言 stock_daily 表写入行数 > 0。

**工作量**：~120 行代码 + 3 个单测。

---

#### Task A2: board_ladder_daily 从 limit_stocks_daily 聚合写入

**问题**：`board_ladder_daily` 表已建（v021 迁移）但无 fetcher，表一直 0 行。

**修复方案**：新增 fetcher，从 `limit_stocks_daily` 聚合按连板高度分层统计。

```python
async def run(trade_date: str, repo: CacheRepository) -> int:
    """从 limit_stocks_daily 聚合写入 board_ladder_daily。

    按 consecutive_boards 字段分组统计：
    - 1 板：N 只
    - 2 板：M 只
    - 3 板：K 只
    - ...
    """
    limit_stocks = repo.select_limit_stocks(trade_date)
    if not limit_stocks:
        return 0

    # 按连板高度分组
    ladder: dict[int, list[str]] = {}
    for s in limit_stocks:
        boards = s.consecutive_boards
        ladder.setdefault(boards, []).append(s.stock_code)

    rows = [
        BoardLadderRow(
            trade_date=trade_date,
            boards=boards,
            count=len(codes),
            stock_codes=codes,
        )
        for boards, codes in sorted(ladder.items())
    ]
    repo.upsert_board_ladder(trade_date=trade_date, rows=rows)
    return len(rows)
```

**测试**：mock limit_stocks 数据，断言 board_ladder_daily 表按连板高度正确分组。

**工作量**：~60 行代码 + 2 个单测。

---

#### Task E: 6 维度情绪观察框架（代码做维度分类，不做阶段判定）

**目标**：提供 6 维度客观数据 + 维度分类（高位/中位/低位等），让 LLM 基于分类组合受约束推理，避免"单维度（涨停数）判情绪"的刻舟求剑问题。

**v2.6 关键方向修正**（彻底改变思路）：

v2.0-v2.3 的所有方案都隐含假设"涨停数是情绪的代理指标"，但实际市场风格会切换：
- 题材股主导时：涨停数 = 情绪亢奋度（合理）
- 趋势股主导时：涨停数少不代表情绪弱（机构主导，慢牛慢熊）
- 风格切换期：涨停数骤变 ≠ 情绪转折（只是资金切换）

→ **单维度（涨停数）判情绪 = 刻舟求剑**。必须用 6 维度组合观察。

**v2.6 核心原则**：
1. 代码不做"阶段判定"（不写 phase=高潮期）
2. 代码做"维度分类"（写 strength_level=强势 / breadth_level=普涨 等描述性分类）
3. 每个维度的分类有**明确代码定义**（无 AI 发挥空间，避免质量不稳定）
4. AI 基于分类组合推理（受约束推理，不是自由发挥）
5. 维度间矛盾由 SKILL.md 强制规则处理（不是 AI 自由判断）

##### E.1 6 维度框架总览

| 维度 | 观察什么 | 解决什么问题 | v2.2 之前缺失 |
|---|---|---|---|
| **1. 高度** | 涨停数 + 连板数 | 题材股亢奋度 | ❌ 过度依赖，单维度判情绪 |
| **2. 广度** | 涨跌家数比 | 全市场赚钱效应 | ❌ 完全没做 |
| **3. 强度** | 成交额前 20 涨幅 | 主力资金动向 + 市场风格 | ❌ 完全没做 |
| **4. 韧性** | 断板反包 + 累计涨幅 | 修复力度（5+4 模式） | ❌ 只看最高连板 |
| **5. 真实度** | 有效涨停 + 炸板率 | 真假亢奋 | ✅ 已有 |
| **6. 持续性** | 5/20 日趋势方向 | 演化方向 | ✅ 已有但弱 |

##### E.2 emotion_daily 表 schema 扩展（迁移 v023）

**新增字段**（代码全部写入，AI 无发挥空间）：

| 字段 | 类型 | 维度 | 含义 | 数据源 |
|---|---|---|---|---|
| adv_count | int | 广度 | 上涨家数 | legu |
| decl_count | int | 广度 | 下跌家数 | legu |
| adv_decl_ratio | float | 广度 | 涨跌比 = adv/decl | 计算 |
| breadth_level | str | 广度 | 普涨/偏广/平衡/偏窄/普跌 | 计算（明确阈值） |
| top20_volume_avg_chg | float | 强度 | 成交额前20平均涨幅(%) | stock_fund_flow_individual |
| top20_volume_up_count | int | 强度 | 成交额前20上涨家数 | 同上 |
| top20_volume_limit_up_count | int | 强度 | 成交额前20涨停家数 | 同上 |
| strength_level | str | 强度 | 强势/偏强/中性/偏弱/弱势 | 计算（明确阈值） |
| market_style | str | 强度 | 题材股主导/趋势股主导/题材+趋势共振/弱势市场/混合 | 计算（组合判定） |
| board_break_total_count | int | 韧性 | 断板股总数 | stock_daily 多日 |
| board_break_rebound_count | int | 韧性 | 反包成功数（涨幅>5%） | stock_daily 多日 |
| rebound_success_ratio | float | 韧性 | 反包成功率 | 计算 |
| top5d_avg_chg | float | 韧性 | 涨停股5日累计涨幅中位数(%) | stock_daily 多日 |
| resilience_level | str | 韧性 | 强/中/弱/无断板 | 计算（明确阈值） |
| authenticity_level | str | 真实度 | 真实/偏真/偏虚/虚高 | 计算（基于 broken_ratio） |
| height_level | str | 高度 | 高位/中位/低位/极低位 | 计算（分位数） |
| trend_5d | str | 持续性 | 上升/下降/震荡/数据不足 | 计算（线性回归斜率） |
| trend_20d | str | 持续性 | 上升/下降/震荡/数据不足 | 同上 |

**废弃字段**（保持 None，永不写入）：
- `phase` / `phase_confidence` / `phase_reason`（已有字段，保留 schema 但默认 None）

**迁移**：v023 新增上述 18 个字段（ALTER TABLE ADD COLUMN），回滚为 DROP COLUMN。

##### E.3 各维度精确代码定义（无 AI 发挥空间）

###### 维度 1：情绪高度

**原始指标**（已有）：
```python
limit_up_count = count(stock_daily WHERE pct_chg >= 9.8)  # 涨停数
max_consecutive_boards = max(consecutive_days_where_pct_chg >= 9.8)  # 连板
```

**分类阈值**（基于近 20 日分位数，相对化避免刻舟求剑）：
```python
limit_up_pct = percentile(today.limit_up_count, history_20d.limit_up_count)
if limit_up_pct >= 0.8: height_level = "高位"
elif limit_up_pct >= 0.5: height_level = "中位"
elif limit_up_pct >= 0.2: height_level = "低位"
else: height_level = "极低位"
```

###### 维度 2：情绪广度

**数据源**：`ak.stock_market_activity_legu`（已验证稳定可用，Task B 已用）

**实测字段结构**（2026-08-02 验证）：
```
列: ['item', 'value']
行: '上涨' / '下跌' / '涨停' / '跌停' / '炸板' / '平盘' / '停牌' / '活跃度' / '统计日期'
value 列 dtype: object（含浮点数，需 int() 转换）
```

⚠️ 注意：字段名是 `上涨` / `下跌`，不是 `上涨家数` / `下跌家数`。akshare_client.py 已有辅助函数 `_df_to_int(df, item)` 可直接复用。

**原始指标**：
```python
# 复用 akshare_client.py 已有的 _df_to_int 辅助函数
# emotion_daily_fetcher 调 fetch_emotion_daily 时已拿到 activity_df
adv_count = _df_to_int(activity_df, "上涨")
decl_count = _df_to_int(activity_df, "下跌")
adv_decl_ratio = adv_count / decl_count if decl_count > 0 else 999.0
```

**分类阈值**（绝对阈值——广度是全市场指标，不需相对化）：
```python
if adv_decl_ratio >= 3.0: breadth_level = "普涨"      # 75%+ 上涨
elif adv_decl_ratio >= 1.5: breadth_level = "偏广"    # 60%+ 上涨
elif adv_decl_ratio >= 0.67: breadth_level = "平衡"   # 40-60%
elif adv_decl_ratio >= 0.33: breadth_level = "偏窄"   # 25-40%
else: breadth_level = "普跌"                          # <25% 上涨
```

###### 维度 3：情绪强度（判市场风格关键）

**数据源**：`ak.stock_fund_flow_individual`（同花顺，已验证可用）

**实测字段结构**（2026-08-02 验证）：
```
列: ['序号', '股票代码', '股票简称', '最新价', '涨跌幅', '换手率',
     '流入资金', '流出资金', '净额', '成交额']
涨跌幅 dtype: str  示例: "20.01%"
成交额 dtype: str  示例: "3.35亿"
```

⚠️ 注意：
1. 字段名是 `涨跌幅` 不是 `pct_chg`
2. `涨跌幅` 和 `成交额` 都是字符串（带 `%` 或 `亿`/`万` 后缀），必须解析后才能数值运算
3. 不能直接对字符串 `成交额` 排序（"9亿" > "10亿" 字典序错误）

**原始指标**（akshare_client.py 新增 `fetch_top20_volume_stocks`）：
```python
def fetch_top20_volume_stocks() -> Top20VolumeSnapshot:
    """取成交额前 20 名股票的涨幅统计。
    
    akshare 返回的 涨跌幅/成交额 都是字符串，需要解析：
    - "20.01%" → 20.01
    - "3.35亿" → 335000000
    - "9300万" → 93000000
    """
    df = ak.stock_fund_flow_individual()
    # 解析字符串为数值
    df["_pct"] = df["涨跌幅"].apply(_parse_pct_str)        # "20.01%" → 20.01
    df["_amount"] = df["成交额"].apply(_parse_amount_str)  # "3.35亿" → 335000000
    # 用 nlargest 取前 20（不能对字符串 sort_values）
    top20 = df.nlargest(20, "_amount")
    return Top20VolumeSnapshot(
        avg_chg=top20["_pct"].mean(),
        up_count=int((top20["_pct"] > 0).sum()),
        limit_up_count=int((top20["_pct"] >= 9.8).sum()),
    )

def _parse_pct_str(s: str) -> float:
    """解析 '20.01%' → 20.01"""
    if not isinstance(s, str): return 0.0
    return float(s.rstrip("%"))

def _parse_amount_str(s: str) -> float:
    """解析 '3.35亿' → 335000000, '9300万' → 93000000"""
    if not isinstance(s, str): return 0.0
    if s.endswith("亿"): return float(s[:-1]) * 1e8
    if s.endswith("万"): return float(s[:-1]) * 1e4
    try: return float(s)
    except ValueError: return 0.0
```

**强度分类阈值**（绝对阈值——成交额前 20 是绝对排名，不需相对化）：
```python
if top20_volume_avg_chg >= 3.0 and top20_volume_up_count >= 15:
    strength_level = "强势"
elif top20_volume_avg_chg >= 1.0 and top20_volume_up_count >= 10:
    strength_level = "偏强"
elif top20_volume_avg_chg >= -1.0:
    strength_level = "中性"
elif top20_volume_avg_chg >= -3.0:
    strength_level = "偏弱"
else:
    strength_level = "弱势"
```

**市场风格判定**（强度 + 高度组合，客观无歧义）：
```python
if strength_level in ["强势", "偏强"] and height_level in ["低位", "极低位"]:
    market_style = "趋势股主导"  # 前20强 + 涨停少 = 机构主导
elif strength_level in ["强势", "偏强"] and height_level == "高位":
    market_style = "题材+趋势共振"  # 都强
elif strength_level in ["偏弱", "弱势"] and height_level == "高位":
    market_style = "题材股主导"  # 涨停高但前20弱 = 游资打板
elif strength_level in ["偏弱", "弱势"] and height_level in ["低位", "极低位"]:
    market_style = "弱势市场"
else:
    market_style = "混合"
```

###### 维度 4：情绪韧性（5+4 模式识别）

**数据源**：`stock_daily`（需 Task D 完成）+ `limit_stocks_daily`（已有）

**原始指标计算**：
```python
# 1. 找"断板股"：昨日涨停今日未涨停
yesterday_limit_up_codes = limit_stocks_daily[yesterday].stock_codes
board_break_total_count = count(
    stock_daily[today WHERE stock_code IN yesterday_limit_up_codes 
                AND pct_chg < 9.8]
)

# 2. 判定"反包成功"：今日涨幅 > 5%（严格定义，不靠 AI 判断）
#    ⚠️ 排除今日涨停（已计入维度1，不重复算）
board_break_rebound_count = count(
    stock_daily[today WHERE 
        stock_code IN yesterday_limit_up_codes 
        AND pct_chg < 9.8          # 今日未涨停（断板状态）
        AND pct_chg > 5.0          # 今日涨幅 > 5%（反包成功）
    ]
)
rebound_success_ratio = (
    board_break_rebound_count / board_break_total_count 
    if board_break_total_count > 0 else 0.0
)

# 3. 涨停股 5 日累计涨幅中位数（软高度，识别 5+4 模式）
recent_5d_limit_up_codes = limit_stocks_daily[today].stock_codes
top5d_avg_chg = median([
    (stock_daily[today, code].close / stock_daily[today-5, code].close - 1) * 100
    for code in recent_5d_limit_up_codes
    if code in stock_daily[today-5]  # 防御：5日前未上市
])
```

**韧性分类阈值**：
```python
if board_break_total_count == 0:
    resilience_level = "无断板"  # 没有断板股，无法判定韧性
elif rebound_success_ratio >= 0.5 and board_break_rebound_count >= 3:
    resilience_level = "强"  # 一半以上断板股反包，且数量>=3
elif rebound_success_ratio >= 0.3 and board_break_rebound_count >= 2:
    resilience_level = "中"
else:
    resilience_level = "弱"  # 反包少
```

###### 维度 5：情绪真实度（已有，补分类）

**原始指标**（Task B 已实现）：
```python
valid_limit_up_count  # 已有
broken_limit_ratio  # 已有
```

**分类阈值**：
```python
if broken_limit_ratio < 0.15: authenticity_level = "真实"
elif broken_limit_ratio < 0.30: authenticity_level = "偏真"
elif broken_limit_ratio < 0.50: authenticity_level = "偏虚"
else: authenticity_level = "虚高"
```

###### 维度 6：情绪持续性

**原始指标**：近 5 日/20 日的涨停数序列

**分类算法**（线性回归斜率，客观）：
```python
def compute_trend(values: list[float]) -> str:
    """用线性回归斜率判定趋势方向（无 AI 发挥）。"""
    if len(values) < 3:
        return "数据不足"
    n = len(values)
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n
    numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    slope = numerator / denominator if denominator != 0 else 0.0
    # 阈值：日均变化率 > 5% 视为趋势
    avg = y_mean if y_mean > 0 else 1.0
    daily_change_ratio = slope / avg
    if daily_change_ratio > 0.05: return "上升"
    elif daily_change_ratio < -0.05: return "下降"
    else: return "震荡"

trend_5d = compute_trend(history_5d.limit_up_count)
trend_20d = compute_trend(history_20d.limit_up_count)
```

##### E.4 fetcher 改动

**emotion_daily_fetcher**：
- ✅ Task B 已实现：limit_up / valid / max_boards / broken_ratio / total_volume / volume_change_pct
- 🆕 Task E 新增：调 `compute_breadth()` / `compute_strength()` / `compute_resilience()` / `compute_trend()` / `compute_levels()`
- ❌ 不写 phase / phase_confidence / phase_reason 字段（保持 None）

**新增辅助计算模块**：`domain/stock/emotion_dimensions.py`（纯函数，符合 §8.1）

```python
# domain/stock/emotion_dimensions.py
"""6 维度情绪观察的计算函数（纯函数，无 I/O）。

所有函数返回客观值或分类字符串，不做阶段判定。
阈值定义在本模块内硬编码，AI 无发挥空间。
"""

def compute_breadth_level(adv_count: int, decl_count: int) -> str: ...
def compute_strength_level(top20_avg_chg: float, top20_up_count: int) -> str: ...
def compute_market_style(strength_level: str, height_level: str) -> str: ...
def compute_resilience_level(break_total: int, rebound_count: int) -> str: ...
def compute_authenticity_level(broken_ratio: float) -> str: ...
def compute_height_level(limit_up_pct: float) -> str: ...
def compute_trend(values: list[float]) -> str: ...
```

##### E.5 LLM 推理强约束模板（SKILL.md §三第 2 步修订）

LLM 拿到数据后**必须按固定模板推理**，不能自由发挥：

```markdown
**第 2 步输出必须包含**：

1. 6 维度分类快照（直接抄表，不允许修改）：
   - 高度：{height_level}（涨停 {limit_up_count} / 连板 {max_boards}）
   - 广度：{breadth_level}（涨跌比 {adv_decl_ratio:.2f}）
   - 强度：{strength_level}（前20涨幅 {top20_volume_avg_chg:.1f}%）
   - 韧性：{resilience_level}（反包 {board_break_rebound_count}/{board_break_total_count}）
   - 真实度：{authenticity_level}（炸板率 {broken_limit_ratio:.0%}）
   - 持续性：5日{trend_5d} / 20日{trend_20d}
   - 市场风格：{market_style}

2. 综合推理（必须引用上述分类）：
   基于 6 维度组合，描述当前市场状态。
   必须解释维度间的一致性或矛盾。

3. 矛盾处理（SKILL.md 强制规则，非 AI 自由判断）：
   - height_level=高位 + breadth_level=普跌 → 标注"虚假强势"，confidence ≤ 低
   - height_level=低位 + resilience_level=强 → 标注"修复中"（5+4 模式）
   - strength_level=强势 + height_level=低位 → 标注"趋势股主导"，跳过情绪周期框架
   - height_level=高位 + authenticity_level=虚高 → 标注"虚高"
   - trend_5d=下降 + height_level=高位 → 标注"退潮信号"（SKILL.md §三第 3 步）
   - trend_5d=上升 + breadth_level in [普涨, 偏广] → 标注"修复信号"（与规则 2 互补）
   - strength_level=弱势 + breadth_level=普跌 → 标注"系统性风险"（SKILL.md §0.5 大盘维度过滤）
   - market_style=混合 → confidence ≤ 低（风格不明朗时降低置信度）
   - 任意两维度矛盾 → confidence 不超过"中"
   - 三个以上维度矛盾 → 标注"混沌"，confidence=低

4. 不输出"阶段标签"：
   - ❌ "今日处于高潮期"
   - ✅ "高度高位 + 广度偏广 + 强度强势 + 韧性中 + 真实度真实 = 综合强势"
```

##### E.6 工具调用方式

```
Step 2: get_emotion_indicators_trend(date, 5)  # 返回近 5 日序列（含 6 维度分类字段）
        → LLM 基于 SKILL.md §三第 2 步受约束推理
        → LLM 可对比"今日 vs 昨日"的维度变化（trend_5d / height_level 等）

Step 3: get_emotion_cycles(date, 60)            # 上一轮周期段对比（峰谷检测，新增）
        → LLM 基于 SKILL.md §三第 3 步对比"当前修复力度 vs 上一轮修复力度"
```

⚠️ 注意：
- 不能用 `get_emotion_indicators(date-1)` 做对比，因为该端口只返回原始数据（涨停数/炸板率），不含 6 维度分类字段（height_level / trend_5d 等是写入 emotion_daily 表的，需要查表才有）
- 必须用 `get_emotion_indicators_trend(date, 5)` 拿多日序列（含分类字段），LLM 才能做"今日 vs 昨日维度变化对比"
- 第 3 步保留"上一轮周期对比"，由新增的 `identify_emotion_cycles` 函数做峰谷检测提供数据（见 E.10）

##### E.7 测试设计

**测试用例（12 个）**：

1. `test_compute_breadth_level_thresholds`：adv_decl_ratio 边界值 → 正确分类
2. `test_compute_strength_level_thresholds`：top20_avg_chg + up_count 组合 → 正确分类
3. `test_compute_market_style_combinations`：5 种市场风格判定
4. `test_compute_resilience_level_with_no_break`：board_break_total=0 → "无断板"
5. `test_compute_resilience_level_strong`：反包率 0.6 + 数量 4 → "强"
6. `test_compute_resilience_level_weak`：反包率 0.1 + 数量 1 → "弱"
7. `test_compute_authenticity_level_thresholds`：broken_ratio 边界值
8. `test_compute_height_level_with_insufficient_history`：历史 <5 日 → 默认"中位"
9. `test_compute_height_level_percentile`：构造 20 日历史，分位数正确
10. `test_compute_trend_rising`：5 日涨停数 [10,15,20,25,30] → "上升"
11. `test_compute_trend_falling`：5 日涨停数 [30,25,20,15,10] → "下降"
12. `test_compute_trend_oscillating`：5 日涨停数 [20,15,25,15,20] → "震荡"

**不测**：阶段判定（这是 LLM 职责）

##### E.8 SKILL.md 同步修订建议

**§2.1 改为多维度观察**：标注 6 阶段框架仅适用于题材股主导市场；新增 6 维度观察框架。

**§三第 2 步改为受约束推理模板**：必须输出 6 维度快照 + 综合推理 + 矛盾处理（8 条强制规则）；不允许输出阶段标签。

**§三第 3 步保留周期对比**（修正 v2.6 初稿错误）：
- 原计划"简化为 trend_5d/20d"是错的——trend_5d 只能告诉"近 5 日趋势方向"，不能告诉"当前修复力度 vs 上一轮修复力度"
- 必须保留"与上一轮退潮比"，由新增的 `identify_emotion_cycles` 函数（见 E.10）做峰谷检测提供客观数据
- LLM 基于代码提供的周期段数据，对比"当前涨停数 vs 上一轮首次强修复涨停数"

**新增 §0.6 市场风格识别**：market_style 字段说明 + 不同风格的复盘框架选择规则。

**新增 §十 代码与 AI 职责分工**：代码做维度分类（客观）+ 周期段峰谷检测（客观），AI 做综合推理（受约束）。

##### E.9 工作量与依赖

**工作量**：~410 行（v2.6 自检后修正，原估 350 行低估 60 行）
- `domain/stock/emotion_dimensions.py`：~150 行（6 个 compute_* 函数 + 2 个字符串解析辅助函数）
- `domain/stock/emotion_cycles.py`：~80 行（峰谷检测 + 周期段识别，见 E.10）
- `infrastructure/stock/emotion_daily_fetcher.py` 扩展：~60 行（调 6 维度计算）
- `infrastructure/stock/akshare_client.py` 新增 `fetch_top20_volume_stocks`：~80 行（解析 2 个字符串字段 + nlargest 排序 + 取前 20）
- `infrastructure/stock/akshare_client.py` 扩展 `fetch_emotion_daily`：~20 行（多取 adv/decl_count 2 个字段）
- 迁移 v023：~40 行（ALTER TABLE ADD COLUMN × 18 + 回滚 DROP COLUMN × 18）
- 端口/fake 扩展：~40 行（新增 `get_emotion_cycles` 端口方法）

**测试**：14 个单测 + 集成测试更新（原 12 个 + 周期段识别 2 个）。

**依赖**：
- Task B（emotion_daily 基础数据）
- Task D（stock_daily 数据，用于韧性维度——断板反包 + 5 日累计涨幅）
- 迁移 v023（新增 18 个字段）

**与 v2.2 对比**：
| 维度 | v2.2（已废弃） | v2.6（正确） |
|---|---|---|
| 观察维度 | 单维度（涨停数分位） | 6 维度（高度/广度/强度/韧性/真实度/持续性） |
| 阶段判定 | LLM 完全自判 | 代码做维度分类，LLM 受约束推理 |
| 市场风格 | 不识别 | 自动识别 5 种风格 |
| 质量稳定性 | 低（LLM 自由发挥） | 高（阈值硬编码 + 矛盾规则强制） |
| 符合 SKILL.md | ✅ 但走极端 | ✅ 代码辅助 + AI 启发式 |
| 复杂度 | ~180 行 | ~410 行（含周期段识别） |
| 刻舟求剑 | 严重（单维度） | 避免（多维度 + 风格识别） |

##### E.10 周期段识别（峰谷检测，为 SKILL.md §三第 3 步提供数据）

**目的**：SKILL.md §三第 3 步要求"与上一轮退潮比"——找最近一次"强分歧→冰点"周期段，对比当前修复力度。这个峰谷检测是纯算法，LLM 看一串数字找峰谷容易眼花，必须代码做。

**新增模块**：`domain/stock/emotion_cycles.py`（纯函数，符合 §8.1）

**端口定义**（`domain/stock/ports.py`）：
```python
class StockDataSource(Protocol):
    async def get_emotion_cycles(
        self, end_date: str, lookback_days: int = 60
    ) -> list[EmotionCycleSegment]:
        """返回近 N 日的情绪周期段（峰谷检测，客观切分）。
        
        不判定阶段方向——只提供客观数据（峰值日/谷值日/首次修复日），
        LLM 基于 SKILL.md §三第 3 步自己对比修复力度。
        """
        ...
```

**返回 DTO**（`domain/stock/models.py` 新增）：
```python
class EmotionCycleSegment(BaseModel):
    """情绪周期段（峰→谷→修复），供 LLM 对比修复力度。
    
    不含方向判定——LLM 基于 SKILL.md §三第 3 步自己判断。
    """
    model_config = ConfigDict(extra="forbid")
    peak_date: str               # 峰值日（涨停数局部极大）
    peak_limit_up_count: int     # 峰值日涨停数
    trough_date: str             # 谷值日（涨停数局部极小）
    trough_limit_up_count: int   # 谷值日涨停数
    first_repair_date: str | None       # 谷值后首次修复日（涨停数回升 ≥ 30%）
    first_repair_limit_up: int | None   # 首次修复日涨停数
```

**算法实现**（`domain/stock/emotion_cycles.py`）：
```python
def identify_emotion_cycles(
    history: list[EmotionIndicators],  # 近 60 日，按时间正序
    min_peak_trough_gap: int = 3,      # 峰谷间至少间隔 3 日
    repair_threshold: float = 0.3,     # 涨停数回升 30% 视为首次修复
) -> list[EmotionCycleSegment]:
    """峰谷检测：找局部极大值（峰）和局部极小值（谷），切成周期段。
    
    纯算法，不做阶段判定。返回客观数据供 LLM 对比。
    """
    if len(history) < 5:
        return []
    
    # 1. 找局部极大值（峰值日）：今日涨停数 > 前后各 min_peak_trough_gap 日
    peaks = _find_local_maxima(
        [h.limit_up_count for h in history], 
        window=min_peak_trough_gap
    )
    # 2. 找局部极小值（谷值日）
    troughs = _find_local_minima(
        [h.limit_up_count for h in history], 
        window=min_peak_trough_gap
    )
    # 3. 配对峰谷：每个峰值后的第一个谷值
    segments = []
    for peak_idx in peaks:
        # 找该峰值后的第一个谷值
        following_troughs = [t for t in troughs if t > peak_idx]
        if not following_troughs:
            continue
        trough_idx = following_troughs[0]
        # 4. 找谷值后的首次修复（涨停数回升 ≥ 30%）
        trough_value = history[trough_idx].limit_up_count
        repair_idx = None
        for i in range(trough_idx + 1, len(history)):
            if trough_value > 0:
                repair_ratio = (history[i].limit_up_count - trough_value) / trough_value
                if repair_ratio >= repair_threshold:
                    repair_idx = i
                    break
        segments.append(EmotionCycleSegment(
            peak_date=history[peak_idx].trade_date,
            peak_limit_up_count=history[peak_idx].limit_up_count,
            trough_date=history[trough_idx].trade_date,
            trough_limit_up_count=history[trough_idx].limit_up_count,
            first_repair_date=history[repair_idx].trade_date if repair_idx else None,
            first_repair_limit_up=history[repair_idx].limit_up_count if repair_idx else None,
        ))
    return segments

def _find_local_maxima(values: list[int], window: int = 3) -> list[int]:
    """找局部极大值的索引（今日值 > 前后 window 日）。"""
    maxima = []
    for i in range(window, len(values) - window):
        if all(values[i] > values[i-j] for j in range(1, window+1)) \
           and all(values[i] > values[i+j] for j in range(1, window+1)):
            maxima.append(i)
    return maxima

def _find_local_minima(values: list[int], window: int = 3) -> list[int]:
    """找局部极小值的索引（今日值 < 前后 window 日）。"""
    minima = []
    for i in range(window, len(values) - window):
        if all(values[i] < values[i-j] for j in range(1, window+1)) \
           and all(values[i] < values[i+j] for j in range(1, window+1)):
            minima.append(i)
    return minima
```

**LLM 推理示例**（SKILL.md §三第 3 步）：
```
代码提供：上一轮周期段
  - 峰值日 20260715 涨停 80
  - 谷值日 20260722 涨停 15
  - 首次修复日 20260723 涨停 35

当前：今日涨停 45

LLM 推理：
"当前涨停 45 > 上一轮首次修复涨停 35 → 上升周期概率较高（SKILL.md §三第 3 步）
但修复力度不及上一轮峰值 80 的 60%，仍处于修复早期。"
```

**测试用例（2 个，已计入 E.9 的 14 个）**：
13. `test_identify_emotion_cycles_finds_peak_trough`：构造 60 日含明显峰谷 → 正确识别
14. `test_identify_emotion_cycles_returns_empty_when_no_pattern`：历史无峰谷模式 → 返空列表

---

#### Task F: sector_phase_analyzer 新建板块高潮/分歧/抗跌算法

**目标**：新建 [domain/stock/sector_phase_analyzer.py](../../domain/stock/sector_phase_analyzer.py)，实现 3 个算法：

1. `identify_sector_high_phase(sector_history: list[SectorDaily]) -> list[str]`
   - 识别"连续 3 日大涨"的板块（高潮）
2. `identify_sector_divergence(sector_history: list[SectorDaily]) -> list[SectorDivergence]`
   - 高潮后第 4 日涨幅衰减 > 50% 即视为分歧
3. `rank_resistant_sectors(sector_history: list[SectorDaily], market_pct_chg: float) -> list[ResistantSector]`
   - 大盘下跌日，板块跌幅排序，跌幅 < 大盘 × 0.5 即抗跌

**架构位置**：放在 `domain/stock/` 层（纯函数，符合 AGENTS.md §8.1，参照 [domain/stock/heuristics.py](../../domain/stock/heuristics.py) 模式）。

**端口实现**：把 [sqlite_data_source.py](../../infrastructure/stock/sqlite_data_source.py) 的 4 个 stub（`get_sector_heat_distribution` / `get_strong_repair_leaders` / `get_resistant_sectors` / `get_sector_divergence`）改为真实查 SQL + 调 sector_phase_analyzer。

**新增表**：**迁移 v024**（修正：v022 已被 stock_fetch_log 占用，v023 给 Task E 用）新增 `sector_phase_daily` 表存分析结果。

```sql
CREATE TABLE IF NOT EXISTS sector_phase_daily (
    trade_date TEXT NOT NULL,
    sector_name TEXT NOT NULL,
    phase TEXT NOT NULL,          -- high_phase / divergence / resistant
    pct_chg REAL,
    confidence TEXT,
    reason TEXT,
    PRIMARY KEY (trade_date, sector_name, phase)
);
```

**测试**：3 个算法各 2 个单测。

**工作量**：~400 行代码 + schema 迁移 v024 + 6 个单测。

**依赖**：Task C（sector_daily 有数据）。

---

#### Task G: watchlist_scanner 移到 domain 层 + watchlist_service 接入 pipeline

**目标**：

1. **架构修正**：[infrastructure/stock/watchlist_scanner.py](../../infrastructure/stock/watchlist_scanner.py) 的 2 个纯函数移到 [domain/stock/watchlist_heuristics.py](../../domain/stock/watchlist_heuristics.py)（修正架构违规，application 不得 import infrastructure）

2. **新建** [application/stock/watchlist_service.py](../../application/stock/watchlist_service.py)（开发计划 Task 4 要求但未建）

3. **接入 pipeline**：在 [application/stock/pipeline.py](../../application/stock/pipeline.py) 收盘流程后调用 scanner → 写入 watchlist_stocks 表

```python
# domain/stock/watchlist_heuristics.py（从 infrastructure 移过来）
def identify_resistant_stocks(stocks, market_pct_chg, threshold_ratio=0.5):
    """识别抗跌股（纯函数，不依赖 I/O）。"""
    ...

def extract_post_divergence_resistant(divergences, sector_stocks, threshold_ratio=0.5):
    """板块高潮后分歧的板块内抗跌个股。"""
    ...

# application/stock/watchlist_service.py
class WatchlistService:
    """观察池入池服务：收盘后调 scanner 筛选候选股，写入 watchlist_stocks 表。"""

    async def scan_and_persist(self, trade_date: str) -> int:
        # 1. 取当日 stock_daily 全部个股
        stocks = await self._data.get_stock_daily_all(trade_date)
        # 2. 取大盘涨跌幅
        market = await self._data.get_market_snapshot(trade_date)
        # 3. 调 domain 层 scanner（合法依赖）
        from domain.stock.watchlist_heuristics import identify_resistant_stocks
        resistant = identify_resistant_stocks(stocks, market.pct_chg)
        # 4. 写入 watchlist_stocks 表
        # category 字段是 INTEGER（修正：不是字符串）
        self._cache.upsert_watchlist_stocks(
            trade_date=trade_date,
            stocks=resistant,
            category=0,  # 0=resistant, 1=strong_repair, 2=correlation
        )
        return len(resistant)
```

**watchlist_stocks.category 字段编码**（修正：schema 是 INTEGER 不是 TEXT）：

| 值 | 含义 |
|---|---|
| 0 | resistant（抗跌） |
| 1 | strong_repair（强修复） |
| 2 | correlation（庄股/抱团） |

**pipeline.py 改动**：在 `run_close` 函数末尾追加：

```python
async def run_close(self, trade_date: str) -> PipelineResult:
    ...
    # 追加观察池入池
    if self._watchlist_service:
        try:
            await self._watchlist_service.scan_and_persist(trade_date)
        except Exception as e:
            logger.warning("watchlist scan failed: %s", e)
    ...
```

**测试**：mock data_source，断言 watchlist_stocks 表写入行数 > 0。

**工作量**：~150 行代码 + 3 个单测 + 架构迁移。

**依赖**：Task D（stock_daily 有数据）。

---

#### Task H: correlation_analyzer 新建庄股/抱团识别算法

**目标**：新建 [infrastructure/stock/correlation_analyzer.py](../../infrastructure/stock/correlation_analyzer.py)（开发计划 Task 3 要求但未建）。

**架构说明**：[domain/stock/pipeline_ports.py:56-61](../../domain/stock/pipeline_ports.py#L56-L61) 已定义 `CorrelationAnalyzer` Protocol，[application/stock/pipeline.py:53](../../application/stock/pipeline.py#L53) 已接受 `correlation_analyzer` 参数。架构接缝已搭好，**只需实现端口**。

**算法**：基于近 N 日个股 OHLCV 计算相关性矩阵 + 聚类

```python
def identify_correlation_groups(
    stock_daily_history: dict[str, list[StockDaily]],  # stock_code -> 多日日线
    days: int = 7,
    correlation_threshold: float = 0.85,
) -> CorrelationResult:
    """识别庄股/抱团股。

    算法：
    1. 计算所有股票对近 N 日 pct_chg 的 Pearson 相关系数
    2. 相关系数 > threshold 的股票对视为"同涨同跌"
    3. 用 Union-Find 聚类：同涨同跌股票数 ≥ 3 即为一个抱团组
    4. 输出 individual_stocks（独立庄股）+ clustered_groups（抱团组）
    """
    # 1. 构建相关性矩阵
    # 2. Union-Find 聚类
    # 3. 输出 CorrelationResult
```

**端口实现**：把 [sqlite_data_source.py](../../infrastructure/stock/sqlite_data_source.py) 的 `get_correlation` stub 改为真实查 SQL + 调用 correlation_analyzer。

**组合根改动**：[app.py](../../app.py) 把 `correlation_analyzer=None` 改为真实实例注入。

**新增表**：**迁移 v025**（修正：v022 已占用，v023 给 Task E，v024 给 Task F）新增 `correlation_groups` 表存分析结果。

```sql
CREATE TABLE IF NOT EXISTS correlation_groups (
    trade_date TEXT NOT NULL,
    group_id TEXT NOT NULL,          -- 抱团组 ID
    stock_codes TEXT NOT NULL,       -- JSON 数组
    correlation_score REAL,
    group_type TEXT NOT NULL,        -- cluster / individual
    PRIMARY KEY (trade_date, group_id)
);
```

**调度器改动**：周五链式 correlation 触发时调用此模块（[application/scheduler.py](../../application/scheduler.py) 已有 `run_stock_close_fetch` 的周五链式逻辑）。

**测试**：构造 5 只高度相关股票 + 5 只独立股票，断言聚类结果正确。

**工作量**：~300 行代码 + schema 迁移 v025 + 4 个单测。

**依赖**：Task D（stock_daily 有数据）。

---

#### Task I: review_service 接入真实数据

**目标**：[application/stock/review_service.py](../../application/stock/review_service.py) 的 `_build_user_prompt` 当前调 stub 端口拿到空数据，Task E/F/G/H 完成后端口会返回真实数据。

**改动**：
- 确认 review_service 已调 `get_strong_repair_leaders` / `get_resistant_sectors` / `get_sector_heat_distribution` / `get_sector_divergence` / `get_correlation`
- 补充 user_prompt 中这些数据的格式化函数
- 确认复盘文 LLM 输出含真实内容（不是"数据缺失"）
- **对成交额历史数据缺失**：在 user_prompt 中明确标注"成交额数据自 X 日起新增，之前缺失"

**测试**：集成测试用 fake data_source 返回真实数据，断言复盘文含板块名称、股票代码、阶段判定等真实内容。

**工作量**：~100 行代码 + 2 个集成测试。

**依赖**：Task E/F/G/H 全部完成。

---

### 3.4 不做的内容（明确边界）

1. **板块分时涨停分布**：akshare 无免费接口提供历史分时板块涨停数据 → 降级为"日级别"判定（连续大涨 ≥ N 日即视为高潮），不做分时
2. **两市成交额历史回填**：`stock_zh_index_spot_em` 只返回当天，**历史无法回填** → 修复后逐日累积，历史日期标注"成交额数据缺失（接口限制）"
3. **不使用 `stock_zh_index_daily.volume` 作成交额**：实测是指数成交量（差 9.1 倍），不是成交额
4. **不使用 `stock_zh_index_daily_tx.amount` 作成交额**：实测差 911 倍，不可用
5. **换数据源不引入新依赖**：同花顺/腾讯接口都在 akshare 内，不新增 requirements
6. **不修改历史迁移**：v021/v022 不动，新增 v023/v024/v025
7. **不重构现有架构**：保持端口/组合根/分层依赖不变，只补实现 + watchlist_scanner 迁移

---

### 3.5 风险与应对

| 风险 | 应对 |
|---|---|
| 同花顺/腾讯接口也被反爬 | fetcher 串行调用 + 1-2 秒 sleep + 失败重试 2 次（AGENTS.md §5.3） |
| 板块 90 个串行调接口慢（~3-4 分钟） | 接受现状，作为后台任务不影响登录（已用 `asyncio.create_task` 后台跑） |
| 个股 K 线换腾讯后仍有失败 | 接受部分缺失，记录到 stock_fetch_log，复盘文标注"该股数据缺失" |
| 两市成交额历史无法回填 | 复盘文明确标注"成交额数据自 X 日起新增"，不臆测历史 |
| 6 维度分类阈值不准 | 阈值硬编码在 emotion_dimensions.py，可调整；先实现再迭代；不做阶段判定（LLM 受约束推理） |
| 庄股/抱团算法复杂 | 用简化版 Pearson + Union-Find，不引入 sklearn |
| 新增迁移 v023/v024/v025 | 不修改历史迁移，回滚脚本必须配套（AGENTS.md §4） |
| watchlist_scanner 架构迁移 | 从 infrastructure 移到 domain，保持纯函数；同步更新测试 import 路径 |

---

### 3.6 验收标准

每个 Task 完成后必须满足：

1. **测试**：先写失败测试 → 实现 → 测试转绿
2. **门禁**（AGENTS.md §6 + §8.4）：
   ```powershell
   python scripts/check_architecture.py
   python -m ruff check .
   python -m mypy api application domain infrastructure
   python -m bandit -r api application domain infrastructure -lll
   python -m pytest --cov=api --cov=application --cov=domain --cov=infrastructure --cov-fail-under=70
   ```
3. **数据库实测**：对应表行数 > 0（不是 0 行）
4. **复盘文实测**：生成复盘文后，对应章节不再是"数据缺失"
5. **commit 规范**（AGENTS.md §9）：中文提交信息 + scope=stock + body 声明组合根/迁移改动

---

## 四、实施计划总览

| Task | 内容 | 工作量 | 依赖 | 优先级 |
|---|---|---|---|---|
| A | 修 pct_chg 字段 None bug | 小 | 无 | P0 |
| B | emotion_daily_fetcher 降级 + 边界修复 | 中 | 无 | P0 |
| C | sector_daily_fetcher 换源（同花顺） | 中 | 无 | P0 |
| D | stock_daily_fetcher 换源（腾讯） | 中 | 无 | P0 |
| A2 | board_ladder_daily 聚合写入 | 小 | 无（limit_stocks 已有数据） | P0 |
| E | 6 维度情绪观察框架 + 迁移 v023 | 大 | B + D | P1 |
| F | 板块高潮/分歧/抗跌算法 + 迁移 v024 | 大 | C | P1 |
| G | watchlist_scanner 迁移 + watchlist_service | 中 | D | P1 |
| H | 庄股/抱团识别算法 + 迁移 v025 | 大 | D | P2 |
| I | review_service 接入真实数据 | 小 | E/F/G/H | P2 |

**建议顺序**：

1. **第一波**（P0，让数据层可用）：A → B → C → D → A2
2. **第二波**（P1，补算法）：E → F → G
3. **第三波**（P2，收尾）：H → I

每个 Task 完成后**独立 commit**，commit message 遵循 AGENTS.md §9 中文规范。

---

## 五、附录

### 5.1 akshare 接口实测结果（2026-08-01）

| 接口 | 数据源 | 状态 | 用途 | 备注 |
|---|---|---|---|---|
| `stock_zt_pool_em` | 东财 | ✅ 可用 | 涨停股池 | 一直稳定 |
| `stock_zh_index_daily` | 新浪 | ✅ 可用 | 大盘指数 OHLCV | **volume 不是成交额** |
| `stock_market_activity_legu` | 乐股 | ✅ 可用 | 当日涨跌停数 | 仅当日截面，不含成交额 |
| `stock_board_industry_name_ths` | 同花顺 | ✅ 可用 | 90 个板块列表 | |
| `stock_board_industry_index_ths` | 同花顺 | ✅ 可用 | 板块历史 OHLCV+成交额 | 带日期参数 |
| `stock_zh_a_hist_tx` | 腾讯 | ✅ 可用 | 个股历史 OHLCV | 带日期参数 |
| `stock_fund_flow_individual` | 同花顺 | ✅ 可用 | 个股资金流 | |
| `stock_fund_flow_industry` | 同花顺 | ✅ 可用 | 板块资金流+领涨股 | |
| `stock_zh_index_spot_em` | 东财 | ⚠️ 不稳定（~50%） | 两市成交额 | **仅当日，不带日期参数** |
| `stock_zh_index_daily_em` | 东财 | ❌ 反爬失败 | （弃用） | |
| `stock_board_industry_name_em` | 东财 | ❌ 反爬失败 | （弃用） | |
| `stock_zh_a_hist` | 东财 | ❌ 反爬失败 | （弃用） | |
| `stock_individual_fund_flow` | 东财 | ❌ 反爬失败 | （弃用） | |

### 5.2 受影响文件清单

**修改**：
- [infrastructure/stock/akshare_client.py](../../infrastructure/stock/akshare_client.py) — Task A/B/C/D/E（E 新增 `fetch_top20_volume_stocks`）
- [infrastructure/stock/emotion_daily_fetcher.py](../../infrastructure/stock/emotion_daily_fetcher.py) — Task B/E（E 调 6 维度计算）
- [infrastructure/stock/sector_daily_fetcher.py](../../infrastructure/stock/sector_daily_fetcher.py) — Task C
- [infrastructure/stock/stock_daily_fetcher.py](../../infrastructure/stock/stock_daily_fetcher.py) — Task D
- [infrastructure/stock/sqlite_data_source.py](../../infrastructure/stock/sqlite_data_source.py) — Task F/H/I
- [domain/stock/heuristics.py](../../domain/stock/heuristics.py) — Task E（保留现有 3 个聚合函数，不扩展 classify_emotion_phase）
- [application/stock/pipeline.py](../../application/stock/pipeline.py) — Task G
- [application/stock/review_service.py](../../application/stock/review_service.py) — Task I
- [app.py](../../app.py) — Task H（组合根注入）
- [domain/stock/ports.py](../../domain/stock/ports.py) — Task F/H（如需新增端口方法）
- [domain/stock/models.py](../../domain/stock/models.py) — Task B/E（B: EmotionRawData.total_volume 改 Optional；E: EmotionRawData 扩展 18 个字段）

**新建**：
- [domain/stock/emotion_dimensions.py](../../domain/stock/emotion_dimensions.py) — Task E（6 个 compute_* 函数 + 2 个字符串解析辅助函数，纯函数）
- [domain/stock/emotion_cycles.py](../../domain/stock/emotion_cycles.py) — Task E（峰谷检测 + 周期段识别，纯函数）
- [domain/stock/sector_phase_analyzer.py](../../domain/stock/sector_phase_analyzer.py) — Task F
- [domain/stock/watchlist_heuristics.py](../../domain/stock/watchlist_heuristics.py) — Task G（从 infrastructure 迁移）
- [application/stock/watchlist_service.py](../../application/stock/watchlist_service.py) — Task G
- [infrastructure/stock/correlation_analyzer.py](../../infrastructure/stock/correlation_analyzer.py) — Task H
- [infrastructure/stock/board_ladder_fetcher.py](../../infrastructure/stock/board_ladder_fetcher.py) — Task A2
- [infrastructure/persistence/migrations/v023_025.py](../../infrastructure/persistence/migrations/v023_025.py) — Task E（emotion_daily 新增 18 字段）
- [infrastructure/persistence/migrations/v024_025.py](../../infrastructure/persistence/migrations/v024_025.py) — Task F（sector_phase_daily 表）
- [infrastructure/persistence/migrations/v025_025.py](../../infrastructure/persistence/migrations/v025_025.py) — Task H（correlation_groups 表）

**删除**：
- [infrastructure/stock/watchlist_scanner.py](../../infrastructure/stock/watchlist_scanner.py) — Task G（迁移到 domain 后删除原文件）

### 5.3 测试文件清单

- `tests/unit/stock/test_akshare_client.py` — Task A/B/C/D/E
- `tests/unit/stock/test_emotion_dimensions.py` — Task E（新建，12 个测试用例）
- `tests/unit/stock/test_emotion_cycles.py` — Task E（新建，2 个测试用例：峰谷检测 + 空模式）
- `tests/unit/stock/test_heuristics.py` — Task B/E（保留现有 3 个聚合函数测试）
- `tests/unit/stock/test_sector_phase_analyzer.py` — Task F（新建）
- `tests/unit/stock/test_watchlist_heuristics.py` — Task G（新建，替代原 test_watchlist_scanner）
- `tests/unit/stock/test_watchlist_service.py` — Task G（新建）
- `tests/unit/stock/test_correlation_analyzer.py` — Task H（新建）
- `tests/unit/stock/test_board_ladder_fetcher.py` — Task A2（新建）
- `tests/integration/stock/test_review_pipeline.py` — Task I（扩展）

### 5.4 累计变更说明

#### v2.0 相对 v1.0 的修正

| # | v1.0 问题 | v2.0 修正 |
|---|---|---|
| 错误 1 | Task B 用 `stock_zh_index_daily.volume` 作成交额 | 改为保留 spot_em + 降级处理；明确历史无法回填 |
| 错误 2 | 迁移版本号 v022/v023 | 修正为 v023（Task F）/ v024（Task H），v022 已被 stock_fetch_log 占用 |
| 错误 3 | watchlist_stocks.category 用字符串 | 修正为 INTEGER 编码（0/1/2） |
| 错误 4 | Task B 现状描述"100% 失败" | 修正为"spot_em 不稳定（~50%），legu 稳定" |
| 错误 5 | 腾讯 amount 作成交额 | 明确删除该方案，腾讯 amount 差 911 倍不可用 |
| 错误 6 | Task E 依赖循环 | 明确分两档：单日判定可立即跑，多日趋势需积累 5-10 日<br>**⚠️ v2.6 已重构**：Task E 改为 6 维度框架，依赖 Task B + Task D，不再有依赖循环 |
| 问题 1 | Task G 架构违规（application → infrastructure） | 明确 watchlist_scanner 从 infrastructure 移到 domain/stock/watchlist_heuristics.py |
| 问题 2 | Task H 端口描述不准 | 修正为"实现已有的 CorrelationAnalyzer Protocol" |
| 遗漏 1 | board_ladder_daily 表无 fetcher | 新增 Task A2 从 limit_stocks_daily 聚合 |
| 遗漏 2 | 无 limit_stocks 跳过逻辑 | Task B 方案补充此边界条件（涨停为 0 也写入） |
| 遗漏 3 | 性能低估 | 修正为 90 板块 ~3-4 分钟，99 股 ~3-5 分钟 |

#### v2.1 相对 v2.0 的修正

| # | v2.0 问题 | v2.1 修正 |
|---|---|---|
| 设计错误 1 | Task E 用绝对阈值判定阶段（涨停<20、>60 等） | 改为相对分位数判定（当日值在近 20 日序列中的分位） |
| 设计错误 2 | Task E 阶段判定不分牛熊市 | 相对化自动适应牛熊市（牛市冰点涨停可能 30 只，熊市高潮可能 25 只） |
| 设计错误 3 | Task E 冷启动期 confidence=high | 冷启动 confidence 必须为 low（绝对阈值可能严重失真） |
| 接口变化 | Task E 函数签名 `classify_emotion_phase(today, prev_trend=None)` | 改为 `classify_emotion_phase(today, history)`，history 必填（冷启动传空列表） |
| 工作量变化 | Task E ~200 行 | Task E ~280 行（新增 `_percentile` + 冷启动兜底 + 7 个测试） |
| 依赖变化 | Task E 需 5-10 日数据 | Task E 需 5 日起步（low）/ 20 日推荐（high） |
| 测试变化 | Task E 6 个测试 | Task E 7 个测试（含"同 today 不同 history 判出不同阶段"关键断言） |

#### v2.2 相对 v2.1 的修正（方向性纠偏，已被 v2.6 取代）

| # | v2.1 问题 | v2.2 修正 |
|---|---|---|
| 方向错误 1 | 代码 `classify_emotion_phase()` 返回阶段字符串 | 删除该函数；代码不判定阶段，LLM 基于 SKILL.md 自判 |
| 方向错误 2 | 违背 SKILL.md §0"启发式框架非硬规则" | 代码只提供数据（分位数+周期对比），LLM 做启发式判断 |
| 方向错误 3 | phase 写入 emotion_daily 表 | phase/phase_confidence/phase_reason 保持 None，不预存 |
| 方向错误 4 | 无法处理"混沌"场景（SKILL.md §2.1 信号矛盾） | LLM 自己识别混沌，降低置信度 |
| 方向错误 5 | 代码无法感知大盘维度（SKILL.md §0.5） | LLM 综合大盘/情绪/板块多维度自判 |
| 遗漏 1 | 未覆盖 SKILL.md §三第 3 步"与上一轮退潮比" | 新增 `get_previous_cycle_comparison` 工具 |
| 接口变化 | `classify_emotion_phase(today, history)` | 改为 `get_emotion_percentile(date)` + `get_previous_cycle_comparison(date)` 两个数据查询工具 |
| 工作量变化 | ~280 行 | ~180 行（减少 100 行，去掉判定函数） |
| 测试变化 | 7 个测试（含阶段判定断言） | 5 个测试（只测数据查询正确性，不测阶段判定） |

**⚠️ v2.2 的局限**：LLM 完全自判阶段会导致复盘质量不稳定；单维度（涨停数分位）判情绪仍是刻舟求剑；未识别市场风格切换。v2.6 已修正这些问题。

#### v2.6 相对 v2.2 的修正（6 维度框架，彻底解决刻舟求剑）

| # | v2.2 问题 | v2.6 修正 |
|---|---|---|
| 设计错误 1 | 单维度（涨停数分位）判情绪，市场风格切换时刻舟求剑 | 6 维度组合观察（高度/广度/强度/韧性/真实度/持续性） |
| 设计错误 2 | LLM 完全自判阶段，质量不稳定 | 代码做维度分类（阈值硬编码），LLM 受约束推理 |
| 设计错误 3 | 不识别市场风格 | 自动识别 5 种风格（题材股/趋势股/共振/弱势/混合） |
| 设计错误 4 | 未识别"5+4 修复模式" | 韧性维度（断板反包 + 5 日累计涨幅）识别 |
| 设计错误 5 | 情绪广度未观察 | 新增涨跌家数比（普涨/偏广/平衡/偏窄/普跌） |
| 遗漏 1 | 趋势股主导时复盘失效 | market_style=趋势股主导时跳过情绪周期框架 |
| 接口变化 | `get_emotion_percentile` + `get_previous_cycle_comparison` | emotion_daily 表扩展 18 字段 + 6 个 compute_* 函数 |
| 工作量变化 | ~180 行 | ~350 行 |
| 测试变化 | 5 个 | 12 个（6 维度分类边界值测试） |
| 迁移变化 | 无 | 新增迁移 v023（18 个字段） |
| 迁移冲突 | — | Task F 改用 v024，Task H 改用 v025 |

#### v2.6.1 相对 v2.6 的修正（自检后修正 7 处问题）

| # | v2.6 问题 | v2.6.1 修正 |
|---|---|---|
| 错误 1 | 维度 3 用 `pct_chg` 字段名（实测字段名是 `涨跌幅`，且是字符串） | 改为 `涨跌幅` + 新增 `_parse_pct_str` 解析 "20.01%" → 20.01 |
| 错误 2 | 维度 3 用 `sort_by("成交额")` 排序（成交额是字符串，字典序错） | 改为 `nlargest(20, "_amount")` + 新增 `_parse_amount_str` 解析 "3.35亿" |
| 错误 3 | 维度 2 用 `上涨家数`/`下跌家数` 字段名（实测是 `上涨`/`下跌`） | 改为复用 `_df_to_int(activity_df, "上涨")` |
| 错误 4 | E.6 调 `get_emotion_indicators(date-1)` 但昨日数据无维度分类 | 改为 `get_emotion_indicators_trend(date, 5)` 拿多日序列（含分类字段） |
| 错误 5 | E.5 矛盾规则只有 4 条，覆盖不全 | 扩展到 8 条（新增退潮信号/修复信号/系统性风险/混合） |
| 错误 6 | E.8 说"第 3 步简化为 trend_5d"（trend_5d 不能替代周期对比） | 保留第 3 步周期对比，新增 E.10 `identify_emotion_cycles` 做峰谷检测 |
| 错误 7 | E.9 工作量 350 行低估（akshare 字符串解析 + 周期段识别漏算） | 修正为 410 行（含 emotion_cycles.py + 字符串解析辅助函数） |

### 5.5 数据可行性限制总结（关键边界）

以下限制在实施过程中必须遵守，不得通过技术手段绕过：

1. **两市成交额历史无法回填**：`stock_zh_index_spot_em` 仅返回当天数据；`stock_zh_index_daily.volume` 和 `stock_zh_index_daily_tx.amount` 实测均不是成交额（分别差 9.1 倍和 911 倍）。修复后只能逐日累积，历史日期必须标注"成交额数据缺失（接口限制）"。

2. **板块分时涨停分布无数据源**：akshare 无免费接口提供历史分时板块涨停数据。降级为"日级别"判定（连续大涨 ≥ N 日即视为高潮）。

3. **情绪阶段判定不由代码做，但维度分类由代码做（v2.6 修正）**：Task E 不写 `classify_emotion_phase` 函数，emotion_daily 表的 phase 字段保持 None。但代码做维度分类（height_level / breadth_level / strength_level / resilience_level / authenticity_level / market_style / trend_5d/20d），阈值硬编码无 AI 发挥空间。LLM 基于 6 维度分类 + 8 条矛盾强制规则受约束推理，不允许自由发挥或输出阶段标签。代码同时做周期段峰谷检测（`identify_emotion_cycles`，v2.6.1 新增），为 SKILL.md §三第 3 步"与上一轮退潮比"提供客观数据。

4. **akshare 反爬不可控**：同花顺/腾讯接口目前可用，但可能随时被封。fetcher 必须有失败降级处理，复盘文必须能标注"该维度数据缺失"。

5. **Task E 依赖 Task D**：韧性维度（断板反包 + 5 日累计涨幅）需要 stock_daily 数据。若 Task D 未完成，Task E 只能实现 5 维度（缺韧性），复盘文需标注"韧性维度数据缺失"。

6. **迁移版本号已修正**：v023（Task E 用，18 个字段）→ v024（Task F 用，sector_phase_daily 表）→ v025（Task H 用，correlation_groups 表）。不得复用已存在的 v022（stock_fetch_log）。

---

**文档结束**

本文档作为修复工作的基线，每个 Task 完成后应在 PR 描述中引用本文档对应章节。
v2.6.1 自检修正 v2.6 的 7 处问题（字段名错、矛盾规则不全、第 3 步废弃错误、新增周期段识别等），
v2.6 重构 Task E 为 6 维度情绪观察框架（解决单维度刻舟求剑 + LLM 自判质量不稳定），
v2.2 修正 Task E 设计方向（代码不判定阶段，已被 v2.6 取代），
v2.1 修正 Task E 算法（绝对阈值→相对分位数，已被 v2.6 取代），
v2.0 修正 v1.0 的全部已知技术错误，可作为实施依据。
