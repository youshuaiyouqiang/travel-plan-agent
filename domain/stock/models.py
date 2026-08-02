"""股票复盘 DTO 定义。

所有 DTO 遵循 Pydantic v2 + ConfigDict(extra="forbid")（AGENTS.md §5）。
DTO 放在 domain 层供 application / infrastructure 共享；这是股票领域的
核心数据契约。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class LimitStock(BaseModel):
    """涨停股池 DTO。"""

    model_config = ConfigDict(extra="forbid")
    trade_date: str
    stock_code: str
    stock_name: str
    limit_type: str  # up / down / broken
    consecutive_boards: int
    first_limit_time: str | None
    last_limit_time: str | None
    open_count: int  # 炸板次数
    is_valid_limit_up: bool  # 一次性封死判定


class EmotionIndicators(BaseModel):
    """单日情绪指标（截面）。

    Task E：新增 6 维度情绪观察框架的 18 个字段。
    - 维度 1 高度：height_level（基于近 20 日涨停数分位数）
    - 维度 2 广度：adv_count/decl_count/adv_decl_ratio/breadth_level
    - 维度 3 强度：top20_volume_*/strength_level/market_style
    - 维度 4 韧性：board_break_*/rebound_success_ratio/top5d_avg_chg/resilience_level
    - 维度 5 真实度：authenticity_level（基于已有 broken_limit_ratio）
    - 维度 6 持续性：trend_5d/trend_20d

    全部新字段允许 None——fetcher 调用方未计算时保持 None。
    phase / phase_confidence / phase_reason 保留 schema 但 Task E 不再写入
    （代码做维度分类，LLM 受约束推理，不写阶段标签）。
    """

    model_config = ConfigDict(extra="forbid")
    trade_date: str
    limit_up_count: int
    limit_down_count: int
    valid_limit_up_count: int
    broken_limit_ratio: float
    max_consecutive_boards: int
    yesterday_limit_up_today_premium: float | None
    total_volume: float | None  # Task B：spot_em 失败时降级 None
    volume_change_pct: float | None
    phase: str | None
    phase_confidence: str | None
    phase_reason: str | None
    # Task E：6 维度情绪观察框架（v023 新增 18 字段）
    # 维度 2：广度
    adv_count: int | None = None
    decl_count: int | None = None
    adv_decl_ratio: float | None = None
    breadth_level: str | None = None
    # 维度 3：强度
    top20_volume_avg_chg: float | None = None
    top20_volume_up_count: int | None = None
    top20_volume_limit_up_count: int | None = None
    strength_level: str | None = None
    market_style: str | None = None
    # 维度 4：韧性
    board_break_total_count: int | None = None
    board_break_rebound_count: int | None = None
    rebound_success_ratio: float | None = None
    top5d_avg_chg: float | None = None
    resilience_level: str | None = None
    # 维度 5：真实度（已有 broken_limit_ratio，新增分类）
    authenticity_level: str | None = None
    # 维度 1：高度
    height_level: str | None = None
    # 维度 6：持续性
    trend_5d: str | None = None
    trend_20d: str | None = None


class EmotionRawData(BaseModel):
    """akshare 拉取的"原始"情绪指标（fetcher 二次加工前的中间 DTO）。

    Task 12：emotion_daily_fetcher 通过 AkshareClient.fetch_emotion_daily
    取得本 DTO，再结合 limit_stocks_daily 聚合 + heuristics 算 valid /
    broken_ratio / max_boards，并查询昨日 emotion_daily 算 volume_change_pct，
    最终拼出 EmotionIndicators 写入 cache。

    Task E 扩展：新增 adv_count / decl_count（来自 legu "上涨"/"下跌"项），
    供维度 2（广度）计算 breadth_level。

    字段语义：
    - limit_up_count / limit_down_count: akshare 截面涨停/跌停家数
    - broken_count: 当日炸板数（fetcher 用此算 broken_limit_ratio）
    - total_volume: 两市成交额（元）；Task B 改为 Optional——
      ``stock_zh_index_spot_em`` 反爬不稳定，失败时降级为 None，
      其他字段照写（不再因 spot_em 失败而整行丢弃）
    - adv_count / decl_count: 上涨/下跌家数（Task E，来自 legu "上涨"/"下跌"）
    """

    model_config = ConfigDict(extra="forbid")
    trade_date: str
    limit_up_count: int
    limit_down_count: int
    broken_count: int
    total_volume: float | None
    # Task E：维度 2 广度原始数据（legu "上涨"/"下跌"项）
    adv_count: int = 0
    decl_count: int = 0


class Top20VolumeSnapshot(BaseModel):
    """成交额前 20 名股票涨幅统计（维度 3 强度原始数据）。

    Task E：akshare_client.fetch_top20_volume_stocks 返回本 DTO，
    fetcher 用此计算 strength_level + market_style。

    数据源：``ak.stock_fund_flow_individual()``（同花顺，返回 5000+ 只个股
    资金流，含 涨跌幅/成交额 字符串字段）。取成交额前 20 名的涨幅统计。
    """

    model_config = ConfigDict(extra="forbid")
    avg_chg: float  # 前 20 名平均涨幅（%）
    up_count: int  # 前 20 名中上涨家数
    limit_up_count: int  # 前 20 名中涨停家数（pct_chg >= 9.8）


class MarketSnapshot(BaseModel):
    """大盘快照（含三大指数 + 成交额）。"""

    model_config = ConfigDict(extra="forbid")
    trade_date: str
    sh_index: float | None  # 上证
    sz_index: float | None  # 深证
    cyb_index: float | None  # 创业板
    total_volume: float | None  # 两市成交额（亿）
    volume_change_pct: float | None  # 较昨日环比
    consecutive_down_days: int  # 连续下跌天数
    ma20_status: str | None  # "above" / "below" / None


class MarketIndexRow(BaseModel):
    """大盘指数单日行（上证/深证/创业板之一）。

    Task 13：market_index_fetcher 写入 market_index_daily 表的单条记录。
    字段与 v021 迁移 market_index_daily 表一致。
    """

    model_config = ConfigDict(extra="forbid")
    trade_date: str
    index_code: str  # sh000001 / sz399001 / sz399006
    open: float | None
    close: float | None
    high: float | None
    low: float | None
    volume: float | None
    pct_chg: float | None


class StockDaily(BaseModel):
    """个股日线 OHLCV。

    Task 15：stock_daily_fetcher 写入 stock_daily 表的单条记录。
    字段与 v021 迁移 stock_daily 表一致（含 turnover 成交额）。
    """

    model_config = ConfigDict(extra="forbid")
    trade_date: str
    stock_code: str
    open: float | None
    close: float | None
    high: float | None
    low: float | None
    volume: float | None
    pct_chg: float | None
    turnover: float | None


class WatchlistStock(BaseModel):
    """观察池股票（多类别候选池）。"""

    model_config = ConfigDict(extra="forbid")
    stock_code: str
    stock_name: str
    category: int  # 1..5 入池类别
    entry_date: str
    entry_price: float | None
    status: str  # active / removed
    market_index_snapshot: float | None
    notes: str = ""


class SignalStock(BaseModel):
    """新信号股（抗跌 / 新周期 / 分歧后抗跌）。"""

    model_config = ConfigDict(extra="forbid")
    trade_date: str
    stock_code: str
    stock_name: str
    signal_type: str  # resistant / breakout / post_divergence_resistant
    pct_chg: float | None
    market_index_pct_chg: float | None
    entry_price: float | None


class SectorPerformance(BaseModel):
    """板块表现（领涨/领跌）。"""

    model_config = ConfigDict(extra="forbid")
    trade_date: str
    sector_code: str
    sector_name: str
    pct_chg: float | None
    leading_stock_codes: list[str] = []
    limit_up_count: int = 0


class SectorHeatDistribution(BaseModel):
    """板块涨停时段分布（用于"发酵均匀"判定）。"""

    model_config = ConfigDict(extra="forbid")
    trade_date: str
    sector_code: str
    sector_name: str
    morning_limit_up: int = 0  # 上午新涨停
    midday_limit_up: int = 0  # 午盘新涨停
    afternoon_limit_up: int = 0  # 尾盘新涨停


class StrongRepairLeader(BaseModel):
    """强修复领涨板块（用于"强修复领涨延续验证"）。"""

    model_config = ConfigDict(extra="forbid")
    trade_date: str  # 强修复日
    sector_code: str
    sector_name: str
    pct_chg_on_repair_day: float | None
    pct_chg_today: float | None  # 今日表现
    is_continued: bool  # 今日是否继续领涨


class ResistantSector(BaseModel):
    """抗跌板块（大盘下跌时跌幅显著小于大盘）。"""

    model_config = ConfigDict(extra="forbid")
    trade_date: str
    sector_code: str
    sector_name: str
    sector_pct_chg: float | None
    market_pct_chg: float | None
    resistant_ratio: float | None  # (market - sector) / |market|


class SectorLeader(BaseModel):
    """板块龙头（跌幅最小+涨幅最大组合前 2）。"""

    model_config = ConfigDict(extra="forbid")
    trade_date: str
    sector_code: str
    sector_name: str
    stock_code: str
    stock_name: str
    pct_chg: float | None
    leader_kind: str  # "smallest_drop" / "largest_gain"


class SectorDivergence(BaseModel):
    """板块高潮后分歧。"""

    model_config = ConfigDict(extra="forbid")
    trade_date: str
    sector_code: str
    sector_name: str
    was_high_phase: bool  # 昨日是否曾判定板块高潮
    sector_pct_chg: float | None
    leading_stock_pct_chg: float | None
    broken_limit_ratio: float | None


class SectorDaily(BaseModel):
    """板块日线（用于多日趋势）。"""

    model_config = ConfigDict(extra="forbid")
    trade_date: str
    sector_code: str
    sector_name: str
    pct_chg: float | None
    leading_stock_codes: list[str] = []
    limit_up_count: int = 0


class BoardLadder(BaseModel):
    """连板高度分层（按 consecutive_boards 分组统计）。

    Task A2：board_ladder_daily 表（v021 迁移已建但无 fetcher）的单条记录。
    每条记录表示"当日 N 板涨停股有 M 只"，由 limit_stocks_daily 聚合产生：
    - 1 板：3 只 → 一条 BoardLadder(boards=1, count=3, stock_codes=[...])
    - 2 板：2 只 → 一条 BoardLadder(boards=2, count=2, stock_codes=[...])
    - 3 板：1 只 → 一条 BoardLadder(boards=3, count=1, stock_codes=[...])

    SKILL.md 方法论讲"连板高度"时用此表（如"3 板 1 只代表情绪高位"）。
    """

    model_config = ConfigDict(extra="forbid")
    trade_date: str
    boards: int  # 连板高度（1=首板，2=2 连板，3=3 连板...）
    count: int  # 该高度涨停股数量
    stock_codes: list[str]  # 该高度所有涨停股代码列表


class EmotionCycleSegment(BaseModel):
    """情绪周期段（峰→谷→修复），供 LLM 对比修复力度。

    Task E：周期段峰谷检测的输出 DTO。
    不含方向判定——LLM 基于 SKILL.md §三第 3 步自己判断。

    一个周期段由"峰值日 + 谷值日 + 首次修复日"三要素构成。
    LLM 用此对比"当前修复力度 vs 上一轮修复力度"：
    - 当前涨停 45 > 上一轮首次修复涨停 35 → 上升周期概率较高
    - 但修复力度不及上一轮峰值 80 的 60% → 仍处于修复早期
    """

    model_config = ConfigDict(extra="forbid")
    peak_date: str  # 峰值日（涨停数局部极大）
    peak_limit_up_count: int  # 峰值日涨停数
    trough_date: str  # 谷值日（涨停数局部极小）
    trough_limit_up_count: int  # 谷值日涨停数
    first_repair_date: str | None  # 谷值后首次修复日（涨停数回升 ≥ 30%）
    first_repair_limit_up: int | None  # 首次修复日涨停数


class CorrelationResult(BaseModel):
    """庄股/抱团股相关性识别（周复盘专用）。"""

    model_config = ConfigDict(extra="forbid")
    end_date: str
    window_days: int
    individual_stocks: list[StockCorrelation] = []  # 单只庄股
    clustered_groups: list[ClusterGroup] = []  # 抱团股群


class StockCorrelation(BaseModel):
    """单只股票与大盘/板块的相关性。"""

    model_config = ConfigDict(extra="forbid")
    stock_code: str
    stock_name: str
    market_correlation: float  # 与大盘相关性
    sector_correlation: float  # 与板块相关性
    is_independent: bool  # < 0.3 视为独立行情


class ClusterGroup(BaseModel):
    """抱团股群。"""

    model_config = ConfigDict(extra="forbid")
    members: list[str]  # stock_codes
    intra_correlation: float  # > 0.7 视为抱团


class ReviewReport(BaseModel):
    """复盘文存档 DTO。"""

    model_config = ConfigDict(extra="forbid")
    id: str
    user_id: str
    trade_date: str
    content: str
    status: str = "completed"  # completed / degraded / no_data
    llm_metadata: str = "{}"  # JSON 字符串
    created_at: str
