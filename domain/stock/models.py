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
    """单日情绪指标（截面）。"""

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


class EmotionRawData(BaseModel):
    """akshare 拉取的"原始"情绪指标（fetcher 二次加工前的中间 DTO）。

    Task 12：emotion_daily_fetcher 通过 AkshareClient.fetch_emotion_daily
    取得本 DTO，再结合 limit_stocks_daily 聚合 + heuristics 算 valid /
    broken_ratio / max_boards，并查询昨日 emotion_daily 算 volume_change_pct，
    最终拼出 EmotionIndicators 写入 cache。

    字段语义：
    - limit_up_count / limit_down_count: akshare 截面涨停/跌停家数
    - broken_count: 当日炸板数（fetcher 用此算 broken_limit_ratio）
    - total_volume: 两市成交额（元）；Task B 改为 Optional——
      ``stock_zh_index_spot_em`` 反爬不稳定，失败时降级为 None，
      其他字段照写（不再因 spot_em 失败而整行丢弃）
    """

    model_config = ConfigDict(extra="forbid")
    trade_date: str
    limit_up_count: int
    limit_down_count: int
    broken_count: int
    total_volume: float | None


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
