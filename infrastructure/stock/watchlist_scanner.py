"""观察池扫描器——从截面数据中识别多类别候选股票。

Task 3 最小实现：仅 2 个函数。
- identify_resistant_stocks: 大盘下跌时筛选抗跌股
- extract_post_divergence_resistant: 板块高潮后分歧的板块内抗跌个股

扫描器是纯函数（无状态），不写 SQLite——筛选结果由调用方（fetcher/pipeline）
决定是否 upsert 到 watchlist_stocks 表。
"""

from __future__ import annotations

from domain.stock.models import SectorDivergence, StockDaily


def identify_resistant_stocks(
    stocks: list[StockDaily],
    market_pct_chg: float,
    threshold_ratio: float = 0.5,
) -> list[StockDaily]:
    """识别抗跌股。

    抗跌定义：个股涨跌幅 > 大盘涨跌幅 × threshold_ratio。
    当大盘下跌 2%、threshold_ratio=0.5 时，个股跌幅小于 1%（即
    pct_chg > -1%）视为抗跌。上涨股天然入选。

    大盘不跌（pct_chg >= 0）时返回空列表——抗跌是相对概念，需要大盘作锚点。

    Args:
        stocks: 个股日线列表。
        market_pct_chg: 大盘当日涨跌幅（%）。
        threshold_ratio: 抗跌阈值系数；个股跌幅需 < |大盘| × (1 - threshold_ratio)
            等价于 pct_chg > market_pct_chg × threshold_ratio。

    Returns:
        抗跌个股列表；大盘不跌或空输入时返回空列表。
    """
    if market_pct_chg >= 0:
        return []
    cutoff = market_pct_chg * threshold_ratio
    return [s for s in stocks if s.pct_chg is not None and s.pct_chg > cutoff]


def extract_post_divergence_resistant(
    divergences: list[SectorDivergence],
    sector_stocks: dict[str, list[StockDaily]],
    threshold_ratio: float = 0.5,
) -> list[str]:
    """板块高潮后分歧的板块内抗跌个股。

    对每个 ``was_high_phase=True`` 的板块，提取该板块内
    ``pct_chg > sector_pct_chg × threshold_ratio`` 的个股代码。

    Args:
        divergences: 板块分歧列表。
        sector_stocks: 板块名 → 个股日线列表 的映射。
        threshold_ratio: 抗跌阈值系数（同 identify_resistant_stocks）。

    Returns:
        入选个股 stock_code 列表（去重、保序）。
    """
    selected: list[str] = []
    seen: set[str] = set()
    for d in divergences:
        if not d.was_high_phase:
            continue
        if d.sector_pct_chg is None or d.sector_pct_chg >= 0:
            continue
        cutoff = d.sector_pct_chg * threshold_ratio
        for s in sector_stocks.get(d.sector_name, []):
            if s.pct_chg is None:
                continue
            if s.pct_chg > cutoff and s.stock_code not in seen:
                selected.append(s.stock_code)
                seen.add(s.stock_code)
    return selected
