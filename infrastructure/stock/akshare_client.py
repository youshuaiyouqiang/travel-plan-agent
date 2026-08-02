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
import sys
import time
import types
from datetime import datetime, timedelta
from typing import Any

# ── 必须在 import akshare 之前：禁用 akshare 内部 tqdm 进度条 ──
# akshare 在 stock_zh_a_hist_tx、stock_individual_fund_flow_rank、
# akshare.utils.func.fetch_paginated_data 等十几处用
# ``from akshare.utils.tqdm import get_tqdm``，函数体内
# ``tqdm = get_tqdm()``（默认 enable=True）按年份/分页循环，
# 把 ``\r`` 写到 stderr。在 loguru 拦截 stderr 的环境下，
# ``\r`` 不会原地刷新而是变成换行，全量抓取会刷出几百行
# "88%|...| 91/104 [00:08<00:01, 10.72it/s]" 丑陋输出。
#
# 注意：akshare 内部 ``from ... import get_tqdm`` 在 import 时
# **绑定函数对象的本地引用**——``setattr(akshare_module, "get_tqdm", ...)``
# 替换模块属性不影响已绑定的本地引用。所以必须用 ``sys.modules``
# 在 akshare 任何子模块 import 之前占位，fake 模块的 ``get_tqdm``
# 才会被所有 ``from akshare.utils.tqdm import get_tqdm`` 拿到。
#
# 本项目只有 akshare_client.py 顶层 import akshare，其他模块都从这里
# 间接获取，所以这里占位 100% 覆盖所有 akshare 子模块。
def _disabled_get_tqdm(enable: bool = True) -> Any:  # noqa: ARG001
    """akshare.utils.tqdm.get_tqdm 的禁用版，永远返回 no-op 进度条。"""
    def _noop(iterable: Any, *args: Any, **kwargs: Any) -> Any:
        return iterable
    return _noop


_fake_akshare_tqdm = types.ModuleType("akshare.utils.tqdm")
_fake_akshare_tqdm.get_tqdm = _disabled_get_tqdm  # type: ignore[attr-defined]
sys.modules["akshare.utils.tqdm"] = _fake_akshare_tqdm

import akshare as ak  # noqa: E402  # 必须在 sys.modules 占位之后
import pandas as pd
import requests

