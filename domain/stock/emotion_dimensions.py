"""6 维度情绪观察的计算函数（纯函数，无 I/O）。

Task E：为复盘 LLM 提供客观的维度分类数据，受约束推理避免刻舟求剑。

设计要点（AGENTS.md §8.1 端口先于实现 + §2 域层不依赖 I/O）：
- 全部纯函数，无 I/O / 无外部依赖（不读 SQLite / 不调 akshare）
- 阈值在本模块内硬编码，AI 无发挥空间
- 分类返回描述性字符串（如"高位"/"普涨"），不返回阶段判定
- fetcher 调本模块算分类后写入 emotion_daily 表（v023 新增 18 字段）

边界：
- 本模块**禁止** import infrastructure / akshare / sqlite3
- 算法定义见 docs/bug修复/股市复盘Agent数据缺失问题分析与修复方案.md
  §3.3 Task E.3 各维度精确代码定义
"""

from __future__ import annotations


# ── 字符串解析辅助函数 ──────────────────────────────────


def parse_pct_str(s: str | None) -> float:
    """解析 ``"20.01%"`` → ``20.01``；``"-3.50%"`` → ``-3.50``。

    用于解析 akshare ``stock_fund_flow_individual`` 返回的"涨跌幅"字符串
    （akshare 该列 dtype 为 object，带 ``%`` 后缀）。

    Args:
        s: 形如 ``"20.01%"`` / ``"-3.50%"`` 的字符串；非字符串返回 ``0.0``。

    Returns:
        浮点数；解析失败返回 ``0.0``。
    """
    if not isinstance(s, str):
        return 0.0
    try:
        return float(s.rstrip("%"))
    except (ValueError, TypeError):
        return 0.0


def parse_amount_str(s: str | None) -> float:
    """解析 ``"3.35亿"`` → ``335000000``，``"9300万"`` → ``93000000``。

    用于解析 akshare ``stock_fund_flow_individual`` 返回的"成交额"字符串
    （akshare 该列 dtype 为 object，带"亿"/"万"后缀，字典序排序会错）。

    Args:
        s: 形如 ``"3.35亿"`` / ``"9300万"`` / ``"123.45"`` 的字符串；
            非字符串返回 ``0.0``。

    Returns:
        浮点数（元）；解析失败返回 ``0.0``。
    """
    if not isinstance(s, str):
        return 0.0
    s = s.strip()
    if s.endswith("亿"):
        try:
            return float(s[:-1]) * 1e8
        except (ValueError, TypeError):
            return 0.0
    if s.endswith("万"):
        try:
            return float(s[:-1]) * 1e4
        except (ValueError, TypeError):
            return 0.0
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


# ── 维度 1：情绪高度（基于近 20 日涨停数分位数）─────────────────


def compute_height_level(percentile: float | None) -> str:
    """根据当日涨停数在近 20 日中的分位数判定高度。

    相对化避免"刻舟求剑"——同样涨停数 50 在不同市场环境下意义不同：
    - 若近 20 日涨停数普遍 20-40，今日 50 = 高位
    - 若近 20 日涨停数普遍 60-100，今日 50 = 低位

    Args:
        percentile: 今日涨停数在近 20 日的分位数（0.0-1.0）。
            ``None`` 表示历史数据不足（<5 日），返回默认"中位"。

    Returns:
        ``"高位"`` / ``"中位"`` / ``"低位"`` / ``"极低位"``。
    """
    if percentile is None:
        return "中位"
    if percentile >= 0.80:
        return "高位"
    if percentile >= 0.50:
        return "中位"
    if percentile >= 0.20:
        return "低位"
    return "极低位"


def compute_limit_up_percentile(
    today_limit_up: int, history_limit_ups: list[int]
) -> float | None:
    """计算今日涨停数在历史序列中的分位数。

    Args:
        today_limit_up: 今日涨停数。
        history_limit_ups: 近 N 日（如 20 日）涨停数序列，不含今日。

    Returns:
        分位数 0.0-1.0；历史 <5 日返回 ``None``（数据不足）。
    """
    if len(history_limit_ups) < 5:
        return None
    # 分位数 = 历史中小于今日的比例
    below = sum(1 for v in history_limit_ups if v < today_limit_up)
    return below / len(history_limit_ups)


# ── 维度 2：情绪广度（绝对阈值——全市场指标）─────────────────


def compute_breadth_level(adv_count: int, decl_count: int) -> str:
    """根据涨跌家数比判定广度（全市场赚钱效应）。

    绝对阈值——广度是全市场指标，不需相对化（涨跌家数比有客观含义）。

    Args:
        adv_count: 上涨家数（来自 legu "上涨"项）。
        decl_count: 下跌家数（来自 legu "下跌"项）。

    Returns:
        ``"普涨"`` / ``"偏广"`` / ``"平衡"`` / ``"偏窄"`` / ``"普跌"``。

    Raises:
        ZeroDivisionError: 不会发生——decl_count=0 时直接返"普涨"。
    """
    if decl_count == 0:
        # 下跌为 0（全涨）→ 普涨
        return "普涨"
    ratio = adv_count / decl_count
    if ratio >= 3.0:
        return "普涨"
    if ratio >= 1.5:
        return "偏广"
    if ratio >= 0.67:
        return "平衡"
    if ratio >= 0.33:
        return "偏窄"
    return "普跌"


