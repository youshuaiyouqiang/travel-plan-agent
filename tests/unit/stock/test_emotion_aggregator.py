"""Task 3 失败测试：情绪指标聚合器。

覆盖：
- 炸板率 = 炸板数 / (涨停数 + 炸板数)
- 最高连板 = limit_stocks 中 consecutive_boards 的 max
- 有效涨停数 = is_valid_limit_up=True 的股票数

不访问真实网络——用 fake LimitStock 列表。
运行前 infrastructure/stock/emotion_aggregator.py 不存在，本测试应全部失败。
"""

from __future__ import annotations

from domain.stock.models import LimitStock


def _mk_limit(
    code: str, boards: int, open_count: int, first: str, last: str
) -> LimitStock:
    return LimitStock(
        trade_date="20260728",
        stock_code=code,
        stock_name=f"STK{code}",
        limit_type="up",
        consecutive_boards=boards,
        first_limit_time=first,
        last_limit_time=last,
        open_count=open_count,
        is_valid_limit_up=(open_count == 0 and first == last),
    )


def test_broken_limit_ratio_calculation() -> None:
    """炸板率 = 炸板数 / (涨停数 + 炸板数)。空时分母=0 返回 0.0。"""
    from infrastructure.stock.emotion_aggregator import calculate_broken_limit_ratio

    assert calculate_broken_limit_ratio(limit_up_count=50, broken_count=10) == 10 / 60
    assert calculate_broken_limit_ratio(limit_up_count=0, broken_count=0) == 0.0
    assert calculate_broken_limit_ratio(limit_up_count=100, broken_count=0) == 0.0


def test_max_consecutive_boards() -> None:
    """最高连板 = limit_stocks 中 consecutive_boards 的 max。空列表返回 0。"""
    from infrastructure.stock.emotion_aggregator import calculate_max_consecutive_boards

    stocks = [
        _mk_limit("001", boards=3, open_count=0, first="09:30:00", last="09:30:00"),
        _mk_limit("002", boards=5, open_count=0, first="10:00:00", last="10:00:00"),
        _mk_limit("003", boards=1, open_count=1, first="09:30:00", last="14:20:00"),
    ]
    assert calculate_max_consecutive_boards(stocks) == 5
    assert calculate_max_consecutive_boards([]) == 0


def test_valid_limit_up_count() -> None:
    """有效涨停数 = is_valid_limit_up=True 的股票数。"""
    from infrastructure.stock.emotion_aggregator import count_valid_limit_up

    stocks = [
        _mk_limit("001", boards=1, open_count=0, first="09:30:00", last="09:30:00"),
        _mk_limit("002", boards=1, open_count=1, first="09:30:00", last="14:20:00"),
        _mk_limit("003", boards=2, open_count=0, first="10:00:00", last="10:00:00"),
    ]
    assert count_valid_limit_up(stocks) == 2
    assert count_valid_limit_up([]) == 0
