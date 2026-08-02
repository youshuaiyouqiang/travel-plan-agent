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


def is_st_stock(stock_name: str | None) -> bool:
    """判定股票名是否为 ST / *ST / 退市股。

    业务背景（Bug⑨）：ST 股 / *ST 股 / 退市股 涨跌幅限制不同（±5% vs ±10% vs 自由），
    业务上"涨停数"通常指**普涨停**（±10% 涨停股），不应混入 ST 涨停。
    fetcher 抓取后过滤 ST 股写入 limit_stocks_daily，emotion_daily 聚合
    字段（limit_up_count / valid_limit_up_count / top_board_leaders /
    broken_limit_ratio）天然基于 limit_stocks_daily 计算，自动剔除 ST。

    Args:
        stock_name: 股票名称（来自 akshare ``stock_zt_pool_em`` /
            ``stock_zt_pool_dtgc_em`` 的"名称"列）。

    Returns:
        True 表示该股为 ST/*ST/退市股，应从涨停数中剔除。
    """
    if not stock_name:
        return False
    # 退市股 / 退整理期 系列
    if "退" in stock_name:
        return True
    # ST / *ST 系列
    return "ST" in stock_name.upper()


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
