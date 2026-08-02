"""Task E 单元测试：emotion_dimensions 6 维度计算函数。

设计要点：
- 全部纯函数（无 I/O），测试不 mock 任何外部依赖
- 阈值硬编码（无 AI 发挥空间），断言边界值正确分类
- 14 个测试覆盖 6 维度 + market_style 组合 + 趋势判定
"""

from __future__ import annotations


from domain.stock.emotion_dimensions import (
    compute_authenticity_level,
    compute_breadth_level,
    compute_height_level,
    compute_market_style,
    compute_resilience_level,
    compute_strength_level,
    compute_trend,
    parse_amount_str,
    parse_pct_str,
)


# ── 维度 1：情绪高度（基于分位数）──────────────────────────


class TestComputeHeightLevel:
    def test_high_position_when_pct_above_80(self) -> None:
        # 80 分位 → 高位
        assert compute_height_level(percentile=0.80) == "高位"

    def test_high_position_above_80(self) -> None:
        assert compute_height_level(percentile=0.95) == "高位"

    def test_middle_position_50_to_80(self) -> None:
        assert compute_height_level(percentile=0.50) == "中位"
        assert compute_height_level(percentile=0.79) == "中位"

    def test_low_position_20_to_50(self) -> None:
        assert compute_height_level(percentile=0.20) == "低位"
        assert compute_height_level(percentile=0.49) == "低位"

    def test_very_low_below_20(self) -> None:
        assert compute_height_level(percentile=0.19) == "极低位"
        assert compute_height_level(percentile=0.0) == "极低位"

    def test_insufficient_history_returns_middle(self) -> None:
        """历史 <5 日无法算分位数 → 默认"中位"。"""
        assert compute_height_level(percentile=None) == "中位"


# ── 维度 2：情绪广度（绝对阈值）──────────────────────────


class TestComputeBreadthLevel:
    def test_breadth_broad_rally_ratio_above_3(self) -> None:
        # 涨跌比 3.0 → 普涨（75%+ 上涨）
        assert compute_breadth_level(adv_count=300, decl_count=100) == "普涨"

    def test_breadth_wide_1_5_to_3(self) -> None:
        assert compute_breadth_level(adv_count=150, decl_count=100) == "偏广"

    def test_breadth_balanced_0_67_to_1_5(self) -> None:
        assert compute_breadth_level(adv_count=100, decl_count=100) == "平衡"
        assert compute_breadth_level(adv_count=120, decl_count=100) == "平衡"

    def test_breadth_narrow_0_33_to_0_67(self) -> None:
        assert compute_breadth_level(adv_count=50, decl_count=100) == "偏窄"

    def test_breadth_broad_decline_below_0_33(self) -> None:
        assert compute_breadth_level(adv_count=25, decl_count=100) == "普跌"

    def test_breadth_zero_decl_returns_broad_decline(self) -> None:
        """下跌为 0（全涨）→ 普跌分类不可用，直接返普涨。"""
        assert compute_breadth_level(adv_count=100, decl_count=0) == "普涨"


# ── 维度 3：情绪强度（绝对阈值）──────────────────────────


class TestComputeStrengthLevel:
    def test_strong_avg_above_3_up_count_above_15(self) -> None:
        assert compute_strength_level(avg_chg=3.0, up_count=15) == "强势"

    def test_slightly_strong_avg_above_1_up_count_above_10(self) -> None:
        assert compute_strength_level(avg_chg=1.0, up_count=10) == "偏强"

    def test_neutral_avg_above_neg_1(self) -> None:
        assert compute_strength_level(avg_chg=0.5, up_count=5) == "中性"
        assert compute_strength_level(avg_chg=-1.0, up_count=2) == "中性"

    def test_slightly_weak_avg_above_neg_3(self) -> None:
        assert compute_strength_level(avg_chg=-2.0, up_count=1) == "偏弱"

    def test_weak_avg_below_neg_3(self) -> None:
        assert compute_strength_level(avg_chg=-3.5, up_count=0) == "弱势"


