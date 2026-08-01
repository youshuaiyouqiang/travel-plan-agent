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

from domain.stock.models import (
    EmotionRawData,
    LimitStock,
    MarketIndexRow,
    SectorDaily,
)
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


# Task 13：大盘指数 3 个代码（上证/深证/创业板）
MARKET_INDEX_CODES: tuple[str, ...] = (
    "sh000001",  # 上证指数
    "sz399001",  # 深证成指
    "sz399006",  # 创业板指
)


def _to_yyyymmdd(date_str: str) -> str | None:
    """'YYYY-MM-DD' 或 'YYYY/MM/DD' → 'YYYYMMDD'；非法返回 None。"""
    if not date_str:
        return None
    s = str(date_str).strip().replace("-", "").replace("/", "")
    return s if len(s) == 8 and s.isdigit() else None


def fetch_market_index(trade_date: str) -> list[MarketIndexRow]:
    """抓取 3 个大盘指数（上证/深证/创业板）的指定日数据。

    akshare 函数：``ak.stock_zh_index_daily(symbol=...)``，返回 DataFrame
    （含 date/open/close/high/low/volume 等列）。对每个指数分别拉一次后
    过滤到 ``trade_date`` 那天。

    失败时抛 AkshareFetchError，保留原始异常链（__cause__）。
    """
    target = _to_yyyymmdd(trade_date)
    if target is None:
        raise AkshareFetchError(
            f"fetch_market_index invalid trade_date={trade_date!r}"
        )

    rows: list[MarketIndexRow] = []
    for code in MARKET_INDEX_CODES:
        try:
            df: pd.DataFrame = ak.stock_zh_index_daily(symbol=code)
        except _AKSHARE_EXC as e:
            raise AkshareFetchError(
                f"fetch_market_index failed for symbol={code} date={trade_date}"
            ) from e

        if df is None or len(df) == 0:
            logger.warning(
                "fetch_market_index: empty df for symbol=%s date=%s",
                code, trade_date,
            )
            continue

        # 找到 trade_date 那一行
        # akshare 返回的 date 列是 Timestamp 或 'YYYY-MM-DD' 字符串
        match = df[df["date"].astype(str).str.replace("-", "").str.replace("/", "") == target]
        if len(match) == 0:
            logger.warning(
                "fetch_market_index: no row for symbol=%s date=%s",
                code, trade_date,
            )
            continue

        r = match.iloc[0]
        try:
            row = MarketIndexRow(
                trade_date=target,
                index_code=code,
                open=_to_float(r.get("open")),
                close=_to_float(r.get("close")),
                high=_to_float(r.get("high")),
                low=_to_float(r.get("low")),
                volume=_to_float(r.get("volume")),
                pct_chg=_to_float(r.get("pct_chg")),
            )
        except (ValueError, TypeError) as e:
            logger.warning(
                "fetch_market_index: parse failed symbol=%s date=%s err=%s",
                code, trade_date, e,
            )
            continue
        rows.append(row)

    return rows


def _to_float(v: Any) -> float | None:
    """安全地把值转 float；NaN/None/空字符串 → None。"""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    # NaN / inf
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def _df_to_int(df: pd.DataFrame, item: str) -> int:
    """从 ``[{"item": "涨停", "value": 4}, ...]`` 结构的 DataFrame 取 int。

    找不到对应 item 返 0（akshare 接口列值偶发缺失，按 0 处理避免阻断）。
    """
    if df is None or len(df) == 0 or "item" not in df.columns:
        return 0
    match = df[df["item"] == item]
    if len(match) == 0:
        return 0
    val = match.iloc[0].get("value")
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


def _extract_shanghai_total_volume(df: pd.DataFrame) -> float:
    """从 ``stock_zh_index_spot_em`` 返回的截面 DataFrame 取上证成交额。

    返回 0.0（而非 None）— caller（fetcher）会做"未抓到成交额"判定。
    """
    if df is None or len(df) == 0 or "code" not in df.columns or "成交额" not in df.columns:
        return 0.0
    match = df[df["code"] == "sh000001"]
    if len(match) == 0:
        return 0.0
    v = _to_float(match.iloc[0].get("成交额"))
    return v if v is not None else 0.0


