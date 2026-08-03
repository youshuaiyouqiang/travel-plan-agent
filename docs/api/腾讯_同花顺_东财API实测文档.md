# 腾讯 / 同花顺 / 东财 API 实测文档（接口可用性盘点）

> **用途**：本文件作为 AI 引用股票复盘 Agent 数据源接口的**权威参考物**。
> 所有字段、样例数据均来自**真实调用 akshare 1.18.79** 的输出（非推测、非文档摘录）。
>
> **实测环境（重要，影响结果解读）**
> - akshare 版本：`1.18.79`（由 `.venv` 提供，Python 3.14.6 运行时）
> - 实测日期（程序运行）：**2026-08-02（周日，非交易日）**
> - 取样交易日标签：`2026-07-31`（部分接口在交易日曾成功，见下）
> - 调用方式：经 `infrastructure/stock/akshare_client.py` 使用的同一 `akshare` 库，禁用 tqdm 后直连上游服务器
>
> **⚠️ 实测结果判读须知（务必先读）**
> 本次实测在**周日非交易日**进行，且**东方财富存在反爬**（批量请求时约 50% 概率 `ConnectionError: RemoteDisconnected`）。这导致两类"失败"：
> 1. **时段性失败**：日线 / 板块 K 线 / 资金流等接口在非交易日返回空 DataFrame，akshare 解析空表时抛 `IndexError` / `Length mismatch` / `KeyError`。**这不代表接口不可用**——同一接口在交易日（2026-07-31）首轮实测中已成功返回数据（见本文第 2 节原始凭证）。
> 2. **反爬失败**：东财 `_em` 系列在连续请求时被远程断开。需加退避（如 `time.sleep(0.3)` 已被项目采用）或单接口隔离调用。
>
> 因此本文对每个接口标注三种状态之一：
> - **✅ 实测成功**（本次或交易日首轮真实返回字段）
> - **⏳ 接口存在/交易日可用**（本次因非交易日或反爬空返回，但函数存在且交易日可正常取数）
> - **❌ 参数错误/本次未取到**（函数存在，但本次因参数猜测错误或反爬未取到；需正确参数重试）
> - **📋 未逐一实测**（函数存在但本次未调用，按功能分类列出，供 AI 检索是否存在某类数据）

---

## 0. 数据来源与接入状态总览

| 上游来源 | akshare 转发函数总数（stock_*） | 项目已接入 | 本次重点实测 |
|---|---|---|---|
| 腾讯 (tx) | 4 | 2（个股K线、指数日K） | 4 个全部探测 |
| 同花顺 (ths) | 38 | 3（行业板块列表/板块K线/个股资金流） | 精选 19 个探测 |
| 东方财富 (em/legu) | 203 | 2（涨停池、涨跌停炸板） | 精选 33 个探测 |
| 新浪 (sina) | 14（归入东财族） | 0 | 未逐一实测 |

> 字段中文名保持 akshare 原始返回。腾讯系列接口**均不返回 `pct_chg`**，需自算（项目已在 `akshare_client.py` 处理）。
> 同花顺 `_ths` 与东财 `_em` 同名概念/行业接口并存，字段结构不同，接入时需分别处理。

---

## 1. 腾讯接口（共 4 个，全部探测）

| 函数 | 实测状态 | 返回字段 / 说明 |
|---|---|---|
| `stock_zh_a_hist_tx` | ✅ 交易日成功 / ⏳ 本次非交易日空返回 | 个股日K：`date, open, close, high, low, volume, turnover(换手率0-1), amount(成交额)`。注意 `turnover`≠成交额。`start_date`/`end_date` 用 `YYYYMMDD` |
| `stock_zh_index_daily_tx` | ✅ 交易日成功 / ⏳ 本次空返回 | 指数日K：`date, open, high, low, close, volume`，无 pct_chg |
| `stock_zh_a_spot_tx` | ✅ **本次成功** | 沪深A股实时截面 **27 列**：`code, name, zxj(最新价), zdf(涨跌幅), zf(涨幅), zdf_d5/d10/d20/d60/w52/y(各周期涨跌), hsl(换手率), lb(量比), ltsz(流通市值), zsz(总市值), pe_ttm, zljlr(主力净流入), zllr(主力流入), zllc(主力流出), speed(涨速), turnover, volume, stock_type, state, pn, zd` 等。复盘可用维度极丰富（含各周期涨幅、主力资金） |
| `stock_zh_a_tick_tx_js` | ✅ **本次成功** | 个股 tick 分笔：`成交时间, 成交价格, 价格变动, 成交量, 成交金额, 性质(买盘/卖盘)`，本次返回 4300 行 |