class TestComputeMarketStyle:
    def test_theme_dominant_when_strong_and_high(self) -> None:
        # 强 + 高位 → 题材+趋势共振
        assert compute_market_style(
            strength_level="强势", height_level="高位"
        ) == "题材+趋势共振"

    def test_trend_dominant_when_strong_and_low(self) -> None:
        # 强 + 低位 → 趋势股主导
        assert compute_market_style(
            strength_level="偏强", height_level="低位"
        ) == "趋势股主导"
        assert compute_market_style(
            strength_level="强势", height_level="极低位"
        ) == "趋势股主导"

    def test_theme_when_weak_and_high(self) -> None:
        # 弱 + 高位 → 题材股主导
        assert compute_market_style(
            strength_level="偏弱", height_level="高位"
        ) == "题材股主导"

    def test_weak_market_when_weak_and_low(self) -> None:
        assert compute_market_style(
            strength_level="弱势", height_level="低位"
        ) == "弱势市场"

    def test_mixed_otherwise(self) -> None:
        # 中性强度 + 中位 → 混合
        assert compute_market_style(
            strength_level="中性", height_level="中位"
        ) == "混合"


# ── 维度 4：情绪韧性 ────────────────────────────────────


class TestComputeResilienceLevel:
    def test_no_break_when_total_zero(self) -> None:
        assert compute_resilience_level(
            break_total=0, rebound_count=0
        ) == "无断板"

    def test_strong_when_ratio_above_50_and_count_above_3(self) -> None:
        # 6 断板 4 反包 → 比例 0.67，数量 4 ≥ 3 → 强
        assert compute_resilience_level(
            break_total=6, rebound_count=4
        ) == "强"

    def test_medium_when_ratio_above_30_and_count_above_2(self) -> None:
        # 5 断板 2 反包 → 比例 0.4，数量 2 ≥ 2 → 中
        assert compute_resilience_level(
            break_total=5, rebound_count=2
        ) == "中"

    def test_weak_otherwise(self) -> None:
        # 10 断板 1 反包 → 比例 0.1 → 弱
        assert compute_resilience_level(
            break_total=10, rebound_count=1
        ) == "弱"


# ── 维度 5：情绪真实度 ────────────────────────────────────


class TestComputeAuthenticityLevel:
    def test_authentic_below_15_pct(self) -> None:
        assert compute_authenticity_level(broken_ratio=0.10) == "真实"
        assert compute_authenticity_level(broken_ratio=0.149) == "真实"

    def test_slightly_authentic_15_to_30(self) -> None:
        assert compute_authenticity_level(broken_ratio=0.15) == "偏真"
        assert compute_authenticity_level(broken_ratio=0.299) == "偏真"

    def test_slightly_inflated_30_to_50(self) -> None:
        assert compute_authenticity_level(broken_ratio=0.30) == "偏虚"
        assert compute_authenticity_level(broken_ratio=0.499) == "偏虚"

    def test_inflated_above_50(self) -> None:
        assert compute_authenticity_level(broken_ratio=0.50) == "虚高"
        assert compute_authenticity_level(broken_ratio=0.80) == "虚高"


# ── 维度 6：情绪持续性（趋势判定）──────────────────────


class TestComputeTrend:
    def test_rising_when_slope_positive_above_5_pct(self) -> None:
        # [10, 15, 20, 25, 30] → 明显上升
        assert compute_trend([10, 15, 20, 25, 30]) == "上升"

    def test_falling_when_slope_negative_below_neg_5_pct(self) -> None:
        assert compute_trend([30, 25, 20, 15, 10]) == "下降"

    def test_oscillating_when_slope_near_zero(self) -> None:
        # [20, 15, 25, 15, 20] → 震荡
        assert compute_trend([20, 15, 25, 15, 20]) == "震荡"

    def test_insufficient_data_below_3_points(self) -> None:
        assert compute_trend([10, 20]) == "数据不足"
        assert compute_trend([]) == "数据不足"


# ── 字符串解析辅助函数 ──────────────────────────────────


class TestParsePctStr:
    def test_parse_pct_with_percent_suffix(self) -> None:
        assert parse_pct_str("20.01%") == 20.01

    def test_parse_pct_negative(self) -> None:
        assert parse_pct_str("-3.50%") == -3.50

    def test_parse_pct_returns_zero_for_non_str(self) -> None:
        assert parse_pct_str(None) == 0.0
        assert parse_pct_str(123) == 0.0


class TestParseAmountStr:
    def test_parse_amount_yi(self) -> None:
        # "3.35亿" → 335000000
        assert parse_amount_str("3.35亿") == 335_000_000.0

    def test_parse_amount_wan(self) -> None:
        # "9300万" → 93000000
        assert parse_amount_str("9300万") == 93_000_000.0

    def test_parse_amount_plain_number(self) -> None:
        assert parse_amount_str("123.45") == 123.45

    def test_parse_amount_returns_zero_for_non_str(self) -> None:
        assert parse_amount_str(None) == 0.0