def fetch_emotion_daily(trade_date: str) -> EmotionRawData:
    """抓取"原始"情绪指标（Task 12）：涨停/跌停/炸板 + 两市成交额。

    二次加工（valid_count / broken_ratio / max_boards / volume_change_pct /
    yesterday_premium）由 ``emotion_daily_fetcher.run`` 调
    ``domain.stock.heuristics`` + 读 ``limit_stocks_daily`` 完成，
    不在 akshare 包装层做聚合。

    Returns:
        EmotionRawData 单一对象（一天一行）；akshare 失败抛 AkshareFetchError。
    """
    target = _to_yyyymmdd(trade_date)
    if target is None:
        raise AkshareFetchError(
            f"fetch_emotion_daily invalid trade_date={trade_date!r}"
        )

    # 1) 拉涨停/跌停/炸板截面（ak.stock_market_activity_legu）
    try:
        activity_df: pd.DataFrame = ak.stock_market_activity_legu()
    except _AKSHARE_EXC as e:
        raise AkshareFetchError(
            f"fetch_emotion_daily stock_market_activity_legu failed date={trade_date}"
        ) from e

    limit_up = _df_to_int(activity_df, "涨停")
    limit_down = _df_to_int(activity_df, "跌停")
    broken = _df_to_int(activity_df, "炸板")

    # 2) 拉两市成交额（ak.stock_zh_index_spot_em）— 取上证代码 sh000001
    try:
        spot_df: pd.DataFrame = ak.stock_zh_index_spot_em()
    except _AKSHARE_EXC as e:
        raise AkshareFetchError(
            f"fetch_emotion_daily stock_zh_index_spot_em failed date={trade_date}"
        ) from e
    total_volume = _extract_shanghai_total_volume(spot_df)

    if limit_up == 0 and limit_down == 0 and total_volume == 0.0:
        # 三个数都拿不到，视为空数据（接口返空 / 非交易日）
        raise AkshareFetchError(
            f"fetch_emotion_daily empty data for date={trade_date} "
            f"(limit_up=0, limit_down=0, total_volume=0)"
        )

    return EmotionRawData(
        trade_date=target,
        limit_up_count=limit_up,
        limit_down_count=limit_down,
        broken_count=broken,
        total_volume=total_volume,
    )


def fetch_sector_daily(trade_date: str) -> list[SectorDaily]:
    """抓取所有板块的单日涨跌幅（约 100+ 个行业板块）。

    akshare 函数：``ak.stock_board_industry_name_em()``，返回 DataFrame
    包含列：``板块名称``、``板块代码``、``涨跌幅``、``领涨股``、``领涨股代码`` 等。
    该接口为**全量截面**（不带日期参数），fetcher 写入时用调用方传入
    的 ``trade_date`` 作为统一日期标签（与 akshare 实际返回的当天数据对齐）。

    Returns:
        SectorDaily 列表。akshare 失败/空数据时返回 []。
    """
    target = _to_yyyymmdd(trade_date)
    if target is None:
        raise AkshareFetchError(
            f"fetch_sector_daily invalid trade_date={trade_date!r}"
        )

    try:
        df: pd.DataFrame = ak.stock_board_industry_name_em()
    except _AKSHARE_EXC as e:
        raise AkshareFetchError(
            f"fetch_sector_daily stock_board_industry_name_em failed date={trade_date}"
        ) from e

    if df is None or len(df) == 0:
        logger.warning("fetch_sector_daily: empty df date=%s", trade_date)
        return []

    rows: list[SectorDaily] = []
    for _, r in df.iterrows():
        name = r.get("板块名称")
        code = r.get("板块代码")
        # 缺核心字段 → 跳过
        if not name or not code:
            continue
        leader_code = r.get("领涨股代码")
        leading = [leader_code] if leader_code else []
        try:
            rows.append(
                SectorDaily(
                    trade_date=target,
                    sector_code=str(code),
                    sector_name=str(name),
                    pct_chg=_to_float(r.get("涨跌幅")),
                    leading_stock_codes=leading,
                    # limit_up_count 在 Task 14 阶段由 fetcher 填 0；
                    # 后续可由板块龙头 fetcher 二次加工（避免 N+1 akshare 调用）
                    limit_up_count=0,
                )
            )
        except (ValueError, TypeError) as e:
            logger.warning(
                "fetch_sector_daily: parse failed name=%s code=%s err=%s",
                name, code, e,
            )
            continue
    return rows


class AkshareClient:
    """akshare 数据源客户端——StockDataSource 协议的 akshare 实现。

    Task 2 最小实现：仅完成 ``get_limit_stocks``（基于 fetch_zt_pool）。
    其余 14 个方法在 Task 3 起的 fetcher / pipeline 阶段补全，
    此处先以 NotImplementedError 站位，确保 StockDataSource 协议完整。
    """

    async def get_limit_stocks(self, trade_date: str) -> list[LimitStock]:
        """从 akshare 抓取涨停股池。"""
        return fetch_zt_pool(trade_date)

    # ── Task 13：大盘指数 fetcher ──
    async def get_market_index(self, trade_date: str) -> list[MarketIndexRow]:
        """从 akshare 抓取 3 个指数（上证/深证/创业板）的指定日数据。

        Returns:
            MarketIndexRow 列表（通常 3 条）。akshare 失败/空数据时返回 []。
        """
        return fetch_market_index(trade_date)

    # ── Task 12：情绪指标 fetcher ──
    async def fetch_emotion_daily(self, trade_date: str) -> EmotionRawData:
        """从 akshare 抓取当日情绪指标（涨停/跌停/炸板/成交额）。

        Returns:
            EmotionRawData 单对象。akshare 失败时抛 AkshareFetchError，
            由 emotion_daily_fetcher.run 捕获并 log warning 返 0。
        """
        return fetch_emotion_daily(trade_date)

    # ── Task 14：板块日线 fetcher ──
    async def fetch_sector_daily(self, trade_date: str) -> list[SectorDaily]:
        """从 akshare 抓取所有行业板块当日涨跌幅。

        Returns:
            SectorDaily 列表。akshare 失败时抛 AkshareFetchError。
        """
        return fetch_sector_daily(trade_date)

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
