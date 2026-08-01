"""Task 12 失败测试：emotion 指标纯函数启发式（AGENTS.md §8.1 端口先于实现）。

设计要点：
- 纯函数无 I/O，脱离 SQLite 即可单测
- 4 类计算：valid_limit_up / broken_limit_ratio / max_consecutive_boards
- 与 design 文档 §2.4 "Task 3 失败测试" 一一对应
"""

from __future__ import annotations

import pytest

from domain.stock.heuristics import (
    calculate_broken_limit_ratio,
    count_valid_limit_ups,
    is_valid_limit_up,
    max_consecutive_boards,
)
from domain.stock.models import LimitStock


# ── is_valid_limit_up ────────────────────────────────────


class TestIsValidLimitUp:
    """单股"有效涨停"判定：一次性封死（炸板次数=0 且 首封=末封）。"""

    def test_zero_open_count_same_time_is_valid(self) -> None:
        assert is_valid_limit_up(
            open_count=0, first_limit_time="10:00:00", last_limit_time="10:00:00"
        ) is True

    def test_nonzero_open_count_is_invalid(self) -> None:
        assert is_valid_limit_up(
            open_count=1, first_limit_time="10:00:00", last_limit_time="14:00:00"
        ) is False

    def test_different_first_last_time_is_invalid(self) -> None:
        """炸板后回封不算一次性封死。"""
        assert is_valid_limit_up(
            open_count=0, first_limit_time="10:00:00", last_limit_time="14:00:00"
        ) is False

    def test_none_first_time_is_invalid(self) -> None:
        assert is_valid_limit_up(
            open_count=0, first_limit_time=None, last_limit_time="10:00:00"
        ) is False

    def test_none_last_time_is_invalid(self) -> None:
        assert is_valid_limit_up(
            open_count=0, first_limit_time="10:00:00", last_limit_time=None
        ) is False


# ── count_valid_limit_ups ──────────────────────────────────


class TestCountValidLimitUps:
    """涨停股池中"有效涨停"数。"""

    def test_all_valid_returns_count(self) -> None:
        stocks = [
            LimitStock(
                trade_date="20260730", stock_code=f"{i:06d}", stock_name="X",
                limit_type="up", consecutive_boards=1,
                first_limit_time="10:00:00", last_limit_time="10:00:00",
                open_count=0, is_valid_limit_up=True,
            )
            for i in range(5)
        ]
        assert count_valid_limit_ups(stocks) == 5

    def test_mixed_returns_only_valid(self) -> None:
        stocks = [
            LimitStock(  # 有效
                trade_date="20260730", stock_code="000001", stock_name="A",
                limit_type="up", consecutive_boards=1,
                first_limit_time="10:00:00", last_limit_time="10:00:00",
                open_count=0, is_valid_limit_up=True,
            ),
            LimitStock(  # 炸板后回封（无效）
                trade_date="20260730", stock_code="000002", stock_name="B",
                limit_type="up", consecutive_boards=1,
                first_limit_time="10:00:00", last_limit_time="14:00:00",
                open_count=1, is_valid_limit_up=False,
            ),
            LimitStock(  # 跌停（不算）
                trade_date="20260730", stock_code="000003", stock_name="C",
                limit_type="down", consecutive_boards=0,
                first_limit_time=None, last_limit_time=None,
                open_count=0, is_valid_limit_up=False,
            ),
        ]
        assert count_valid_limit_ups(stocks) == 1

    def test_empty_list_returns_zero(self) -> None:
        assert count_valid_limit_ups([]) == 0


# ── calculate_broken_limit_ratio ───────────────────────────


class TestBrokenLimitRatio:
    """炸板率 = 炸板数 / (涨停数 + 炸板数)。"""

    def test_normal(self) -> None:
        assert calculate_broken_limit_ratio(limit_up_count=50, broken_count=10) == pytest.approx(10 / 60)

    def test_zero_zero_returns_zero(self) -> None:
        """涨停+炸板均为 0 → 0.0（不抛 ZeroDivisionError）。"""
        assert calculate_broken_limit_ratio(limit_up_count=0, broken_count=0) == 0.0

    def test_zero_up_nonzero_broken(self) -> None:
        """极端：0 涨停但有炸板（炸板 = 上板未封死，理论上不计入"涨停"）。"""
        assert calculate_broken_limit_ratio(limit_up_count=0, broken_count=5) == 1.0

    def test_high_up_low_broken(self) -> None:
        assert calculate_broken_limit_ratio(limit_up_count=90, broken_count=5) == pytest.approx(5 / 95)


# ── max_consecutive_boards ─────────────────────────────────


class TestMaxConsecutiveBoards:
    """最高连板 = max(consecutive_boards) where limit_type='up'。"""

    def test_returns_max_from_up_stocks(self) -> None:
        stocks = [
            LimitStock(
                trade_date="20260730", stock_code="000001", stock_name="A",
                limit_type="up", consecutive_boards=3,
                first_limit_time="10:00:00", last_limit_time="10:00:00",
                open_count=0, is_valid_limit_up=True,
            ),
            LimitStock(
                trade_date="20260730", stock_code="000002", stock_name="B",
                limit_type="up", consecutive_boards=5,
                first_limit_time="10:00:00", last_limit_time="10:00:00",
                open_count=0, is_valid_limit_up=True,
            ),
            LimitStock(
                trade_date="20260730", stock_code="000003", stock_name="C",
                limit_type="up", consecutive_boards=2,
                first_limit_time="10:00:00", last_limit_time="10:00:00",
                open_count=0, is_valid_limit_up=True,
            ),
        ]
        assert max_consecutive_boards(stocks) == 5

    def test_empty_returns_zero(self) -> None:
        assert max_consecutive_boards([]) == 0

    def test_no_up_type_returns_zero(self) -> None:
        """全是跌停 → 没有"连板"概念，返 0。"""
        stocks = [
            LimitStock(
                trade_date="20260730", stock_code="000001", stock_name="A",
                limit_type="down", consecutive_boards=0,
                first_limit_time=None, last_limit_time=None,
                open_count=0, is_valid_limit_up=False,
            ),
        ]
        assert max_consecutive_boards(stocks) == 0

    def test_down_stocks_excluded(self) -> None:
        """混跌停时，max 只看涨停股。"""
        stocks = [
            LimitStock(
                trade_date="20260730", stock_code="000001", stock_name="A",
                limit_type="up", consecutive_boards=3,
                first_limit_time="10:00:00", last_limit_time="10:00:00",
                open_count=0, is_valid_limit_up=True,
            ),
            LimitStock(
                trade_date="20260730", stock_code="000002", stock_name="B",
                limit_type="down", consecutive_boards=99,  # 跌停 N 板无意义
                first_limit_time=None, last_limit_time=None,
                open_count=0, is_valid_limit_up=False,
            ),
        ]
        assert max_consecutive_boards(stocks) == 3
