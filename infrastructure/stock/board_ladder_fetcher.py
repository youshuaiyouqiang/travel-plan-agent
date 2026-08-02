"""board_ladder_fetcher 模块——连板高度分层聚合（无 akshare 调用）。

设计要点（AGENTS.md §8.1 端口先于实现）：
- 从 limit_stocks_daily 按 consecutive_boards 分组聚合
- 不调 akshare（纯计算），无需 asyncio.to_thread
- 仅用于"写路径"——不读 board_ladder_daily 缓存

Task A2 修复：board_ladder_daily 表（v021 迁移已建）一直 0 行，
SKILL.md 方法论讲"连板高度"（如"3 板 1 只代表情绪高位"）时无数据可用。
本 fetcher 从 limit_stocks_daily 聚合写入，填补该数据缺口。

边界：
- 复盘 Service 不得直接 import 此模块；只能通过 StockDataSource 端口读缓存
"""

from __future__ import annotations

import logging

from domain.stock.models import BoardLadder
from domain.stock.pipeline_ports import CacheWritePort

logger = logging.getLogger(__name__)


async def run(trade_date: str, repo: CacheWritePort) -> int:
    """从 limit_stocks_daily 聚合写入 board_ladder_daily。

    按 ``consecutive_boards`` 字段分组统计：
    - 1 板：N 只 → 一条 BoardLadder(boards=1, count=N, stock_codes=[...])
    - 2 板：M 只 → 一条 BoardLadder(boards=2, count=M, stock_codes=[...])
    - 3 板：K 只 → 一条 BoardLadder(boards=3, count=K, stock_codes=[...])
    - ...

    幂等性：``upsert_board_ladder`` 内部用 ``INSERT OR REPLACE``，重复
    调用同一 ``trade_date`` 会覆盖旧数据，不会产生重复行。

    Args:
        trade_date: 交易日期（YYYYMMDD）。
        repo: 缓存仓储端口（实现 ``CacheWritePort``，需具备
            ``select_limit_stocks`` 和 ``upsert_board_ladder`` 方法）。

    Returns:
        写入条数（连板高度档位数，通常 1-10）；无涨停股时返回 0。
    """
    limit_stocks = repo.select_limit_stocks(trade_date)
    if not limit_stocks:
        logger.info(
            "board_ladder_fetcher.run: trade_date=%s no limit_stocks; skip",
            trade_date,
        )
        return 0

    # 按 consecutive_boards 分组聚合
    ladder: dict[int, list[str]] = {}
    for s in limit_stocks:
        boards = s.consecutive_boards
        ladder.setdefault(boards, []).append(s.stock_code)

    # 按 boards 升序排列写入（便于后续查询展示）
    rows: list[BoardLadder] = [
        BoardLadder(
            trade_date=trade_date,
            boards=boards,
            count=len(codes),
            stock_codes=codes,
        )
        for boards, codes in sorted(ladder.items())
    ]

    repo.upsert_board_ladder(trade_date=trade_date, rows=rows)
    logger.info(
        "board_ladder_fetcher.run: trade_date=%s levels=%d total_stocks=%d",
        trade_date, len(rows), len(limit_stocks),
    )
    return len(rows)