**腾讯小结**：4 个接口全部函数存在且可用。`stock_zh_a_spot_tx` 是**被低估的黄金接口**——一次返回全市场 27 维实时快照（含主力资金、各周期涨幅），比逐个调东财 spot 更稳，建议优先用于盘面广度/强度复盘。

---

## 2. 同花顺接口（共 38 个，精选 19 个探测 + 其余分类列出）

### 2.1 板块 / 概念（✅ 交易日成功，⏳ 本次非交易日空返回）

| 函数 | 状态 | 字段 |
|---|---|---|
| `stock_board_industry_name_ths` | ✅ 交易日成功（90行） | `name, code`（行业板块） |
| `stock_board_industry_index_ths` | ✅ 交易日成功（4行） | `日期, 开盘价, 最高价, 最低价, 收盘价, 成交量, 成交额`（无 pct_chg） |
| `stock_board_industry_summary_ths` | ⏳ 本次空返回 | 行业板块汇总（交易日可用） |
| `stock_board_industry_info_ths` | ✅ **本次成功**（10行） | `项目, 值`（今开/昨收/涨跌幅等板块概况） |
| `stock_board_concept_name_ths` | ✅ 交易日成功（351行） | `name, code`（概念板块，比行业更细） |
| `stock_board_concept_index_ths` | ⏳ 本次空返回 | 概念板块K线（交易日可用） |
| `stock_board_concept_summary_ths` | ⏳ 本次空返回 | 概念板块汇总 |
| `stock_board_concept_cons_ths` | 📋 未实测（函数名缺失于当前环境，需确认） | 概念板块成分股 |

### 2.2 资金流 / 排名（⏳ 本次非交易日空返回，交易日可用）

| 函数 | 状态 | 说明 |
|---|---|---|
| `stock_fund_flow_individual` | ✅ 交易日成功（5197行） | 个股资金流：`序号, 股票代码, 股票简称, 最新价, 涨跌幅(带%), 换手率(带%), 流入资金(带亿), 流出资金(带亿), 净额(带万), 成交额(带亿)`。**字符串型需解析** |
| `stock_rank_ljqd_ths` | ⏳ 本次空返回 | 量价齐升排名 |
| `stock_rank_cxg_ths` | ⏳ 本次空返回 | 创新高排名 |
| `stock_rank_xstp_ths` | ⏳ 本次空返回 | 小探tp排名（新高类） |
| `stock_rank_ljqs_ths` | ⏳ 本次空返回 | 量价齐升排名 |
| `stock_rank_lxxd_ths` | ⏳ 本次空返回 | 连续下跌排名 |
| `stock_rank_lxsz_ths` | ⏳ 本次空返回 | 连续上涨排名 |
| `stock_rank_cxfl_ths` | 📋 未实测 | 持续放量排名 |
| `stock_rank_cxd_ths` | 📋 未实测 | 持续下跌排名 |
| `stock_rank_xzjp_ths` | 📋 未实测 | 险资举牌排名 |

### 2.3 财务 / 基本面（📋 未实测，与每日复盘无关，归档备查）

`stock_financial_abstract_ths`, `stock_financial_abstract_new_ths`, `stock_financial_benefit_ths`, `stock_financial_benefit_new_ths`, `stock_financial_cash_ths`, `stock_financial_cash_new_ths`, `stock_financial_debt_ths`, `stock_financial_debt_new_ths`, `stock_fhps_detail_ths`, `stock_fhps_detail_ths`, `stock_hk_fhpx_detail_ths`, `stock_info_global_ths`, `stock_ipo_ths`, `stock_ipo_benefit_ths`, `stock_ipo_hk_ths`, `stock_management_change_ths`, `stock_profit_forecast_ths`, `stock_shareholder_change_ths`, `stock_xgsr_ths`, `stock_zyjs_ths`（✅ 本次成功：主营业务/产品/经营范围，1行）

