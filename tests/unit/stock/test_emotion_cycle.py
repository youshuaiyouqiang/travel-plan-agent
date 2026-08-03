"""情绪周期得分与阶段判定纯函数单测（开发文档 §9.1）。

设计要点：
- 全部纯函数（无 I/O），测试不 mock 任何外部依赖
- 不依赖 numpy（避免 mypy stub 问题），全部用内置 float 算术
- 覆盖：三风格得分正常 / 降级路径 / 等权合成 / 阶段映射 6 分支 / clamp 边界

测试路径说明：开发文档 §9.1 写的是 ``tests/unit/domain/stock/test_emotion_cycle.py``，
但项目既有约定是 ``tests/unit/stock/``（同目录已有 ``test_emotion_cycles.py`` 复数峰谷检测
单测），本文件沿用既有约定放在 ``tests/unit/stock/``，与同目录兄弟测试一致。
"""

from __future__ import annotations

import pytest

from domain.stock.emotion_cycle import (
    _clamp,
    compute_board_style_score,
    compute_emotion_score,
    compute_raw_phase,
    compute_rebound_style_score,
    compute_trend_style_score,
)


# ── _clamp ────────────────────────────────────────────────


class TestClamp:
    def test_clamp_bounds(self) -> None:
        """归一化超界值 clamp 到 [0, 100]。"""
        assert _clamp(-10, 0, 100) == 0
        assert _clamp(150, 0, 100) == 100
        assert _clamp(50, 0, 100) == 50
        assert _clamp(0, 0, 100) == 0
        assert _clamp(100, 0, 100) == 100

    def test_clamp_custom_range(self) -> None:
        """clamp 支持任意 [lo, hi] 区间。"""
        assert _clamp(-5, -1, 1) == -1
        assert _clamp(5, -1, 1) == 1


# ── 打板风格得分 ───────────────────────────────────────────


class TestBoardStyleScore:
    def test_compute_board_style_score_normal(self) -> None:
        """打板得分正常计算（一阶溢价 + 二阶首末差值）。

        premium=2.0 → first_norm = (2+5)/10*100 = 70
        limit_up 50 vs 3d_ago 40 → second=10 → second_norm = (10+20)/40*100 = 75
        score = 0.6*70 + 0.4*75 = 72.0
        """
        score = compute_board_style_score(
            yesterday_premium=2.0,
            limit_up_count=50,
            limit_up_count_3d_ago=40,
            limit_up_percentile=0.8,  # 有 premium 时不参与
        )
        assert score == pytest.approx(72.0)

    def test_compute_board_style_score_premium_none(self) -> None:
        """溢价 None 时降级用涨停数分位数（0-1 → *100）。

        percentile=0.8 → first_norm = 80
        second 不变 = 75
        score = 0.6*80 + 0.4*75 = 78.0
        """
        score = compute_board_style_score(
            yesterday_premium=None,
            limit_up_count=50,
            limit_up_count_3d_ago=40,
            limit_up_percentile=0.8,
        )
        assert score == pytest.approx(78.0)

    def test_compute_board_style_score_premium_and_percentile_none(self) -> None:
        """溢价与分位数都 None 时，一阶降级为 50（中性），二阶仍可算。

        first_norm = 50
        second = 10 → second_norm = 75
        score = 0.6*50 + 0.4*75 = 60.0
        """
        score = compute_board_style_score(
            yesterday_premium=None,
            limit_up_count=50,
            limit_up_count_3d_ago=40,
            limit_up_percentile=None,
        )
        assert score == pytest.approx(60.0)

    def test_compute_board_style_score_3d_ago_none(self) -> None:
        """3 日前值 None（冷启动）时，二阶动量视为 0。

        premium=2.0 → first_norm = 70
        second = 0 → second_norm = (0+20)/40*100 = 50
        score = 0.6*70 + 0.4*50 = 62.0
        """
        score = compute_board_style_score(
            yesterday_premium=2.0,
            limit_up_count=50,
            limit_up_count_3d_ago=None,
            limit_up_percentile=0.8,
        )
        assert score == pytest.approx(62.0)

    def test_compute_board_style_score_clamps_outliers(self) -> None:
        """一阶/二阶超界值被 clamp 到 [0, 100]。"""
        # premium=100 → first_norm = (100+5)/10*100 = 1050 → clamp 100
        # second = 50-40 = 10 → second_norm = 75
        # score = 0.6*100 + 0.4*75 = 90.0
        score_high = compute_board_style_score(
            yesterday_premium=100.0,
            limit_up_count=50,
            limit_up_count_3d_ago=40,
            limit_up_percentile=None,
        )
        assert score_high == pytest.approx(90.0)

        # premium=-100 → first_norm = (-100+5)/10*100 = -950 → clamp 0
        # score = 0.6*0 + 0.4*75 = 30.0
        score_low = compute_board_style_score(
            yesterday_premium=-100.0,
            limit_up_count=50,
            limit_up_count_3d_ago=40,
            limit_up_percentile=None,
        )
        assert score_low == pytest.approx(30.0)


