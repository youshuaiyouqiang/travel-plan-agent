"""情绪周期得分与阶段判定纯函数（AGENTS.md §8.1 端口先于实现）。

设计要点（开发文档 docs/开发文档/情绪周期折线图/开发文档.md §4 §5 §7.1）：
- 全部为纯函数，无 I/O / 无外部依赖、**不依赖 numpy**（避免 mypy stub 问题）
- 二阶统一用**首末差值**（今日值 − 3 日前值），窗口 3 日——3 点线性回归易过拟合
  且意义不大，首末差值更直观、计算更轻
- 每个风格得分 = 0.6 * 一阶归一化 + 0.4 * 二阶归一化，输出 0-100
- 一阶缺失时各风格有独立降级策略；二阶 3 日前值缺失（冷启动）时动量视为 0
- 阶段判定 v1 用 ``compute_raw_phase``（无状态、无防抖）；防抖见开发文档 §13 后续扩展

边界（AGENTS.md §8.3）：
- 本模块**禁止** import infrastructure / api / application / fastapi / 具体 I/O SDK
- fetcher 调用本模块做得分计算和阶段判定，本模块不感知 I/O
- 与同目录 ``emotion_cycles.py``（复数，峰谷检测）职责不同，勿混淆
"""

from __future__ import annotations


# ── 工具 ────────────────────────────────────────────────────


def _clamp(value: float, lo: float, hi: float) -> float:
    """把 ``value`` 限制在闭区间 ``[lo, hi]``。

    Args:
        value: 原始值。
        lo: 下界。
        hi: 上界。

    Returns:
        被夹紧后的值；``value < lo`` 返 ``lo``，``value > hi`` 返 ``hi``，
        否则原值返回。``lo > hi`` 时行为未定义（调用方需保证 lo ≤ hi）。
    """
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


# ── 风格得分 ────────────────────────────────────────────────


def compute_board_style_score(
    yesterday_premium: float | None,
    limit_up_count: int,
    limit_up_count_3d_ago: int | None,
    limit_up_percentile: float | None,
) -> float | None:
    """打板风格得分 0-100（开发文档 §4.1）。

    一阶：昨日涨停今日溢价（典型 -5% ~ +5%），``yesterday_premium`` 为 None
    时降级用涨停数近 20 日分位数（``limit_up_percentile``，0.0-1.0 → *100）；
    两者皆 None 时一阶取 50（中性）。
    二阶：涨停数 3 日首末差值（典型 -20 ~ +20），``limit_up_count_3d_ago``
    为 None（冷启动）时动量视为 0。

    Args:
        yesterday_premium: 昨日涨停今日溢价（百分比，如 2.0 表示 +2%）。
        limit_up_count: 今日涨停数。
        limit_up_count_3d_ago: 3 日前涨停数；None 时二阶动量视为 0。
        limit_up_percentile: 今日涨停数近 20 日分位数（0.0-1.0）；
            仅在 ``yesterday_premium`` 为 None 时用作一阶降级。

    Returns:
        打板风格得分 0-100；本风格始终可计算（涨停数必存在），不会返回 None。
    """
    # 一阶
    if yesterday_premium is not None:
        first_norm = _clamp((yesterday_premium + 5) / 10 * 100, 0, 100)
    elif limit_up_percentile is not None:
        first_norm = _clamp(limit_up_percentile * 100, 0, 100)
    else:
        first_norm = 50.0

    # 二阶：首末差值
    second = (
        limit_up_count - limit_up_count_3d_ago
        if limit_up_count_3d_ago is not None
        else 0
    )
    second_norm = _clamp((second + 20) / 40 * 100, 0, 100)

    return 0.6 * first_norm + 0.4 * second_norm


def compute_trend_style_score(
    top20_avg_chg: float | None,
    adv_count: int | None,
    adv_count_3d_ago: int | None,
    adv_decl_ratio: float | None,
) -> float | None:
    """趋势风格得分 0-100（开发文档 §4.2）。

    一阶：成交额前 20 平均涨幅（典型 -3% ~ +3%），``top20_avg_chg`` 为 None
    时降级用涨跌家数比 ``adv_decl_ratio`` 归一化（``ratio/(1+ratio)*100``，
    1.0 → 50 中性，全涨 → 100，全跌 → 0）；两者皆 None 时一阶取 50。
    二阶：上涨家数 3 日首末差值（典型 -500 ~ +500），``adv_count`` 或
    ``adv_count_3d_ago`` 为 None 时动量视为 0。

    Args:
        top20_avg_chg: 成交额前 20 平均涨幅（百分比）。
        adv_count: 今日上涨家数。
        adv_count_3d_ago: 3 日前上涨家数；None 时二阶动量视为 0。
        adv_decl_ratio: 涨跌家数比（adv/decl）；仅在一阶降级时使用。

    Returns:
        趋势风格得分 0-100；本风格始终可计算，不会返回 None。
    """
    # 一阶
    if top20_avg_chg is not None:
        first_norm = _clamp((top20_avg_chg + 3) / 6 * 100, 0, 100)
    elif adv_decl_ratio is not None:
        # ratio/(1+ratio) 把 [0, ∞) 映射到 [0, 100)，1.0 → 50 中性
        first_norm = _clamp(adv_decl_ratio / (1 + adv_decl_ratio) * 100, 0, 100)
    else:
        first_norm = 50.0

    # 二阶：首末差值
    if adv_count is not None and adv_count_3d_ago is not None:
        second = adv_count - adv_count_3d_ago
    else:
        second = 0
    second_norm = _clamp((second + 500) / 1000 * 100, 0, 100)

    return 0.6 * first_norm + 0.4 * second_norm