> 同花顺财务类接口本次未逐一实测；`stock_zyjs_ths` 实测可用（个股主营业务，复盘"题材归类"可用）。

---

## 3. 东方财富接口（共 203 个，精选 33 个探测）

### 3.1 涨停 / 跌停 / 炸板池（✅ 本次成功，复盘核心）

| 函数 | 状态 | 字段要点 |
|---|---|---|
| `stock_zt_pool_em` | ✅ 成功（99行） | 涨停池：`代码,名称,涨跌幅,最新价,成交额,流通市值,总市值,换手率,封板资金,首次封板时间,最后封板时间,炸板次数,涨停统计,连板数,所属行业`（16列） |
| `stock_zt_pool_strong_em` | ✅ 成功（64行） | 强势涨停池：多 `涨停价/涨速/是否新高/量比/入选理由` |
| `stock_zt_pool_previous_em` | ✅ 成功（52行） | 昨日涨停今日表现：多 `振幅/昨日封板时间/昨日连板数`（连板晋级率核心） |
| `stock_zt_pool_sub_new_em` | ✅ 成功（143行） | 次新涨停池：多 `转手率/开板几日/开板日期/上市日期`（注意列名是`转手率`非`换手率`） |
| `stock_zt_pool_zbgc_em` | ✅ 成功（107行） | 炸板池：多 `涨停价/涨速/首次封板时间/炸板次数/振幅` |
| `stock_zt_pool_dtgc_em` | ✅ 成功（**0行 0列**） | 跌停池：该交易日无跌停，返回空表。**解析前需判空** |

### 3.2 市场情绪 / 涨跌停计数

| 函数 | 状态 | 字段 |
|---|---|---|
| `stock_market_activity_legu` | ✅ 成功（12行） | `item, value`（上涨/涨停/跌停/炸板等12项） |

### 3.3 实时截面 / 指数（❌ 本次反爬失败，交易日+退避可用）

| 函数 | 状态 | 说明 |
|---|---|---|
| `stock_zh_index_spot_em` | ❌ 反爬失败 | 指数实时。项目已降级处理 |
| `stock_board_industry_name_em` | ❌ 反爬失败 | 东财行业板块列表（与同花顺并存） |
| `stock_board_industry_spot_em` | ❌ 反爬失败 | 东财行业板块实时 |
| `stock_board_concept_name_em` | ❌ 反爬失败 | 东财概念板块列表 |
| `stock_board_concept_spot_em` | ❌ 反爬失败 | 东财概念板块实时 |
| `stock_zh_a_spot_em` | ❌ 反爬失败 | 沪深A股实时 |
| `stock_sh_a_spot_em` / `stock_sz_a_spot_em` / `stock_cy_a_spot_em` | ❌ 反爬失败 | 沪/深/创业板块实时 |

> **替代建议**：东财实时截面反爬严重，建议改用 **腾讯 `stock_zh_a_spot_tx`**（本次实测稳定成功，27列全市场快照）。

### 3.4 热度 / 资金（✅ 本次成功）

| 函数 | 状态 | 字段 |
|---|---|---|
| `stock_hot_rank_em` | ✅ 成功（100行） | `当前排名, 代码, 股票名称, 最新价, 涨跌额, 涨跌幅`（人气榜） |
| `stock_hot_up_em` | ✅ 成功（100行） | `排名较昨日变动, 当前排名, 代码, 股票名称, 最新价, 涨跌额, 涨跌幅`（人气上升榜） |
| `stock_hsgt_fund_flow_summary_em` | ✅ 成功（4行） | 沪深港通资金：`交易日,类型,板块,资金方向,成交净买额,资金净流入,上涨数,下跌数,相关指数,指数涨跌幅` |

### 3.5 解禁 / 股东 / 主营（✅ 本次成功）