# ── 趋势风格得分 ───────────────────────────────────────────


class TestTrendStyleScore:
    def test_compute_trend_style_score_normal(self) -> None:
        """趋势得分正常计算。

        top20_avg_chg=1.5 → first_norm = (1.5+3)/6*100 = 75
        adv 3000 vs 3d_ago 2500 → second=500 → second_norm = (500+500)/1000*100 = 100
        score = 0.6*75 + 0.4*100 = 85.0
        """
        score = compute_trend_style_score(
            top20_avg_chg=1.5,
            adv_count=3000,
            adv_count_3d_ago=2500,
            adv_decl_ratio=2.0,  # 有 top20 时不参与
        )
        assert score == pytest.approx(85.0)

    def test_compute_trend_style_score_top20_none(self) -> None:
        """top20_avg_chg None 时降级用 adv_decl_ratio 归一化。

        ratio=2.0 → first_norm = 2.0/(1+2.0)*100 = 66.666...
        second = 500 → second_norm = 100
        score = 0.6*(200/3) + 0.4*100 = 40 + 40 = 80.0
        """
        score = compute_trend_style_score(
            top20_avg_chg=None,
            adv_count=3000,
            adv_count_3d_ago=2500,
            adv_decl_ratio=2.0,
        )
        assert score == pytest.approx(80.0)

    def test_compute_trend_style_score_top20_and_ratio_none(self) -> None:
        """top20 与 adv_decl_ratio 都 None 时，一阶降级 50（中性）。

        first_norm = 50
        second = 500 → second_norm = 100
        score = 0.6*50 + 0.4*100 = 70.0
        """
        score = compute_trend_style_score(
            top20_avg_chg=None,
            adv_count=3000,
            adv_count_3d_ago=2500,
            adv_decl_ratio=None,
        )
        assert score == pytest.approx(70.0)

    def test_compute_trend_style_score_adv_count_none(self) -> None:
        """adv_count None（无广度数据）时，二阶动量视为 0。

        top20_avg_chg=1.5 → first_norm = 75
        second = 0 → second_norm = (0+500)/1000*100 = 50
        score = 0.6*75 + 0.4*50 = 65.0
        """
        score = compute_trend_style_score(
            top20_avg_chg=1.5,
            adv_count=None,
            adv_count_3d_ago=2500,
            adv_decl_ratio=2.0,
        )
        assert score == pytest.approx(65.0)


# ── 反包风格得分 ───────────────────────────────────────────


class TestReboundStyleScore:
    def test_compute_rebound_style_score_none(self) -> None:
        """反包成功率 None → 返回 None（无降级，全局合成跳过）。"""
        assert compute_rebound_style_score(
            rebound_ratio=None, rebound_ratio_3d_ago=0.4
        ) is None

    def test_compute_rebound_style_score_normal(self) -> None:
        """反包得分正常计算。

        ratio=0.6 → first_norm = 60
        second = 0.6-0.6 = 0 → second_norm = (0+0.3)/0.6*100 = 50
        score = 0.6*60 + 0.4*50 = 56.0
        """
        score = compute_rebound_style_score(
            rebound_ratio=0.6, rebound_ratio_3d_ago=0.6
        )
        assert score == pytest.approx(56.0)

    def test_compute_rebound_style_score_3d_ago_none(self) -> None:
        """3 日前值 None 时，二阶动量视为 0。

        ratio=0.6 → first_norm = 60
        second = 0 → second_norm = 50
        score = 0.6*60 + 0.4*50 = 56.0
        """
        score = compute_rebound_style_score(
            rebound_ratio=0.6, rebound_ratio_3d_ago=None
        )
        assert score == pytest.approx(56.0)


# ── 全局情绪得分 ───────────────────────────────────────────


class TestEmotionScore:
    def test_compute_emotion_score_equal_weight(self) -> None:
        """等权合成，None 跳过。

        (60+40+50)/3 = 50.0
        """
        assert compute_emotion_score(60.0, 40.0, 50.0) == pytest.approx(50.0)

    def test_compute_emotion_score_skip_none(self) -> None:
        """部分 None 跳过，只取非 None 的等权平均。

        (60+40)/2 = 50.0
        """
        assert compute_emotion_score(60.0, None, 40.0) == pytest.approx(50.0)

    def test_compute_emotion_score_all_none(self) -> None:
        """全 None 返回 50.0 中性。"""
        assert compute_emotion_score(None, None, None) == pytest.approx(50.0)

    def test_compute_emotion_score_single(self) -> None:
        """只有一个风格有值时，全局得分 = 该值。"""
        assert compute_emotion_score(72.0, None, None) == pytest.approx(72.0)


# ── 阶段判定 ───────────────────────────────────────────────


