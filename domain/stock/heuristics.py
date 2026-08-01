"""股票复盘启发式纯函数（AGENTS.md §8.1 端口先于实现 + §2 域层不依赖 I/O）。

设计要点：
- 全部为纯函数，无 I/O / 无外部依赖（不读 SQLite / 不调 akshare）
- 可独立单测；fetcher / 缓存层调它们做字段计算
- 命名前缀区分：单股用 ``is_*`` / ``calculate_*``，列表聚合用 ``count_*`` / ``*_boards``

边界：
- 本模块**禁止** import infrastructure / akshare / sqlite3
- 算法定义见 docs/superpowers/plans/2026-07-26-stock-review-agent.md §2.4
"""

from __future__ import annotations

from typing import Iterable

from domain.stock.models import LimitStock


# ── 单股判定 ──────────────────────────────────────────────


def is_valid_limit_up(
    open_count: int, first_limit_time: str | None, last_limit_time: str | None
) -> bool:
    """单股"有效涨停"判定：一次性封死。

    Args:
        open_count: 炸板次数（open / reopen 计数）。
        first_limit_time: 首次封板时间（HH:MM:SS），未封板则为 None。
        last_limit_time: 末次封板时间（HH:MM:SS），未封板则为 None。

    Returns:
        True 当且仅当 open_count == 0 且 first == last（一次性封死，无回开）。
    """
    if first_limit_time is None or last_limit_time is None:
        return False
    return open_count == 0 and first_limit_time == last_limit_time


# ── 列表聚合 ──────────────────────────────────────────────


def count_valid_limit_ups(stocks: Iterable[LimitStock]) -> int:
    """涨停股池中满足 ``is_valid_limit_up`` 条件的股数。"""
    return sum(
        1 for s in stocks
        if s.limit_type == "up" and is_valid_limit_up(
            s.open_count, s.first_limit_time, s.last_limit_time
        )
    )


def max_consecutive_boards(stocks: Iterable[LimitStock]) -> int:
    """最高连板 = max(consecutive_boards) where limit_type == 'up'。

    空列表 / 全跌停 / 无涨停股均返回 0（避免下游 None 比较）。
    """
    boards = [s.consecutive_boards for s in stocks if s.limit_type == "up"]
    return max(boards) if boards else 0


# ── 简单算式 ──────────────────────────────────────────────


def calculate_broken_limit_ratio(limit_up_count: int, broken_count: int) -> float:
    """炸板率 = 炸板数 / (涨停数 + 炸板数)。

    分母为 0 时返回 0.0（不抛 ZeroDivisionError），便于下游直接格式化。
    涨停为 0 但炸板 > 0 时（罕见：全部上板未封死），返回 1.0。
    """
    denom = limit_up_count + broken_count
    if denom == 0:
        return 0.0
    return broken_count / denom