| 函数 | 状态 | 字段 |
|---|---|---|
| `stock_restricted_release_summary_em` | ✅ 成功（29行） | 解禁汇总：`解禁时间,当日解禁股票家数,解禁数量,实际解禁数量,实际解禁市值,沪深300指数,沪深300指数涨跌幅` |
| `stock_zyjs_ths` | ✅ 成功（同花顺，1行） | 主营业务/产品/经营范围 |
| `stock_account_statistics_em` | ✅ 成功（101行） | 投资者账户统计：`数据日期,新增投资者,期末投资者,沪深总市值,沪深户均市值,上证指数收盘,上证指数涨跌幅` |

### 3.6 龙虎榜 / 个股明细（❌ 本次参数错误/反爬，需正确参数）

| 函数 | 状态 | 说明 |
|---|---|---|
| `stock_lhb_detail_em` | ❌ 参数错误（`date` 不接受） | 龙虎榜明细，正确参数需查签名 |
| `stock_lhb_yybph_em` | ❌ 参数错误 | 营业部排行 |
| `stock_lhb_stock_statistic_em` | ❌ 参数错误 | 个股龙虎榜统计 |
| `stock_individual_info_em` | ❌ 反爬失败 | 个股信息 |
| `stock_intraday_em` | ❌ 反爬失败 | 个股分时 |
| `stock_bid_ask_em` | ❌ 反爬失败 | 个股五档盘口 |
| `stock_comment_em` | ❌ 参数错误 | 个股评论 |
| `stock_gdfx_top_10_em` | ❌ 参数错误（`sdgd` KeyError） | 前十大股东 |

### 3.7 财报 / IPO / 回购等（❌ 本次空返回，与每日复盘无关）

`stock_yjbb_em`(业绩报表), `stock_yjkb_em`(业绩快报), `stock_yjyg_em`(业绩预告), `stock_qbzf_em`(全屏增发), `stock_repurchase_em`(回购), `stock_ipo_review_em`(IPO审核), `stock_new_a_spot_em`(新股), `stock_zcfz_em`(资产负债表), `stock_lrb_em`(利润表), `stock_xjll_em`(现金流), `stock_financial_analysis_indicator_em` 等——本次空返回（财报期/参数），属低频基本面数据，**不适合每日复盘热路径**。

### 3.8 东财其余接口（📋 未逐一实测，按功能索引，供检索）

- **龙虎榜族**：`stock_lhb_detail_daily_sina`, `stock_lhb_ggtj_sina`, `stock_lhb_hyyyb_em`(活跃营业部), `stock_lhb_jgmmtj_em`(机构买卖), `stock_lhb_jgmx_sina`, `stock_lhb_jgstatistic_em`(机构统计), `stock_lhb_jgzz_sina`, `stock_lhb_stock_detail_em`, `stock_lhb_stock_detail_date_em`, `stock_lhb_traderstatistic_em`, `stock_lhb_yyb_detail_em`(营业部明细), `stock_lhb_yytj_sina`
- **沪深港通族**：`stock_hsgt_board_rank_em`, `stock_hsgt_fund_min_em`, `stock_hsgt_hist_em`, `stock_hsgt_hold_stock_em`, `stock_hsgt_individual_detail_em`, `stock_hsgt_individual_em`, `stock_hsgt_institution_statistics_em`, `stock_hsgt_sh_hk_spot_em`, `stock_hsgt_stock_statistics_em`
- **板块历史/K线**：`stock_board_change_em`, `stock_board_industry_cons_em`, `stock_board_industry_hist_em`, `stock_board_industry_hist_min_em`, `stock_board_concept_cons_em`, `stock_board_concept_hist_em`, `stock_board_concept_hist_min_em`
- **指数**：`stock_zh_index_daily_em`, `stock_zh_index_spot_em`, `stock_zh_index_spot_sina`
- **财务报族**：`stock_balance_sheet_by_report_em`, `stock_balance_sheet_by_yearly_em`, `stock_cash_flow_sheet_by_report_em`, `stock_profit_sheet_by_report_em`, `stock_financial_report_sina` 等
- **股东/股本**：`stock_gdfx_*`(十余个：free_top_10/holding_change/detail/statistics/teamwork 等), `stock_gpzy_*`(股权质押)
- **新闻/研报**：`stock_news_em`, `stock_comment_detail_*`, `stock_research_report_em`, `stock_hot_keyword_em`, `stock_hot_rank_relate_em`, `stock_hot_rank_latest_em`, `stock_hot_rank_detail_em`, `stock_hot_rank_detail_realtime_em`
- **其他**：`stock_analyst_detail_em`, `stock_analyst_rank_em`, `stock_changes_em`, `stock_classify_sina`, `stock_cyq_em`(筹码), `stock_dxsyl_em`, `stock_esg_*`, `stock_fhps_em`, `stock_gddh_em`, `stock_ggcg_em`, `stock_gpzy_*`, `stock_gsrl_gsdt_em`, `stock_hk_*`(港股族), `stock_info_cjzc_em`, `stock_info_global_em`, `stock_ipo_declare_em`, `stock_ipo_tutor_em`, `stock_jgdy_*`, `stock_kc_a_spot_em`, `stock_pg_em`, `stock_profit_forecast_em`, `stock_qsjy_em`, `stock_register_all_em`, `stock_restricted_release_*`, `stock_sy_em`(市盈率), `stock_tfp_em`, `stock_us_*`(美股族), `stock_value_em`, `stock_xgsglb_em`, `stock_yysj_em`, `stock_zdhtmx_em`, `stock_zh_a_*`, `stock_zh_ab_comparison_em`, `stock_zh_ah_spot_em`, `stock_zh_b_spot_em`, `stock_zh_dupont_comparison_em`, `stock_zh_growth_comparison_em`, `stock_zh_kcb_report_em`, `stock_zh_scale_comparison_em`, `stock_zh_valuation_comparison_em`, `stock_zygc_em`