class TestComputeRawPhase:
    def test_compute_raw_phase_高潮_过热(self) -> None:
        """得分 ≥ 80 → 高潮（任意动量）。"""
        assert compute_raw_phase(85.0, 80.0) == "高潮"
        assert compute_raw_phase(80.0, None) == "高潮"
        assert compute_raw_phase(95.0, 50.0) == "高潮"

    def test_compute_raw_phase_强修复_高位扩散(self) -> None:
        """60–80 + 动量 > 0 → 强修复。"""
        assert compute_raw_phase(70.0, 60.0) == "强修复"  # momentum=10
        assert compute_raw_phase(65.0, 64.0) == "强修复"  # momentum=1 > 0

    def test_compute_raw_phase_高潮_高位减速(self) -> None:
        """60–80 + 动量 ≤ 0 → 高潮（高位见顶 / 减速）。"""
        assert compute_raw_phase(70.0, 75.0) == "高潮"  # momentum=-5 ≤ 0
        assert compute_raw_phase(65.0, 70.0) == "高潮"  # momentum=-5 ≤ 0

    def test_compute_raw_phase_弱修复_中位加速(self) -> None:
        """40–60 + 动量 > +5 → 强修复（中位加速）。"""
        assert compute_raw_phase(50.0, 40.0) == "强修复"  # momentum=10 > 5

    def test_compute_raw_phase_弱分歧_中位回落(self) -> None:
        """40–60 + 动量 < −5 → 弱分歧。"""
        assert compute_raw_phase(50.0, 60.0) == "弱分歧"  # momentum=-10 < -5

    def test_compute_raw_phase_弱修复_中位震荡(self) -> None:
        """40–60 + 动量在 [−5, +5] → 弱修复（中位震荡偏修复）。"""
        assert compute_raw_phase(50.0, 48.0) == "弱修复"  # momentum=2
        assert compute_raw_phase(50.0, 52.0) == "弱修复"  # momentum=-2
        assert compute_raw_phase(50.0, 55.0) == "弱修复"  # momentum=-5 边界
        assert compute_raw_phase(50.0, 45.0) == "弱修复"  # momentum=5 边界

    def test_compute_raw_phase_弱修复_低位反弹(self) -> None:
        """20–40 + 动量 > +5 → 弱修复（低位反弹）。"""
        assert compute_raw_phase(30.0, 20.0) == "弱修复"  # momentum=10 > 5

    def test_compute_raw_phase_强分歧_低位续跌(self) -> None:
        """20–40 + 动量 < −5 → 强分歧。"""
        assert compute_raw_phase(30.0, 45.0) == "强分歧"  # momentum=-15 < -5

    def test_compute_raw_phase_弱修复_低位震荡筑底(self) -> None:
        """20–40 + 动量在 [−5, +5] → 弱修复（低位震荡筑底）。"""
        assert compute_raw_phase(30.0, 28.0) == "弱修复"  # momentum=2
        assert compute_raw_phase(30.0, 32.0) == "弱修复"  # momentum=-2

    def test_compute_raw_phase_冰点(self) -> None:
        """< 20 + 动量 ≤ 0 → 冰点。"""
        assert compute_raw_phase(15.0, 20.0) == "冰点"  # momentum=-5 ≤ 0
        assert compute_raw_phase(10.0, 10.0) == "冰点"  # momentum=0 ≤ 0

    def test_compute_raw_phase_冰点反弹_弱修复(self) -> None:
        """< 20 + 动量 > 0 → 弱修复（冰点反弹）。"""
        assert compute_raw_phase(15.0, 10.0) == "弱修复"  # momentum=5 > 0
        assert compute_raw_phase(18.0, 8.0) == "弱修复"  # momentum=10 > 0

    def test_compute_raw_phase_无历史降级(self) -> None:
        """score_3d_ago=None 动量视为 0，按得分粗判。

        70 → momentum=0, not >0 → 高潮
        50 → momentum=0, in [-5,5] → 弱修复
        30 → momentum=0, not <-5 → 弱修复
        15 → momentum=0, not >0 → 冰点
        """
        assert compute_raw_phase(70.0, None) == "高潮"
        assert compute_raw_phase(50.0, None) == "弱修复"
        assert compute_raw_phase(30.0, None) == "弱修复"
        assert compute_raw_phase(15.0, None) == "冰点"

    def test_compute_raw_phase_boundary_80(self) -> None:
        """80 分边界：≥80 直接高潮，不受动量影响。"""
        assert compute_raw_phase(80.0, 90.0) == "高潮"  # momentum=-10 但 ≥80
        assert compute_raw_phase(79.9, 70.0) == "强修复"  # 60-80 + momentum>0

    def test_compute_raw_phase_boundary_60(self) -> None:
        """60 分边界：60-80 分支。"""
        assert compute_raw_phase(60.0, 50.0) == "强修复"  # momentum=10 > 0
        assert compute_raw_phase(59.9, 50.0) == "强修复"  # 40-60, momentum=9.9 > 5
