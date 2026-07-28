"""akshare 薄包装层（Task 2 最小实现）。

职责：
- 包装 akshare 调用，转换 DataFrame → DTO
- 捕获 requests / 解析层具体异常并包装为 AkshareFetchError，保留异常链
  （AGENTS.md §5：禁止 except Exception 一把梭；akshare 无统一异常基类）
- 提供启发式判定函数 is_valid_limit_up
- 不做缓存（缓存由 cache_repository 负责，Task 3 实现）

边界：
- 仅用于"写路径"（fetcher / pipeline 调 akshare）
- 复盘 Service（review_service）只能通过 StockDataSource 端口读缓存，
  不得直接 import akshare（任务约束：禁止 review_service 直连 akshare）
"""

from __future__ import annotations

import logging
from typing import Any

import akshare as ak
import pandas as pd
import requests

from domain.stock.models import LimitStock
from domain.stock.ports import StockDataSource

logger = logging.getLogger(__name__)


class AkshareFetchError(Exception):
    """akshare 抓取失败异常。包装 requests / 解析层具体异常并保留异常链。"""


# akshare 抛出的具体异常类型（无统一基类，按用户约束精确捕获）
_AKSHARE_EXC: tuple[type[BaseException], ...] = (
    requests.RequestException,  # 网络层
    ValueError,  # 解析 / 类型转换
    KeyError,  # DataFrame 列名缺失
    IndexError,  # DataFrame 为空 / 越界
)


def is_valid_limit_up(
    open_count: int, first_time: str | None, last_time: str | None
) -> bool:
    """有效涨停 = 一次性封死（炸板次数=0 且 首封=末封时间）。

    数据定义（SQL 查询条件），不是判定阈值。
    首末时间为空时返回 False（数据缺失视为无效）。
    """
    if first_time is None or last_time is None:
        return False
    return open_count == 0 and first_time == last_time


def fetch_zt_pool(trade_date: str) -> list[LimitStock]:
    """抓取涨停股池，返回 LimitStock DTO 列表。

    akshare 函数：``ak.stock_zt_pool_em(date=...)``，返回 DataFrame。
    失败时抛 AkshareFetchError，保留原始异常链（__cause__）。
    """
    try:
        df: pd.DataFrame = ak.stock_zt_pool_em(date=trade_date)
    except _AKSHARE_EXC as e:
        raise AkshareFetchError(
            f"fetch_zt_pool failed for trade_date={trade_date}"
        ) from e

    if df is None or len(df) == 0:
        return []

    result: list[LimitStock] = []
    for _, row in df.iterrows():
        try:
            first_time = str(row.get("首次封板时间", "") or "") or None
            last_time = str(row.get("最后封板时间", "") or "") or None
            open_count = int(row.get("炸板次数", 0) or 0)
            result.append(
                LimitStock(
                    trade_date=trade_date,
                    stock_code=str(row["代码"]),
                    stock_name=str(row["名称"]),
                    limit_type="up",
                    consecutive_boards=int(row.get("连板数", 1) or 1),
                    first_limit_time=first_time,
                    last_limit_time=last_time,
                    open_count=open_count,
                    is_valid_limit_up=is_valid_limit_up(
                        open_count, first_time, last_time
                    ),
                )
            )
        except _AKSHARE_EXC as e:
            # 单行解析失败：跳过该行，记录 warning，整体流程不中断
            logger.warning(
                "fetch_zt_pool skipped malformed row date=%s err=%s",
                trade_date,
                e,
            )
            continue
    return result


class AkshareClient:
    """akshare 数据源客户端——StockDataSource 协议的 akshare 实现。

    Task 2 最小实现：仅完成 ``get_limit_stocks``（基于 fetch_zt_pool）。
    其余 14 个方法在 Task 3 起的 fetcher / pipeline 阶段补全，
    此处先以 NotImplementedError 站位，确保 StockDataSource 协议完整。
    """

    async def get_limit_stocks(self, trade_date: str) -> list[LimitStock]:
        """从 akshare 抓取涨停股池。"""
        return fetch_zt_pool(trade_date)

    # ── Task 3+ 补全的占位方法（NotImplementedError 而非 ...） ──
    async def get_market_snapshot(self, trade_date: str) -> Any:  # type: ignore[override]
        raise NotImplementedError("get_market_snapshot 计划在 Task 3 实现")

    async def get_emotion_indicators(self, trade_date: str) -> Any:  # type: ignore[override]
        raise NotImplementedError("get_emotion_indicators 计划在 Task 3 实现")

    async def get_emotion_indicators_trend(
        self, end_date: str, days: int
    ) -> Any:  # type: ignore[override]
        raise NotImplementedError(
            "get_emotion_indicators_trend 计划在 Task 3 实现"
        )

    async def get_watchlist(self) -> Any:  # type: ignore[override]
        raise NotImplementedError("get_watchlist 计划在 Task 3/4 实现")

    async def get_stock_daily(self, stock_code: str, days: int) -> Any:  # type: ignore[override]
        raise NotImplementedError("get_stock_daily 计划在 Task 3 实现")

    async def get_signal_stocks(self, trade_date: str) -> Any:  # type: ignore[override]
        raise NotImplementedError("get_signal_stocks 计划在 Task 3 实现")

    async def get_sector_rotation(self, trade_date: str) -> Any:  # type: ignore[override]
        raise NotImplementedError("get_sector_rotation 计划在 Task 3 实现")

    async def get_sector_heat_distribution(self, trade_date: str) -> Any:  # type: ignore[override]
        raise NotImplementedError(
            "get_sector_heat_distribution 计划在 Task 3 实现"
        )

    async def get_strong_repair_leaders(self) -> Any:  # type: ignore[override]
        raise NotImplementedError(
            "get_strong_repair_leaders 计划在 Task 3 实现"
        )

    async def get_resistant_sectors(self, trade_date: str) -> Any:  # type: ignore[override]
        raise NotImplementedError("get_resistant_sectors 计划在 Task 3 实现")

    async def get_sector_leaders(self, sector_name: str) -> Any:  # type: ignore[override]
        raise NotImplementedError("get_sector_leaders 计划在 Task 3 实现")

    async def get_sector_divergence(self, trade_date: str) -> Any:  # type: ignore[override]
        raise NotImplementedError("get_sector_divergence 计划在 Task 3 实现")

    async def get_correlation(self, end_date: str, days: int) -> Any:  # type: ignore[override]
        raise NotImplementedError("get_correlation 计划在 Task 3 实现（周复盘专用）")

    async def get_sector_history(self, sector_name: str, days: int) -> Any:  # type: ignore[override]
        raise NotImplementedError("get_sector_history 计划在 Task 3 实现")


# Protocol 形式确认：mypy/IDE 静态检查时类满足 StockDataSource 协议
_ = StockDataSource  # noqa: F841 — 仅作 import 校验
