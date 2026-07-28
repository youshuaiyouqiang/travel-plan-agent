"""情绪指标聚合器——从 LimitStock 列表计算截面指标。

Task 3 最小实现：仅实现 3 个核心函数。
- calculate_broken_limit_ratio: 炸板率 = 炸板数 / (涨停 + 炸板)
- calculate_max_consecutive_boards: 最高连板
- count_valid_limit_up: 有效涨停数

聚合器是纯函数（无状态），便于测试。
不调用 akshare、不访问 SQLite——只接收内存中的 LimitStock 列表。
"""

from __future__ import annotations

from domain.stock.models import LimitStock


def calculate_broken_limit_ratio(limit_up_count: int, broken_count: int) -> float:
    """计算炸板率 = 炸板数 / (涨停数 + 炸板数)。

    分母为 0 时返回 0.0（避免除零）。炸板数不可能为负——但函数不强制校验，
    异常输入由调用方负责。

    Args:
        limit_up_count: 涨停封死股票数。
        broken_count: 炸板股票数（曾封板但未守住）。

    Returns:
        炸板率，区间 [0.0, 1.0]。分母为 0 时返回 0.0。
    """
    total = limit_up_count + broken_count
    if total <= 0:
        return 0.0
    return broken_count / total


def calculate_max_consecutive_boards(stocks: list[LimitStock]) -> int:
    """计算最高连板数 = limit_stocks 中 consecutive_boards 的最大值。

    空列表返回 0（避免 max() 抛 ValueError）。

    Args:
        stocks: 涨停股池 DTO 列表。

    Returns:
        最高连板数；空列表时为 0。
    """
    if not stocks:
        return 0
    return max(s.consecutive_boards for s in stocks)


def count_valid_limit_up(stocks: list[LimitStock]) -> int:
    """计算有效涨停数 = is_valid_limit_up=True 的股票数。

    Args:
        stocks: 涨停股池 DTO 列表。

    Returns:
        有效涨停数；空列表时为 0。
    """
    return sum(1 for s in stocks if s.is_valid_limit_up)
