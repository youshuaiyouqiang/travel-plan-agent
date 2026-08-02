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
import time
from datetime import datetime, timedelta
from typing import Any

import akshare as ak
import pandas as pd
import requests

from domain.stock.models import (
    EmotionRawData,
    LimitStock,
    MarketIndexRow,
    SectorDaily,
    StockDaily,
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

    **Task A 修复**：``stock_zh_index_daily`` 实际返回的列不含 ``pct_chg``
    （实测列名 ``['date', 'open', 'high', 'low', 'close', 'volume']``）。
    因此 pct_chg 必须自己算：用前一行 close 作为 prev_close，公式
    ``(close - prev_close) / prev_close * 100``。首行无前日时 pct_chg=None。

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
        date_norm = df["date"].astype(str).str.replace("-", "").str.replace("/", "")
        match_mask = date_norm == target
        if not match_mask.any():
            logger.warning(
                "fetch_market_index: no row for symbol=%s date=%s",
                code, trade_date,
            )
            continue

        match_idx = int(match_mask.values.argmax())  # 第一个 True 的位置
        r = df.iloc[match_idx]
        close = _to_float(r.get("close"))

        # Task A：自己算 pct_chg（akshare stock_zh_index_daily 不返回该字段）
        # 用前一行 close 作为 prev_close；首行无前日时 pct_chg=None
        pct_chg: float | None = None
        if match_idx > 0:
            prev_close = _to_float(df.iloc[match_idx - 1].get("close"))
            if prev_close is not None and prev_close != 0 and close is not None:
                pct_chg = (close - prev_close) / prev_close * 100

        try:
            row = MarketIndexRow(
                trade_date=target,
                index_code=code,
                open=_to_float(r.get("open")),
                close=close,
                high=_to_float(r.get("high")),
                low=_to_float(r.get("low")),
                volume=_to_float(r.get("volume")),
                pct_chg=pct_chg,
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


def _extract_shanghai_total_volume(df: pd.DataFrame) -> float | None:
    """从 ``stock_zh_index_spot_em`` 返回的截面 DataFrame 取上证成交额。

    Task B：返回 None（而非 0.0）表示"未抓到成交额"。
    区分"接口返空"（None）和"成交额确实为 0"（0.0）两种语义。
    """
    if df is None or len(df) == 0 or "code" not in df.columns or "成交额" not in df.columns:
        return None
    match = df[df["code"] == "sh000001"]
    if len(match) == 0:
        return None
    v = _to_float(match.iloc[0].get("成交额"))
    return v  # 可能 None


def fetch_emotion_daily(trade_date: str) -> EmotionRawData:
    """抓取"原始"情绪指标（Task 12）：涨停/跌停/炸板 + 两市成交额。

    二次加工（valid_count / broken_ratio / max_boards / volume_change_pct /
    yesterday_premium）由 ``emotion_daily_fetcher.run`` 调
    ``domain.stock.heuristics`` + 读 ``limit_stocks_daily`` 完成，
    不在 akshare 包装层做聚合。

    **Task B 修复**：``stock_zh_index_spot_em`` 反爬不稳定（约 50% 成功率），
    原代码在该接口失败时直接 ``raise AkshareFetchError``，导致整个
    emotion_daily 该日不写入。修复后：spot_em 失败时降级为
    ``total_volume=None``，其他字段（涨停/跌停/炸板）照写——
    legu 接口稳定可用，不应被 spot_em 拖累。

    Returns:
        EmotionRawData 单一对象（一天一行）；legu 失败抛 AkshareFetchError。
        spot_em 失败时 total_volume=None，不抛异常。
    """
    target = _to_yyyymmdd(trade_date)
    if target is None:
        raise AkshareFetchError(
            f"fetch_emotion_daily invalid trade_date={trade_date!r}"
        )

    # 1) 拉涨停/跌停/炸板截面（ak.stock_market_activity_legu）— 稳定可用
    try:
        activity_df: pd.DataFrame = ak.stock_market_activity_legu()
    except _AKSHARE_EXC as e:
        raise AkshareFetchError(
            f"fetch_emotion_daily stock_market_activity_legu failed date={trade_date}"
        ) from e

    limit_up = _df_to_int(activity_df, "涨停")
    limit_down = _df_to_int(activity_df, "跌停")
    broken = _df_to_int(activity_df, "炸板")

    # 2) 拉两市成交额（ak.stock_zh_index_spot_em）— 反爬不稳定，失败降级 None
    # Task B：不再因 spot_em 失败而抛异常；legu 成功即写入
    total_volume: float | None = None
    try:
        spot_df: pd.DataFrame = ak.stock_zh_index_spot_em()
        total_volume = _extract_shanghai_total_volume(spot_df)
    except _AKSHARE_EXC as e:
        logger.warning(
            "fetch_emotion_daily stock_zh_index_spot_em failed date=%s err=%s",
            trade_date, e,
        )
        total_volume = None  # 降级：成交额缺失，其他字段照写

    if limit_up == 0 and limit_down == 0 and broken == 0 and total_volume is None:
        # 涨停/跌停/炸板/成交额全空 → 视为空数据（非交易日）
        raise AkshareFetchError(
            f"fetch_emotion_daily empty data for date={trade_date} "
            f"(limit_up=0, limit_down=0, broken=0, total_volume=None)"
        )

    return EmotionRawData(
        trade_date=target,
        limit_up_count=limit_up,
        limit_down_count=limit_down,
        broken_count=broken,
        total_volume=total_volume,
    )


def _shift_date_yyyymmdd(date_yyyymmdd: str, days: int) -> str:
    """把 ``YYYYMMDD`` 日期往前/往后推 ``days`` 天，返回 ``YYYYMMDD``。

    Task C 辅助函数：用于计算 ``stock_board_industry_index_ths`` 的
    ``start_date`` —— 往前推几天以保证覆盖前一个交易日的 close，
    用来自己算 pct_chg（同花顺接口不直接返回 pct_chg）。
    """
    dt = datetime.strptime(date_yyyymmdd, "%Y%m%d")
    return (dt + timedelta(days=days)).strftime("%Y%m%d")


def fetch_sector_daily(trade_date: str) -> list[SectorDaily]:
    """抓取所有板块的单日涨跌幅（约 90 个同花顺行业板块）。

    **Task C 修复**：从东财 ``stock_board_industry_name_em``（反爬失败，
    sector_daily 表 0 行）切换到同花顺 ``stock_board_industry_index_ths``。

    实现策略（两步走）：
    1. ``ak.stock_board_industry_name_ths()`` 拿 90 个板块列表（列 ``name`` /
       ``code``，如 ``半导体`` / ``881121``）。该接口失败时抛
       ``AkshareFetchError``（拿不到板块列表后续无法继续）。
    2. 逐板块调 ``ak.stock_board_industry_index_ths(symbol=name,
       start_date, end_date)`` 取 K 线。``start_date`` 往前推 3 天以保证
       拿到前一个交易日的 close，用来自己算 ``pct_chg``
       （同花顺接口不返回 pct_chg 字段，与 ``stock_zh_index_daily`` 同病）。

    单板块失败：log warning continue，不中断整体流程（部分板块接口失败
    不应让当日 sector_daily 完全空）。

    性能：90 板块 × (2-3s akshare + 0.3s 反爬 sleep) ≈ 200-300s。
    作为后台任务（``asyncio.create_task``）可接受；本函数为同步实现，
    fetcher 用 ``asyncio.to_thread`` 包装后调用。

    Args:
        trade_date: 交易日期（``YYYY-MM-DD`` 或 ``YYYYMMDD``）。

    Returns:
        SectorDaily 列表（约 80-90 行，部分板块可能因接口失败而跳过）。

    Raises:
        AkshareFetchError: 当 ``stock_board_industry_name_ths`` 失败时抛出
            （拿不到板块列表，后续无法继续）。
    """
    target = _to_yyyymmdd(trade_date)
    if target is None:
        raise AkshareFetchError(
            f"fetch_sector_daily invalid trade_date={trade_date!r}"
        )

    # 1. 取 90 个板块列表（同花顺）
    try:
        sectors_df: pd.DataFrame = ak.stock_board_industry_name_ths()
    except _AKSHARE_EXC as e:
        raise AkshareFetchError(
            f"fetch_sector_daily stock_board_industry_name_ths failed date={trade_date}"
        ) from e

    if sectors_df is None or len(sectors_df) == 0:
        logger.warning(
            "fetch_sector_daily: empty sectors df date=%s", trade_date,
        )
        return []

    # 2. start_date 往前推 3 天确保覆盖前一个交易日（用于算 pct_chg）
    start_date = _shift_date_yyyymmdd(target, days=-3)

    rows: list[SectorDaily] = []
    for _, sector in sectors_df.iterrows():
        name = sector.get("name")
        code = sector.get("code")
        # 缺核心字段 → 跳过
        if not name or not code:
            continue
        name_str = str(name)
        code_str = str(code)

        try:
            hist_df: pd.DataFrame = ak.stock_board_industry_index_ths(
                symbol=name_str,
                start_date=start_date,
                end_date=target,
            )
        except _AKSHARE_EXC as e:
            # 单板块失败：跳过，不中断整体
            logger.warning(
                "fetch_sector_daily: ths index failed name=%s date=%s err=%s",
                name_str, trade_date, e,
            )
            continue

        if hist_df is None or len(hist_df) == 0:
            logger.warning(
                "fetch_sector_daily: empty hist name=%s date=%s",
                name_str, trade_date,
            )
            continue

        # 找到 trade_date 那一行（同花顺日期格式为 'YYYY-MM-DD'）
        date_norm = hist_df["日期"].astype(str).str.replace("-", "")
        match_mask = date_norm == target
        if not match_mask.any():
            logger.warning(
                "fetch_sector_daily: no row for name=%s date=%s",
                name_str, trade_date,
            )
            continue

        match_idx = int(match_mask.values.argmax())  # 第一个 True 的位置
        r = hist_df.iloc[match_idx]
        close = _to_float(r.get("收盘价"))

        # 自己算 pct_chg（同花顺接口不返回该字段）
        # 用前一行 close 作为 prev_close；首行无前日时 pct_chg=None
        pct_chg: float | None = None
        if match_idx > 0:
            prev_close = _to_float(hist_df.iloc[match_idx - 1].get("收盘价"))
            if prev_close is not None and prev_close != 0 and close is not None:
                pct_chg = (close - prev_close) / prev_close * 100

        try:
            rows.append(
                SectorDaily(
                    trade_date=target,
                    sector_code=code_str,
                    sector_name=name_str,
                    pct_chg=pct_chg,
                    # 同花顺 stock_board_industry_index_ths 不返回领涨股
                    # → Task F 阶段由 stock_fund_flow_industry 二次加工
                    leading_stock_codes=[],
                    # 同花顺接口不返回板块涨停数
                    # → Task F 阶段由 limit_stocks_daily 聚合
                    limit_up_count=0,
                )
            )
        except (ValueError, TypeError) as e:
            logger.warning(
                "fetch_sector_daily: parse failed name=%s code=%s err=%s",
                name_str, code_str, e,
            )
            continue

        # 反爬防护：每次 akshare 调用后 sleep 0.3 秒
        # （90 板块 × 0.3s ≈ 27s，总耗时增加约 30s，可接受）
        time.sleep(0.3)

    return rows


def fetch_stock_daily(
    stock_code: str, trade_date: str
) -> list[StockDaily]:
    """抓取单只股的多日 K 线（ak.stock_zh_a_hist）。

    akshare 函数：``ak.stock_zh_a_hist(symbol=stock_code, period='daily',
    end_date=YYYY-MM-DD)``。返回 DataFrame 列名（中文）：
    ``日期`` / ``开盘`` / ``收盘`` / ``最高`` / ``最低`` / ``成交量`` /
    ``成交额`` / ``振幅`` / ``涨跌幅`` / ``涨跌额`` / ``换手率``。

    Args:
        stock_code: 6 位股票代码（如 "000001"）。
        trade_date: 交易日期（YYYYMMDD）；用于限定 end_date。

    Returns:
        StockDaily 列表（含指定日期及之前所有 K 线）。akshare 失败/空数据
        时返回 []。
    """
    target = _to_yyyymmdd(trade_date)
    if target is None:
        raise AkshareFetchError(
            f"fetch_stock_daily invalid trade_date={trade_date!r}"
        )
    end_date_dash = f"{target[:4]}-{target[4:6]}-{target[6:8]}"

    try:
        df: pd.DataFrame = ak.stock_zh_a_hist(
            symbol=str(stock_code), period="daily", end_date=end_date_dash,
        )
    except _AKSHARE_EXC as e:
        raise AkshareFetchError(
            f"fetch_stock_daily stock_zh_a_hist failed code={stock_code} date={trade_date}"
        ) from e

    if df is None or len(df) == 0:
        logger.warning(
            "fetch_stock_daily: empty df code=%s date=%s", stock_code, trade_date
        )
        return []

    rows: list[StockDaily] = []
    for _, r in df.iterrows():
        date_raw = r.get("日期")
        if date_raw is None:
            continue
        if hasattr(date_raw, "strftime"):
            norm_date = date_raw.strftime("%Y%m%d")
        else:
            s = str(date_raw).strip()
            norm_date = s.replace("-", "").replace("/", "")
            if len(norm_date) != 8:
                continue
        try:
            rows.append(
                StockDaily(
                    trade_date=norm_date,
                    stock_code=str(stock_code),
                    open=_to_float(r.get("开盘")),
                    close=_to_float(r.get("收盘")),
                    high=_to_float(r.get("最高")),
                    low=_to_float(r.get("最低")),
                    volume=_to_float(r.get("成交量")),
                    pct_chg=_to_float(r.get("涨跌幅")),
                    turnover=_to_float(r.get("成交额")),
                )
            )
        except (ValueError, TypeError) as e:
            logger.warning(
                "fetch_stock_daily: parse failed code=%s date=%s err=%s",
                stock_code, norm_date, e,
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

    # ── Task 15：个股 K 线 fetcher ──
    async def fetch_stock_daily(
        self, stock_code: str, trade_date: str
    ) -> list[StockDaily]:
        """从 akshare 抓取单只股的多日 K 线。

        Returns:
            StockDaily 列表。akshare 失败时抛 AkshareFetchError。
        """
        return fetch_stock_daily(stock_code, trade_date)

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

    # ── Task 18：非交易日复盘回退（akshare 不实现——SQLite 读缓存） ──
    async def get_latest_trade_date_with_data(self) -> Any:  # type: ignore[override]
        raise NotImplementedError(
            "get_latest_trade_date_with_data 只由 SqliteStockDataSource 实现读缓存"
        )

    # ── Task 19：行数对齐判定（akshare 不实现——SQLite 读缓存） ──
    async def count_limit_stocks(self, trade_date: str) -> Any:  # type: ignore[override]
        raise NotImplementedError(
            "count_limit_stocks 只由 SqliteStockDataSource 实现读缓存"
        )

    async def count_stock_daily(self, trade_date: str) -> Any:  # type: ignore[override]
        raise NotImplementedError(
            "count_stock_daily 只由 SqliteStockDataSource 实现读缓存"
        )


# Protocol 形式确认：mypy/IDE 静态检查时类满足 StockDataSource 协议
_ = StockDataSource  # noqa: F841 — 仅作 import 校验