def compute_rebound_style_score(
    rebound_ratio: float | None,
    rebound_ratio_3d_ago: float | None,
) -> float | None:
    """反包风格得分 0-100（开发文档 §4.3）。

    一阶：断板反包成功率（0 ~ 1），``rebound_ratio`` 为 None 时（如昨日无涨停
    / 今日无 stock_daily）**直接返回 None**——反包无降级，全局合成时跳过。
    二阶：反包成功率 3 日首末差值（典型 -0.3 ~ +0.3），``rebound_ratio_3d_ago``
    为 None 时动量视为 0。

    Args:
        rebound_ratio: 今日断板反包成功率（0.0-1.0）。
        rebound_ratio_3d_ago: 3 日前反包成功率；None 时二阶动量视为 0。

    Returns:
        反包风格得分 0-100；``rebound_ratio`` 为 None 时返回 None。
    """
    if rebound_ratio is None:
        return None

    # 一阶：直接 *100
    first_norm = _clamp(rebound_ratio * 100, 0, 100)

    # 二阶：首末差值
    second = (
        rebound_ratio - rebound_ratio_3d_ago
        if rebound_ratio_3d_ago is not None
        else 0.0
    )
    second_norm = _clamp((second + 0.3) / 0.6 * 100, 0, 100)

    return 0.6 * first_norm + 0.4 * second_norm


# ── 全局情绪得分 ───────────────────────────────────────────


def compute_emotion_score(
    board_score: float | None,
    trend_score: float | None,
    rebound_score: float | None,
) -> float:
    """全局情绪得分 0-100（开发文档 §4.4）。

    三风格**等权合成**，None 跳过（反包数据缺失时只取打板 + 趋势）；
    全部为 None 时返回 50.0（中性，避免下游除零）。

    Args:
        board_score: 打板风格得分；None 表示该风格无数据。
        trend_score: 趋势风格得分；None 表示该风格无数据。
        rebound_score: 反包风格得分；None 表示该风格无数据。

    Returns:
        全局情绪得分 0-100；无任何风格数据时返回 50.0。
    """
    scores = [
        s for s in (board_score, trend_score, rebound_score) if s is not None
    ]
    if not scores:
        return 50.0
    return sum(scores) / len(scores)


# ── 阶段判定 ───────────────────────────────────────────────


def compute_raw_phase(
    emotion_score: float,
    score_3d_ago: float | None,
) -> str:
    """判定原始情绪阶段（开发文档 §5.2，6 阶段之一，无防抖）。

    一阶（得分）判断赚不赚，二阶（动量）判断跟风增减，组合确定阶段。
    动量 = 今日得分 − 3 日前得分；``score_3d_ago`` 为 None（老行 / 冷启动）
    时动量视为 0，纯按得分粗判。

    阶段闭环：冰点 → 弱修复 → 强修复 → 高潮 → 弱分歧 → 强分歧 → 冰点。

    Args:
        emotion_score: 全局情绪得分 0-100。
        score_3d_ago: 3 日前全局得分；None 时动量视为 0。

    Returns:
        六阶段之一：``冰点`` / ``强分歧`` / ``弱分歧`` / ``弱修复`` /
        ``强修复`` / ``高潮``。

    Note:
        v1 不实现防抖（连续 2 日确认），单日抖动在折线图上表现为毛刺；
        防抖需新增 ``emotion_phase_pending`` 列，见开发文档 §13 后续扩展。
    """
    momentum = (
        emotion_score - score_3d_ago if score_3d_ago is not None else 0.0
    )

    if emotion_score >= 80:
        return "高潮"
    if emotion_score >= 60:
        # 60-80 是"赚钱区间"：momentum>0 向高潮走=强修复(红)；
        # momentum<-5 急跌=赚钱效应收敛=弱分歧(浅绿)；平稳=强修复(红)。
        if momentum > 0:
            return "强修复"
        if momentum < -5:
            return "弱分歧"
        return "强修复"
    if emotion_score >= 40:
        if momentum > 5:
            return "强修复"
        if momentum < -5:
            return "弱分歧"
        return "弱修复"
    if emotion_score >= 20:
        if momentum < -5:
            return "强分歧"
        return "弱修复"
    # < 20
    return "弱修复" if momentum > 0 else "冰点"