> 以上 📋 项**函数均存在于 akshare 1.18.79**，但本次未逐一调用验证字段。若后续需接入某一具体维度（如龙虎榜、沪深港通、筹码分布），应先在交易日 + 退避条件下单独实测，确认字段后再写封装（参考 `infrastructure/stock/akshare_client.py` 的模式）。

---

## 4. 字段映射与对接要点（给 AI 的落地约束）

1. **pct_chg 一律自算**：腾讯/同花顺 K 线接口不返回涨跌幅，用前一日 `close` 计算；首行无前日时 `pct_chg=None`。
2. **字符串型数值必须解析**：同花顺 `stock_fund_flow_individual` 的 `涨跌幅`/`换手率`(带`%`)、`流入/流出/净额/成交额`(带`亿`/`万`) 是字符串，需 `parse_pct_str` / `parse_amount_str`（来自 `domain.stock.emotion_dimensions`）。
3. **腾讯 turnover/amount 易混淆**：`turnover`=换手率(0–1)，`amount`=成交额(元)。
4. **反爬不稳定接口降级**：东财 `_em` 实时截面（spot/index_spot）失败率约 50%（实测 `ConnectionError`），失败时降级为 `None`/空，不可阻断主流程。**优先用腾讯 `stock_zh_a_spot_tx` 替代东财实时截面。**
5. **空数据接口**：`stock_zt_pool_dtgc_em` 在强势市场返回 0 行 0 列，解析前需判空。
6. **列名差异**：同花顺次新池用 `转手率`，其余涨停池用 `换手率`——字段名不统一。
7. **涨停池家族列结构不一致**：`stock_zt_pool_em`(含封板资金/封板时间/炸板次数/连板数) vs `stock_zt_pool_strong_em`(含涨停价/涨速/是否新高/量比/入选理由) vs `stock_zt_pool_previous_em`(含昨日封板时间/昨日连板数) vs `stock_zt_pool_zbgc_em`(含炸板次数/振幅)。整合到统一 `LimitStock` 模型时按各自列名取值，缺字段补默认/None。
8. **非交易日处理**：周日/节假日日线与资金流接口返回空，项目 `akshare_client.py` 已有"非交易日回退到最近有数据日"的逻辑（Task 18），接入新接口时需复用该回退。

---

## 5. 关于"开盘啦"的结论（写入本参考物）

