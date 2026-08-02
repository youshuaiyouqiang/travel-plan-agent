"""Task E 单元测试：emotion_cycles 峰谷检测算法。

设计要点：
- 全部纯函数（无 I/O），测试不 mock 任何外部依赖
- 验证峰谷检测的客观性——代码只切分段，不判定方向
- 覆盖：典型周期段 / 无峰谷 / 数据不足 / 首次修复检测 / 边界窗口
"""

from __future__ import annotations


from domain.stock.emotion_cycles import (
    _find_local_maxima,
    _find_local_minima,
    identify_emotion_cycles,
)
from domain.stock.models import EmotionIndicators


def _make_emotion(
    trade_date: str, limit_up_count: int
) -> EmotionIndicators:
    """构造最小 EmotionIndicators（只关心 trade_date + limit_up_count）。"""
    return EmotionIndicators(
        trade_date=trade_date,
        limit_up_count=limit_up_count,
        limit_down_count=0,
        valid_limit_up_count=0,
        broken_limit_ratio=0.0,
        max_consecutive_boards=0,
        yesterday_limit_up_today_premium=None,
        total_volume=None,
        volume_change_pct=None,
        phase=None,
        phase_confidence=None,
        phase_reason=None,
    )


# ── _find_local_maxima ────────────────────────────────────


class TestFindLocalMaxima:
    def test_single_peak_in_middle(self) -> None:
        # [10, 20, 30, 20, 10] → 峰值在索引 2
        values = [10, 20, 30, 20, 10]
        assert _find_local_maxima(values, window=1) == [2]

    def test_multiple_peaks(self) -> None:
        # [10, 30, 10, 30, 10] → 峰值在索引 1 和 3
        values = [10, 30, 10, 30, 10]
        assert _find_local_maxima(values, window=1) == [1, 3]

    def test_no_peak_in_flat_series(self) -> None:
        # [10, 10, 10, 10] → 无峰值（严格 >）
        values = [10, 10, 10, 10]
        assert _find_local_maxima(values, window=1) == []

    def test_window_3_excludes_boundary(self) -> None:
        # window=3 时前 3 个和后 3 个不能是峰值
        values = [100, 1, 1, 1, 50, 1, 1, 1, 100]
        # 索引 0 和 8 不能是峰值（在边界外）
        assert _find_local_maxima(values, window=3) == [4]

    def test_empty_list_returns_empty(self) -> None:
        assert _find_local_maxima([], window=1) == []

    def test_short_list_returns_empty(self) -> None:
        # len <= 2*window 时无峰值
        assert _find_local_maxima([1, 2, 3], window=1) == []


# ── _find_local_minima ────────────────────────────────────


class TestFindLocalMinima:
    def test_single_trough_in_middle(self) -> None:
        # [30, 20, 10, 20, 30] → 谷值在索引 2
        values = [30, 20, 10, 20, 30]
        assert _find_local_minima(values, window=1) == [2]

    def test_multiple_troughs(self) -> None:
        values = [30, 10, 30, 10, 30]
        assert _find_local_minima(values, window=1) == [1, 3]

    def test_no_trough_in_flat_series(self) -> None:
        values = [10, 10, 10, 10]
        assert _find_local_minima(values, window=1) == []


# ── identify_emotion_cycles ────────────────────────────────