# ── 维度 3：情绪强度（成交额前 20 涨幅）─────────────────


def compute_strength_level(avg_chg: float, up_count: int) -> str:
    """根据成交额前 20 涨幅判定强度。

    Args:
        avg_chg: 前 20 名平均涨幅（%）。
        up_count: 前 20 名中上涨家数。

    Returns:
        ``"强势"`` / ``"偏强"`` / ``"中性"`` / ``"偏弱"`` / ``"弱势"``。
    """
    if avg_chg >= 3.0 and up_count >= 15:
        return "强势"
    if avg_chg >= 1.0 and up_count >= 10:
        return "偏强"
    if avg_chg >= -1.0:
        return "中性"
    if avg_chg >= -3.0:
        return "偏弱"
    return "弱势"


def compute_market_style(strength_level: str, height_level: str) -> str:
    """根据强度 + 高度组合判定市场风格。

    客观无歧义——5 种风格各有明确触发条件。

    Args:
        strength_level: ``compute_strength_level`` 返回值。
        height_level: ``compute_height_level`` 返回值。

    Returns:
        ``"题材股主导"`` / ``"趋势股主导"`` / ``"题材+趋势共振"`` /
        ``"弱势市场"`` / ``"混合"``。
    """
    strong = strength_level in ("强势", "偏强")
    weak = strength_level in ("偏弱", "弱势")
    high = height_level == "高位"
    low = height_level in ("低位", "极低位")

    if strong and low:
        return "趋势股主导"  # 前 20 强 + 涨停少 = 机构主导
    if strong and high:
        return "题材+趋势共振"  # 都强
    if weak and high:
        return "题材股主导"  # 涨停高但前 20 弱 = 游资打板
    if weak and low:
        return "弱势市场"
    return "混合"


# ── 维度 4：情绪韧性（断板反包 + 5 日累计涨幅）─────────────────


def compute_resilience_level(break_total: int, rebound_count: int) -> str:
    """根据断板反包情况判定韧性。

    Args:
        break_total: 断板股总数（昨日涨停今日未涨停）。
        rebound_count: 反包成功数（断板股今日涨幅 > 5%）。

    Returns:
        ``"无断板"`` / ``"强"`` / ``"中"`` / ``"弱"``。
    """
    if break_total == 0:
        return "无断板"  # 没有断板股，无法判定韧性
    ratio = rebound_count / break_total
    if ratio >= 0.5 and rebound_count >= 3:
        return "强"
    if ratio >= 0.3 and rebound_count >= 2:
        return "中"
    return "弱"


def compute_rebound_success_ratio(
    break_total: int, rebound_count: int
) -> float | None:
    """计算反包成功率。

    Args:
        break_total: 断板股总数。
        rebound_count: 反包成功数。

    Returns:
        成功率（0.0-1.0）；``break_total=0`` 时返回 ``None``（无法计算）。
    """
    if break_total == 0:
        return None
    return rebound_count / break_total


# ── 维度 5：情绪真实度（基于炸板率）─────────────────


def compute_authenticity_level(broken_ratio: float) -> str:
    """根据炸板率判定真实度。

    Args:
        broken_ratio: 炸板率（0.0-1.0）。

    Returns:
        ``"真实"`` / ``"偏真"`` / ``"偏虚"`` / ``"虚高"``。
    """
    if broken_ratio < 0.15:
        return "真实"
    if broken_ratio < 0.30:
        return "偏真"
    if broken_ratio < 0.50:
        return "偏虚"
    return "虚高"


# ── 维度 6：情绪持续性（线性回归斜率）─────────────────


def compute_trend(values: list[float]) -> str:
    """用线性回归斜率判定趋势方向。

    阈值：日均变化率 > 5% 视为趋势（上升/下降），否则震荡。
    数据点 <3 时返"数据不足"。

    Args:
        values: 时间序列（如近 5 日涨停数 [10, 15, 20, 25, 30]）。

    Returns:
        ``"上升"`` / ``"下降"`` / ``"震荡"`` / ``"数据不足"``。
    """
    if len(values) < 3:
        return "数据不足"
    n = len(values)
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n
    numerator = sum(
        (i - x_mean) * (v - y_mean) for i, v in enumerate(values)
    )
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    if denominator == 0:
        return "震荡"
    slope = numerator / denominator
    # 阈值：日均变化率 > 5% 视为趋势
    avg = y_mean if y_mean > 0 else 1.0
    daily_change_ratio = slope / avg
    if daily_change_ratio > 0.05:
        return "上升"
    if daily_change_ratio < -0.05:
        return "下降"
    return "震荡"
