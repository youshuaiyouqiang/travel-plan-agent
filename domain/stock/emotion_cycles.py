"""情绪周期段峰谷检测（纯函数，无 I/O）。

Task E.10：为 SKILL.md §三第 3 步"与上一轮退潮比"提供客观数据。

设计要点（AGENTS.md §8.1 端口先于实现 + §2 域层不依赖 I/O）：
- 全部纯函数，无 I/O / 无外部依赖（不读 SQLite / 不调 akshare）
- 只做客观数据切分（峰/谷/首次修复日），不判定阶段方向
- LLM 基于代码提供的周期段数据，对比"当前涨停数 vs 上一轮首次修复涨停数"

边界：
- 本模块**禁止** import infrastructure / akshare / sqlite3
- 算法定义见 docs/bug修复/股市复盘Agent数据缺失问题分析与修复方案.md
  §3.3 Task E.10 周期段识别（峰谷检测）
"""

from __future__ import annotations

from domain.stock.models import EmotionCycleSegment, EmotionIndicators


def _find_local_maxima(values: list[int], window: int = 3) -> list[int]:
    """找局部极大值的索引（今日值严格 > 前后 ``window`` 日）。

    Args:
        values: 时间序列（如近 60 日涨停数）。
        window: 峰值需要在其前后各 ``window`` 日内严格最大。

    Returns:
        局部极大值的索引列表（升序）。
        边界 ``[0, window)`` 和 ``[len-window, len)`` 不参与判定，
        避免边界效应导致误判。
    """
    if len(values) < 2 * window + 1:
        return []
    maxima: list[int] = []
    for i in range(window, len(values) - window):
        left = all(values[i] > values[i - j] for j in range(1, window + 1))
        right = all(values[i] > values[i + j] for j in range(1, window + 1))
        if left and right:
            maxima.append(i)
    return maxima


def _find_local_minima(values: list[int], window: int = 3) -> list[int]:
    """找局部极小值的索引（今日值严格 < 前后 ``window`` 日）。

    Args:
        values: 时间序列。
        window: 谷值需要在其前后各 ``window`` 日内严格最小。

    Returns:
        局部极小值的索引列表（升序）。
    """
    if len(values) < 2 * window + 1:
        return []
    minima: list[int] = []
    for i in range(window, len(values) - window):
        left = all(values[i] < values[i - j] for j in range(1, window + 1))
        right = all(values[i] < values[i + j] for j in range(1, window + 1))
        if left and right:
            minima.append(i)
    return minima


def identify_emotion_cycles(
    history: list[EmotionIndicators],
    min_peak_trough_gap: int = 3,
    repair_threshold: float = 0.3,
) -> list[EmotionCycleSegment]:
    """峰谷检测：找局部极大值（峰）和局部极小值（谷），切成周期段。

    纯算法，不做阶段判定。返回客观数据供 LLM 对比修复力度。

    流程：
    1. 找局部极大值（峰值日）：今日涨停数 > 前后各 ``min_peak_trough_gap`` 日
    2. 找局部极小值（谷值日）
    3. 配对峰谷：每个峰值后的第一个谷值
    4. 找谷值后的首次修复日（涨停数回升 >= ``repair_threshold``）

    谷值涨停数为 0 时（冰点期），任意 >0 都算修复（防除零，绝对增长即修复）。

    Args:
        history: 近 N 日情绪指标序列，**必须按时间正序**（旧→新）。
        min_peak_trough_gap: 峰谷判定的窗口大小（默认 3）。
            峰值/谷值需要在其前后各 ``min_peak_trough_gap`` 日内严格最大/最小。
        repair_threshold: 涨停数回升比例阈值（默认 0.3 = 30%）。

    Returns:
        EmotionCycleSegment 列表；历史 <5 日或无峰谷模式时为空列表。
    """
    if len(history) < 5:
        return []

    values = [h.limit_up_count for h in history]
    peaks = _find_local_maxima(values, window=min_peak_trough_gap)
    troughs = _find_local_minima(values, window=min_peak_trough_gap)
    if not peaks or not troughs:
        return []

    segments: list[EmotionCycleSegment] = []
    for peak_idx in peaks:
        # 找该峰值后的第一个谷值
        following_troughs = [t for t in troughs if t > peak_idx]
        if not following_troughs:
            continue
        trough_idx = following_troughs[0]
        trough_value = history[trough_idx].limit_up_count

        # 找谷值后的首次修复日（涨停数回升 >= threshold）
        repair_idx: int | None = None
        for i in range(trough_idx + 1, len(history)):
            today_value = history[i].limit_up_count
            if trough_value > 0:
                repair_ratio = (today_value - trough_value) / trough_value
                if repair_ratio >= repair_threshold:
                    repair_idx = i
                    break
            else:
                # 谷值=0（冰点期）：任意 >0 都算修复
                if today_value > 0:
                    repair_idx = i
                    break

        segments.append(
            EmotionCycleSegment(
                peak_date=history[peak_idx].trade_date,
                peak_limit_up_count=history[peak_idx].limit_up_count,
                trough_date=history[trough_idx].trade_date,
                trough_limit_up_count=trough_value,
                first_repair_date=(
                    history[repair_idx].trade_date if repair_idx is not None else None
                ),
                first_repair_limit_up=(
                    history[repair_idx].limit_up_count
                    if repair_idx is not None
                    else None
                ),
            )
        )
    return segments