class TestIdentifyEmotionCycles:
    def test_typical_cycle_with_repair(self) -> None:
        """典型周期段：峰 → 谷 → 修复。

        构造序列（近 15 日）：
        日 0-2: 上升（涨停 10/20/30）
        日 3: 峰值 80
        日 4-6: 下降（涨停 60/40/20）
        日 7: 谷值 10
        日 8: 修复（涨停 15，回升 50% > 30% 阈值）
        日 9-14: 稳定
        """
        history = [
            _make_emotion("20260701", 10),
            _make_emotion("20260702", 20),
            _make_emotion("20260703", 30),
            _make_emotion("20260704", 80),  # 峰值
            _make_emotion("20260705", 60),
            _make_emotion("20260706", 40),
            _make_emotion("20260707", 20),
            _make_emotion("20260708", 10),  # 谷值
            _make_emotion("20260709", 15),  # 修复（10 → 15 = +50%）
            _make_emotion("20260710", 25),
            _make_emotion("20260711", 30),
            _make_emotion("20260712", 28),
            _make_emotion("20260713", 35),
            _make_emotion("20260714", 40),
            _make_emotion("20260715", 38),
        ]
        segments = identify_emotion_cycles(
            history, min_peak_trough_gap=1, repair_threshold=0.3
        )
        assert len(segments) >= 1
        seg = segments[0]
        assert seg.peak_date == "20260704"
        assert seg.peak_limit_up_count == 80
        assert seg.trough_date == "20260708"
        assert seg.trough_limit_up_count == 10
        assert seg.first_repair_date == "20260709"
        assert seg.first_repair_limit_up == 15

    def test_no_repair_returns_none_for_repair_fields(self) -> None:
        """谷值后无修复（涨停数持续低位）→ first_repair 字段为 None。"""
        history = [
            _make_emotion("20260701", 50),
            _make_emotion("20260702", 80),  # 峰值
            _make_emotion("20260703", 40),
            _make_emotion("20260704", 10),  # 谷值
            _make_emotion("20260705", 11),  # +10% < 30% 阈值，不算修复
            _make_emotion("20260706", 12),  # +20% < 30%，不算修复
            _make_emotion("20260707", 11),
            _make_emotion("20260708", 10),
            _make_emotion("20260709", 12),
            _make_emotion("20260710", 11),
        ]
        segments = identify_emotion_cycles(
            history, min_peak_trough_gap=1, repair_threshold=0.3
        )
        assert len(segments) >= 1
        seg = segments[0]
        assert seg.first_repair_date is None
        assert seg.first_repair_limit_up is None

    def test_insufficient_data_returns_empty(self) -> None:
        """历史 < 5 日 → 返空列表。"""
        history = [
            _make_emotion("20260701", 10),
            _make_emotion("20260702", 20),
            _make_emotion("20260703", 30),
        ]
        assert identify_emotion_cycles(history) == []

    def test_no_peak_returns_empty(self) -> None:
        """单调序列无峰值 → 返空。"""
        history = [
            _make_emotion(f"2026070{i}", i)
            for i in range(1, 10)
        ]
        # 单调递增无局部极大值
        assert identify_emotion_cycles(
            history, min_peak_trough_gap=1
        ) == []

    def test_trough_zero_baseline_repair(self) -> None:
        """谷值涨停数为 0 时，修复判定用绝对增长（防除零）。

        谷值=0 → 任意 >0 都算修复（0 → 5 = 增长 5，比例无穷大但视为修复）。
        """
        history = [
            _make_emotion("20260701", 30),
            _make_emotion("20260702", 50),  # 峰值
            _make_emotion("20260703", 20),
            _make_emotion("20260704", 0),   # 谷值=0（冰点）
            _make_emotion("20260705", 5),   # 修复（0 → 5）
            _make_emotion("20260706", 10),
            _make_emotion("20260707", 15),
            _make_emotion("20260708", 20),
            _make_emotion("20260709", 18),
        ]
        segments = identify_emotion_cycles(
            history, min_peak_trough_gap=1, repair_threshold=0.3
        )
        assert len(segments) >= 1
        seg = segments[0]
        assert seg.trough_limit_up_count == 0
        assert seg.first_repair_date == "20260705"
        assert seg.first_repair_limit_up == 5

    def test_multiple_cycles_returned(self) -> None:
        """两轮峰谷周期 → 返回 2 个 segment。"""
        # 构造两轮完整的峰→谷→修复
        history = [
            # 第一轮
            _make_emotion("20260701", 10),
            _make_emotion("20260702", 50),  # 峰1
            _make_emotion("20260703", 30),
            _make_emotion("20260704", 10),  # 谷1
            _make_emotion("20260705", 20),  # 修复1（+100%）
            # 第二轮
            _make_emotion("20260706", 40),
            _make_emotion("20260707", 60),  # 峰2
            _make_emotion("20260708", 40),
            _make_emotion("20260709", 15),  # 谷2
            _make_emotion("20260710", 25),  # 修复2（+67%）
            _make_emotion("20260711", 30),
            _make_emotion("20260712", 28),
        ]
        segments = identify_emotion_cycles(
            history, min_peak_trough_gap=1, repair_threshold=0.3
        )
        assert len(segments) == 2
        assert segments[0].peak_date == "20260702"
        assert segments[1].peak_date == "20260707"

    def test_peak_without_following_trough_skipped(self) -> None:
        """峰值后无谷值（数据末尾）→ 该峰值被跳过。"""
        history = [
            _make_emotion("20260701", 10),
            _make_emotion("20260702", 50),  # 峰值
            _make_emotion("20260703", 40),
            _make_emotion("20260704", 30),
            _make_emotion("20260705", 20),  # 末尾递减无谷值
        ]
        segments = identify_emotion_cycles(
            history, min_peak_trough_gap=1
        )
        # 峰值后有递减但无局部极小值（边界排除）→ 无 segment
        assert segments == []
