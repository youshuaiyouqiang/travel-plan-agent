"""股票复盘工具装配——按 session_mode 过滤工具集合。

日复盘会话不含 `get_correlation`；周复盘会话包含全部 15 个工具。
"""

from __future__ import annotations

from typing import Literal


def build_stock_tools(session_mode: Literal["daily", "weekly"]) -> list[str]:
    """返回当前会话模式的工具清单。

    Parameters
    ----------
    session_mode : "daily" | "weekly"
        日复盘只返回 14 个常规工具；周复盘追加 `get_correlation`。

    Returns
    -------
    list[str]
        工具名列表（顺序与 yaml 一致，便于对照）。
    """
    # 14 个常规工具（按 yaml 顺序）
    common: list[str] = [
        "get_market_snapshot",
        "get_emotion_indicators",
        "get_emotion_indicators_trend",
        "get_strong_repair_leaders",
        "get_sector_rotation",
        "get_sector_heat_distribution",
        "get_resistant_sectors",
        "get_sector_leaders",
        "get_sector_divergence",
        "get_sector_history",
        "get_watchlist",
        "get_stock_daily",
        "get_signal_stocks",
        "get_limit_stocks",
    ]
    if session_mode == "weekly":
        return common + ["get_correlation"]
    return common