- **开盘啦（kaipanla）无免费公开接口、无开发者文档、无官方 SDK**（web 检索确认：官网仅网页端与 App，社区获取方式均为 Fiddler/Charles/mitmproxy 抓包逆向私有接口）。
- **akshare 1.18.79 命名空间不含任何 `kpl`/`kaipanla`/`longhu` 函数**（首轮实测 `AKSHARE_KPL_NAMESPACE_HITS=[]`）。
- **推荐替代方案**：复盘所需开盘啦特色维度，已由以下**已验证可用**接口覆盖：
  - 封单金额 → `stock_zt_pool_em.封板资金`
  - 连板梯队/晋级率 → `stock_zt_pool_em.连板数` + `stock_zt_pool_previous_em.昨日连板数`
  - 强势股/新高 → `stock_zt_pool_strong_em.是否新高/量比/入选理由`
  - 炸板 → `stock_zt_pool_zbgc_em`
  - 全市场广度/主力资金 → `stock_zh_a_spot_tx`（腾讯，27列，本次实测稳定）
- **不建议**直连开盘啦私有接口：签名算法易变、无 SLA、且违反项目 `AGENTS.md §3/§4` 关于外部未授权数据源的约束。

---

## 6. 实测原始输出凭证（可审计）

### 6.1 本轮（2026-08-02 周日，部分成功）
```
AKSHARE_VERSION=1.18.79

[腾讯] stock_zh_a_spot_tx  OK_DF rows=200
  COLUMNS=['code','hsl','lb','ltsz','name','pe_ttm','pn','speed','state','stock_type','turnover','volume','zd','zdf','zdf_d10','zdf_d20','zdf_d5','zdf_d60','zdf_w52','zdf_y','zf','zljlr','zllc','zllc_d5','zllr','zllr_d5','zsz','zxj']
  SAMPLE={'code':'sh688808','name':'联讯仪器','zxj':1640.0,'zdf':6.77,'hsl':'10.03','lb':'1.08','ltsz':'316.46','zsz':'1683.73','pe_ttm':'616.24','zljlr':'2097.95','zllr':'334226.05','zllc':'332128.10','zdf_d5':-16.11,'zdf_d60':45.13,'zdf_y':1902.93,'speed':'-1.20'}

[腾讯] stock_zh_a_tick_tx_js  OK_DF rows=4300
  COLUMNS=['成交时间','成交价格','价格变动','成交量','成交金额','性质']
  SAMPLE={'成交时间':'09:25:02','成交价格':1330.03,'价格变动':-0.13,'成交量':1191,'成交金额':158405243,'性质':'卖盘'}

[东财] stock_zt_pool_em  OK_DF rows=99
  COLUMNS=['序号','代码','名称','涨跌幅','最新价','成交额','流通市值','总市值','换手率','封板资金','首次封板时间','最后封板时间','炸板次数','涨停统计','连板数','所属行业']
  SAMPLE={'代码':'000593','名称':'德龙汇能','涨跌幅':10.013,'封板资金':82413851,'首次封板时间':'092500','炸板次数':0,'连板数':1,'所属行业':'燃气Ⅱ'}

[东财] stock_zt_pool_strong_em  OK_DF rows=64
  COLUMNS=['序号','代码','名称','涨跌幅','最新价','涨停价','成交额','流通市值','总市值','换手率','涨速','是否新高','量比','涨停统计','入选理由','所属行业']
  SAMPLE={'代码':'300795','名称':'米奥会展','涨停价':16.44,'是否新高':'是','量比':1.379,'入选理由':'60日新高'}

[东财] stock_zt_pool_previous_em  OK_DF rows=52
  COLUMNS=['序号','代码','名称','涨跌幅','最新价','涨停价','成交额','流通市值','总市值','换手率','涨速','振幅','昨日封板时间','昨日连板数','涨停统计','所属行业']
  SAMPLE={'代码':'000009','名称':'中国宝安','振幅':13.566,'昨日封板时间':'100415','昨日连板数':1,'涨停统计':'2/2'}

[东财] stock_zt_pool_sub_new_em  OK_DF rows=143
  COLUMNS=['序号','代码','名称','涨跌幅','最新价','涨停价','成交额','流通市值','总市值','转手率','开板几日','开板日期','上市日期','是否新高','涨停统计','所属行业']
  SAMPLE={'代码':'301677','名称':'C欣兴','转手率':73.331,'开板几日':2,'上市日期':datetime.date(2026,7,30),'是否新高':'否'}

[东财] stock_zt_pool_zbgc_em  OK_DF rows=107
  COLUMNS=['序号','代码','名称','涨跌幅','最新价','涨停价','成交额','流通市值','总市值','换手率','涨速','首次封板时间','炸板次数','涨停统计','振幅','所属行业']
  SAMPLE={'代码':'000636','名称':'风华高科','涨跌幅':-2.277,'涨停价':55.55,'炸板次数':3,'振幅':14.178}

[东财] stock_zt_pool_dtgc_em  OK_DF rows=0 cols=0 (该交易日无跌停)

[东财] stock_market_activity_legu  OK_DF rows=12
  COLUMNS=['item','value']  SAMPLE={'item':'上涨','value':4395.0}

[东财] stock_hot_rank_em  OK_DF rows=100
  COLUMNS=['当前排名','代码','股票名称','最新价','涨跌额','涨跌幅']
  SAMPLE={'当前排名':1,'代码':'SZ002131','股票名称':'利欧股份','最新价':4.66,'涨跌幅':9.91}

[东财] stock_hot_up_em  OK_DF rows=100
  COLUMNS=['排名较昨日变动','当前排名','代码','股票名称','最新价','涨跌额','涨跌幅']

[东财] stock_hsgt_fund_flow_summary_em  OK_DF rows=4
  COLUMNS=['交易日','类型','板块','资金方向','交易状态','成交净买额','资金净流入','当日资金余额','上涨数','持平数','下跌数','相关指数','指数涨跌幅']

[东财] stock_restricted_release_summary_em  OK_DF rows=29
  COLUMNS=['序号','解禁时间','当日解禁股票家数','解禁数量','实际解禁数量','实际解禁市值','沪深300指数','沪深300指数涨跌幅']

[同花顺] stock_zyjs_ths(symbol=600519)  OK_DF rows=1
  COLUMNS=['股票代码','主营业务','产品类型','产品名称','经营范围']

[东财] stock_account_statistics_em  OK_DF rows=101
  COLUMNS=['数据日期','新增投资者-数量','新增投资者-环比','新增投资者-同比','期末投资者-总量','期末投资者-A股账户','期末投资者-B股账户','沪深总市值','沪深户均市值','上证指数-收盘','上证指数-涨跌幅']

[东财] stock_zh_index_spot_em / stock_board_industry_name_em / stock_zh_a_spot_em 等
  => ERR ConnectionError: RemoteDisconnected (反爬，需退避或交易日重试)
```