from domain.stock.emotion_dimensions import parse_amount_str, parse_pct_str
from domain.stock.heuristics import is_st_stock
from domain.stock.models import (
    EmotionRawData,
    LimitStock,
    MarketIndexRow,
    SectorDaily,
    StockDaily,
    Top20VolumeSnapshot,
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
            stock_name = str(row["名称"])
            # Bug⑨：ST/*ST/退市股涨跌幅限制不同，过滤不计入普涨停数
            if is_st_stock(stock_name):
                continue
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


def fetch_zt_pool_dtgc(trade_date: str) -> list[LimitStock]:
    """抓取炸板股池（封板后开板的个股），返回 LimitStock DTO 列表。

    akshare 函数：``ak.stock_zt_pool_dtgc_em(date=...)``，返回 DataFrame。
    失败时抛 AkshareFetchError，保留原始异常链（__cause__）。

    与 ``fetch_zt_pool`` 互补：
    - ``stock_zt_pool_em``：当日封死涨停股（含连板）
    - ``stock_zt_pool_dtgc_em``：当日封板后开板的炸板股（封板失败）

    字段映射：
    - 代码 / 名称 → stock_code / stock_name
    - 最后封板时间 → last_limit_time（炸板前的最后封板时刻）
    - 开板次数 → open_count（炸板后再封次数）
    - consecutive_boards=0（炸板未真正连板）
    - is_valid_limit_up=False（一次性封死判定为否）
    - first_limit_time=None（akshare 不返回炸板股的首次封板时间）
    """
    try:
        df: pd.DataFrame = ak.stock_zt_pool_dtgc_em(date=trade_date)
    except _AKSHARE_EXC as e:
        raise AkshareFetchError(
            f"fetch_zt_pool_dtgc failed for trade_date={trade_date}"
        ) from e

    if df is None or len(df) == 0:
        return []

    result: list[LimitStock] = []
    for _, row in df.iterrows():
        try:
            stock_name = str(row["名称"])
            # Bug⑨：ST/*ST/退市股 涨跌幅限制不同（±5% vs ±10%），不计入涨停数
            if is_st_stock(stock_name):
                continue
            last_time = str(row.get("最后封板时间", "") or "") or None
            open_count = int(row.get("开板次数", 0) or 0)
            result.append(
                LimitStock(
                    trade_date=trade_date,
                    stock_code=str(row["代码"]),
                    stock_name=stock_name,
                    limit_type="broken",
                    consecutive_boards=0,
                    first_limit_time=None,
                    last_limit_time=last_time,
                    open_count=open_count,
                    is_valid_limit_up=False,
                )
            )
        except _AKSHARE_EXC as e:
            logger.warning(
                "fetch_zt_pool_dtgc skipped malformed row date=%s err=%s",
                trade_date, e,
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
    # Task E：维度 2 广度原始数据（legu "上涨"/"下跌"项）
    adv_count = _df_to_int(activity_df, "上涨")
    decl_count = _df_to_int(activity_df, "下跌")

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
        adv_count=adv_count,
        decl_count=decl_count,
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


def _to_tx_symbol(stock_code: str) -> str:
    """把 6 位股票代码转为腾讯接口要求的 ``sh``/``sz`` 前缀格式。

    规则（按 A 股代码首位）：
    - ``6`` 开头 → 上交所 ``sh`` + code（如 600519 → sh600519）
    - ``0`` / ``3`` 开头 → 深交所 ``sz`` + code（如 000001 → sz000001）
    - ``8`` / ``4`` 开头（北交所）→ 默认归 ``bj``；腾讯接口对北交所
      支持不稳定，调用方按失败处理（akshare 抛异常 → log warning 跳过）

    Args:
        stock_code: 6 位股票代码（如 ``"000001"``）。

    Returns:
        带交易所前缀的 symbol（如 ``"sz000001"``）。

    Raises:
        AkshareFetchError: 当 stock_code 不是 6 位数字时。
    """
    code = str(stock_code).strip()
    if len(code) != 6 or not code.isdigit():
        raise AkshareFetchError(
            f"_to_tx_symbol invalid stock_code={stock_code!r}"
        )
    first = code[0]
    if first == "6":
        return f"sh{code}"
    if first in ("0", "3"):
        return f"sz{code}"
    # 北交所（8/4 开头）——腾讯接口支持不稳定，仍按 bj 前缀尝试
    return f"bj{code}"


def fetch_stock_daily(
    stock_code: str, trade_date: str
) -> list[StockDaily]:
    """抓取单只股的多日 K 线（腾讯 ``stock_zh_a_hist_tx``）。

    **Task D 修复**：从东财 ``stock_zh_a_hist``（反爬严重，99 股失败 80 只）
    切换到腾讯 ``stock_zh_a_hist_tx``（成功率显著提升）。

    akshare 函数：``ak.stock_zh_a_hist_tx(symbol=sh/sz+code,
    start_date=YYYYMMDD, end_date=YYYYMMDD)``。返回 DataFrame 列名（英文）：
    ``date`` / ``open`` / ``close`` / ``high`` / ``low`` / ``volume`` /
    ``turnover``（换手率，0-1 小数）/ ``amount``（成交额）。
    腾讯接口**不返回 pct_chg 字段**，需用前日 close 自己算（与
    ``stock_zh_index_daily`` / ``stock_board_industry_index_ths`` 同病）。

    start_date 往前推 3 天确保覆盖前一个交易日（用于算 pct_chg）。

    Args:
        stock_code: 6 位股票代码（如 ``"000001"``）。
        trade_date: 交易日期（``YYYYMMDD``）；用于限定 end_date。

    Returns:
        StockDaily 列表（含指定日期及之前约 3-4 天的 K 线）。
        akshare 失败/空数据时返回 ``[]``。
    """
    target = _to_yyyymmdd(trade_date)
    if target is None:
        raise AkshareFetchError(
            f"fetch_stock_daily invalid trade_date={trade_date!r}"
        )
    symbol = _to_tx_symbol(stock_code)
    start_date = _shift_date_yyyymmdd(target, days=-3)

    try:
        df: pd.DataFrame = ak.stock_zh_a_hist_tx(
            symbol=symbol, start_date=start_date, end_date=target,
        )
    except _AKSHARE_EXC as e:
        raise AkshareFetchError(
            f"fetch_stock_daily stock_zh_a_hist_tx failed code={stock_code} date={trade_date}"
        ) from e

    if df is None or len(df) == 0:
        logger.warning(
            "fetch_stock_daily: empty df code=%s date=%s", stock_code, trade_date
        )
        return []

    # 预先转成 norm_date 列，便于按 trade_date 过滤与定位 prev_close
    df = df.reset_index(drop=True)
    date_norm = df["date"].astype(str).str.replace("-", "").str.replace("/", "")

    rows: list[StockDaily] = []
    for i, r in df.iterrows():
        norm_date = str(date_norm.iloc[i])
        if len(norm_date) != 8:
            continue
        close = _to_float(r.get("close"))

        # 自己算 pct_chg（腾讯接口不返回该字段）
        # 用前一行 close 作为 prev_close；首行无前日时 pct_chg=None
        pct_chg: float | None = None
        if i > 0:
            prev_close = _to_float(df.iloc[i - 1].get("close"))
            if prev_close is not None and prev_close != 0 and close is not None:
                pct_chg = (close - prev_close) / prev_close * 100

        try:
            rows.append(
                StockDaily(
                    trade_date=norm_date,
                    stock_code=str(stock_code),
                    open=_to_float(r.get("open")),
                    close=close,
                    high=_to_float(r.get("high")),
                    low=_to_float(r.get("low")),
                    volume=_to_float(r.get("volume")),
                    pct_chg=pct_chg,
                    # StockDaily.turnover 是"成交额"，对应腾讯 amount 字段
                    # （腾讯 turnover 字段是"换手率"，StockDaily 无此字段）
                    turnover=_to_float(r.get("amount")),
                )
            )
        except (ValueError, TypeError) as e:
            logger.warning(
                "fetch_stock_daily: parse failed code=%s date=%s err=%s",
                stock_code, norm_date, e,
            )
            continue
    return rows


def fetch_top20_volume_stocks() -> Top20VolumeSnapshot:
    """取成交额前 20 名股票的涨幅统计（维度 3 强度原始数据）。

    Task E：调用 ``ak.stock_fund_flow_individual()``（同花顺，返回 5000+ 只
    个股资金流）。akshare 返回的 ``涨跌幅`` 和 ``成交额`` 都是字符串
    （带 ``%`` 或 ``亿``/``万`` 后缀），必须解析后才能数值运算。

    实现要点：
    - 用 ``parse_pct_str`` 解析 ``"20.01%"`` → ``20.01``
    - 用 ``parse_amount_str`` 解析 ``"3.35亿"`` → ``335000000``
    - 用 ``df.nlargest(20, "_amount")`` 取前 20（不能对字符串 ``sort_values``）
    - 返回 ``Top20VolumeSnapshot``（avg_chg / up_count / limit_up_count）

    失败时抛 ``AkshareFetchError``，由调用方（emotion_daily_fetcher）捕获后
    降级为 ``strength_level=None``。

    Returns:
        Top20VolumeSnapshot DTO。

    Raises:
        AkshareFetchError: akshare 调用失败或返回空数据时抛出。
    """
    try:
        df: pd.DataFrame = ak.stock_fund_flow_individual()
    except _AKSHARE_EXC as e:
        raise AkshareFetchError(
            "fetch_top20_volume_stocks stock_fund_flow_individual failed"
        ) from e

    if df is None or len(df) == 0:
        raise AkshareFetchError(
            "fetch_top20_volume_stocks empty df from stock_fund_flow_individual"
        )

    # 解析字符串字段为数值（parse_pct_str / parse_amount_str 来自 domain 层）
    df = df.copy()
    df["_pct"] = df["涨跌幅"].apply(parse_pct_str)
    df["_amount"] = df["成交额"].apply(parse_amount_str)

    if len(df) < 20:
        logger.warning(
            "fetch_top20_volume_stocks: only %d rows (< 20), using all",
            len(df),
        )
        top20 = df.nlargest(min(len(df), 20), "_amount")
    else:
        top20 = df.nlargest(20, "_amount")

    avg_chg = float(top20["_pct"].mean()) if len(top20) > 0 else 0.0
    up_count = int((top20["_pct"] > 0).sum())
    limit_up_count = int((top20["_pct"] >= 9.8).sum())

    return Top20VolumeSnapshot(
        avg_chg=avg_chg,
        up_count=up_count,
        limit_up_count=limit_up_count,
    )


class AkshareClient:
    """akshare 数据源客户端——StockDataSource 协议的 akshare 实现。

    Task 2 最小实现：仅完成 ``get_limit_stocks``（基于 fetch_zt_pool）。
    其余 14 个方法在 Task 3 起的 fetcher / pipeline 阶段补全，
    此处先以 NotImplementedError 站位，确保 StockDataSource 协议完整。
    """

    async def get_limit_stocks(self, trade_date: str) -> list[LimitStock]:
        """从 akshare 抓取涨停股池。"""
        return fetch_zt_pool(trade_date)

    async def get_broken_limit_stocks(self, trade_date: str) -> list[LimitStock]:
        """从 akshare 抓取炸板股池（封板后开板的个股）。

        用于 limit_broken_fetcher，与 get_limit_stocks 互补：
        涨停股池走 ``stock_zt_pool_em``，炸板股池走 ``stock_zt_pool_dtgc_em``。
        """
        return fetch_zt_pool_dtgc(trade_date)

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

    # ── Task E：成交额前 20 强度数据 ──
    async def fetch_top20_volume_stocks(self) -> Top20VolumeSnapshot:
        """从 akshare 抓取成交额前 20 名股票涨幅统计（维度 3 强度）。

        Task E：供 emotion_daily_fetcher 计算 strength_level + market_style。
        失败时抛 AkshareFetchError，由 fetcher 捕获后降级为 strength_level=None。

        Returns:
            Top20VolumeSnapshot DTO（avg_chg / up_count / limit_up_count）。
        """
        return fetch_top20_volume_stocks()

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

    async def get_emotion_cycles(
        self, end_date: str, lookback_days: int = 60
    ) -> Any:  # type: ignore[override]
        raise NotImplementedError(
            "get_emotion_cycles 只由 SqliteStockDataSource 实现读缓存"
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