### 6.2 首轮（交易日 2026-07-31，成功返回，本轮因非交易日空返回）
```
[腾讯] stock_zh_a_hist_tx  OK_DF rows=4 cols=8
  COLUMNS=['date','open','close','high','low','volume','turnover','amount']
  SAMPLE={'date':2026-07-28,'open':1299.0,'close':1320.0,'turnover':0.0043,'amount':6960058100.0}

[腾讯] stock_zh_index_daily  OK_DF rows=8694 cols=6
  COLUMNS=['date','open','high','low','close','volume']

[同花顺] stock_board_industry_name_ths  OK_DF rows=90 cols=2
  COLUMNS=['name','code']  SAMPLE={'name':'半导体','code':'881121'}

[同花顺] stock_board_industry_index_ths  OK_DF rows=4 cols=7
  COLUMNS=['日期','开盘价','最高价','最低价','收盘价','成交量','成交额']
  SAMPLE={'日期':2026-07-28,'收盘价':15118.52,'成交额':384668830000.0}

[同花顺] stock_fund_flow_individual  OK_DF rows=5197 cols=10
  COLUMNS=['序号','股票代码','股票简称','最新价','涨跌幅','换手率','流入资金','流出资金','净额','成交额']
  SAMPLE={'股票代码':300720,'涨跌幅':'20.01%','换手率':'3.72%','流入资金':'1.26亿','净额':'-8306.28万','成交额':'3.35亿'}

[同花顺] stock_board_concept_name_ths  OK_DF rows=375 cols=2
  COLUMNS=['name','code']  SAMPLE={'name':'阿尔茨海默概念','code':'308614'}

AKSHARE_KPL_NAMESPACE_HITS=[]
```
