"""一次性回填脚本：补 10 天涨跌家数 + 重算情绪周期字段。

回填范围：20260720–20260731（10 个交易日，跳过周末）。
数据来源：用户手工提供的上涨/下跌家数（akshare legu 实时接口不接受
日期参数，历史日不可得）。

流程（每个交易日）：
1. 从 limit_stocks_daily 聚合 limit_up_count / broken_count / max_boards /
   valid_count / top_board_leaders
2. 调 emotion_daily_fetcher._compute_derived_fields 传入用户提供的
   adv/decl（top20 传 None 降级），算出溢价/韧性/高度/趋势/三风格得分/
   全局得分/阶段
3. 构造 EmotionIndicators 行（含用户提供的 adv/decl + 算出的派生字段），
   通过 CacheRepository.upsert_emotion_daily 落库（INSERT OR REPLACE）

设计原则（AGENTS.md §3 / §4）：
- 仅动 emotion_daily 表，不动其它表；20260803（今日，emotion_score=38.0）
  不在回填范围内，不会被触碰
- 默认 dry_run=True，打印预览；确认后传 --apply 落库
- 复用 fetcher 的 _compute_derived_fields 共享 helper，不复制计算逻辑

用法：
    .venv\\Scripts\\python.exe scripts\\_backfill_emotion_cycle.py            # 预览
    .venv\\Scripts\\python.exe scripts\\_backfill_emotion_cycle.py --apply   # 落库
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import Any

# 把项目根加入 sys.path，让 from app/infrastructure/domain import 可用
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from domain.stock.heuristics import (  # noqa: E402
    calculate_broken_limit_ratio,
    count_valid_limit_ups,
    max_consecutive_boards,
)
from domain.stock.models import EmotionIndicators  # noqa: E402
from domain.stock.emotion_dimensions import compute_authenticity_level  # noqa: E402
from infrastructure.persistence.connection import get_connection  # noqa: E402
from infrastructure.stock.cache_repository import CacheRepository  # noqa: E402
from infrastructure.stock.sqlite_data_source import SqliteStockDataSource  # noqa: E402


# 用户提供的 10 个交易日涨跌家数（7.20-7.31，跳过周末 7.25/7.26）
# 数据来源：用户手工记录的 legu "上涨"/"下跌" 项
ADV_DECL_DATA: dict[str, tuple[int, int]] = {
    "20260720": (1992, 3438),
    "20260721": (2913, 2294),
    "20260722": (1529, 3875),
    "20260723": (4259, 1208),
    "20260724": (555, 4939),
    "20260727": (5195, 285),
    "20260728": (2603, 2768),
    "20260729": (4253, 1214),
    "20260730": (1768, 3635),
    "20260731": (4691, 728),
}


class _DepsBundle:
    """组合 repo + data_source，满足 _compute_derived_fields 的 deps 协议。

    与 EmotionDailyFetcherAdapter._FetcherDepsBundle 同构：
    - select_limit_stocks / select_stock_daily（同步，来自 CacheRepository）
    - get_emotion_indicators_before / get_emotion_indicators_trend（异步，
      来自 SqliteStockDataSource）
    """

    def __init__(self, repo: CacheRepository, data_source: SqliteStockDataSource) -> None:
        self._repo = repo
        self._ds = data_source

    def select_limit_stocks(self, trade_date: str) -> list[Any]:
        return self._repo.select_limit_stocks(trade_date)

    def select_stock_daily(self, trade_date: str) -> list[Any]:
        return self._repo.select_stock_daily(trade_date)

    async def get_emotion_indicators_before(self, trade_date: str) -> Any:
        return await self._ds.get_emotion_indicators_before(trade_date)

    async def get_emotion_indicators_trend(self, end_date: str, days: int) -> Any:
        return await self._ds.get_emotion_indicators_trend(end_date, days)


def _aggregate_limit_stocks(
    repo: CacheRepository, trade_date: str
) -> dict[str, Any]:
    """从 limit_stocks_daily 聚合涨停/炸板/最高板/有效涨停/龙头代码。"""
    limit_stocks = repo.select_limit_stocks(trade_date)
    if not limit_stocks:
        return {
            "db_limit_up_count": 0,
            "db_broken_count": 0,
            "max_boards": 0,
            "valid_count": 0,
            "top_board_leaders": [],
            "broken_ratio": 0.0,
        }
    valid_count = count_valid_limit_ups(limit_stocks)
    max_boards = max_consecutive_boards(limit_stocks)
    db_limit_up_count = sum(1 for s in limit_stocks if s.limit_type == "up")
    db_broken_count = sum(1 for s in limit_stocks if s.limit_type == "broken")
    top_board_leaders = sorted({
        s.stock_code
        for s in limit_stocks
        if s.consecutive_boards == max_boards and max_boards > 0
    })
    broken_ratio = calculate_broken_limit_ratio(
        db_limit_up_count, db_broken_count
    )
    return {
        "db_limit_up_count": db_limit_up_count,
        "db_broken_count": db_broken_count,
        "max_boards": max_boards,
        "valid_count": valid_count,
        "top_board_leaders": top_board_leaders,
        "broken_ratio": broken_ratio,
    }


async def _backfill_one(
    trade_date: str,
    adv_count: int,
    decl_count: int,
    repo: CacheRepository,
    deps: _DepsBundle,
) -> EmotionIndicators:
    """回填单个交易日：聚合 + 算派生字段 + 构造 EmotionIndicators 行。"""
    from infrastructure.stock.emotion_daily_fetcher import _compute_derived_fields

    agg = _aggregate_limit_stocks(repo, trade_date)
    authenticity_level = compute_authenticity_level(agg["broken_ratio"])

    # 调共享 helper：传用户提供的 adv/decl，top20 传 None（无历史 top20 数据）
    yesterday = await deps.get_emotion_indicators_before(trade_date)
    fields = await _compute_derived_fields(
        trade_date,
        yesterday,
        deps,
        effective_limit_up_count=agg["db_limit_up_count"],
        akshare_adv_count=adv_count,
        akshare_decl_count=decl_count,
        akshare_top20_avg_chg=None,
        akshare_top20_up_count=None,
    )

    # adv_decl_ratio（与 _compute_derived_fields 内部一致，但行里也要存）
    if decl_count > 0:
        adv_decl_ratio: float | None = adv_count / decl_count
    elif adv_count > 0:
        adv_decl_ratio = 999.0
    else:
        adv_decl_ratio = None

    return EmotionIndicators(
        trade_date=trade_date,
        limit_up_count=agg["db_limit_up_count"],
        limit_down_count=0,  # akshare 实时源；历史日期无数据
        valid_limit_up_count=agg["valid_count"],
        broken_limit_ratio=agg["broken_ratio"],
        max_consecutive_boards=agg["max_boards"],
        yesterday_limit_up_today_premium=fields["yesterday_limit_up_today_premium"],
        total_volume=None,  # akshare 实时源；历史日期无数据
        volume_change_pct=None,
        phase=None,
        phase_confidence=None,
        phase_reason=None,
        top_board_leaders=agg["top_board_leaders"],
        # 用户提供的涨跌家数（本次回填的核心输入）
        adv_count=adv_count,
        decl_count=decl_count,
        adv_decl_ratio=adv_decl_ratio,
        breadth_level=fields["breadth_level"],
        # akshare 实时源字段：历史日期不可得，全部 None
        top20_volume_avg_chg=None,
        top20_volume_up_count=None,
        top20_volume_limit_up_count=None,
        strength_level=None,
        market_style=None,
        # DB 派生字段（韧性）
        board_break_total_count=fields["board_break_total_count"],
        board_break_rebound_count=fields["board_break_rebound_count"],
        rebound_success_ratio=fields["rebound_success_ratio"],
        top5d_avg_chg=None,
        resilience_level=fields["resilience_level"],
        authenticity_level=authenticity_level,
        # DB 派生字段（高度 / 趋势）
        height_level=fields["height_level"],
        trend_5d=fields["trend_5d"],
        trend_20d=fields["trend_20d"],
        # v025 情绪周期字段（从 DB + 用户 adv/decl 计算）
        board_style_score=fields["board_style_score"],
        trend_style_score=fields["trend_style_score"],
        rebound_style_score=fields["rebound_style_score"],
        emotion_score=fields["emotion_score"],
        emotion_phase=fields["emotion_phase"],
    )


def _preview_row(repo: CacheRepository, trade_date: str) -> dict[str, Any]:
    """读取当前 DB 中该日 emotion_daily 关键字段（用于 before/after 对比）。"""
    rows = repo.select_emotion_daily(trade_date)
    if not rows:
        return {"exists": False}
    r = rows[0]
    return {
        "exists": True,
        "adv_count": r.adv_count,
        "decl_count": r.decl_count,
        "board_style_score": r.board_style_score,
        "trend_style_score": r.trend_style_score,
        "rebound_style_score": r.rebound_style_score,
        "emotion_score": r.emotion_score,
        "emotion_phase": r.emotion_phase,
    }


async def _run(apply: bool) -> int:
    conn = get_connection()
    repo = CacheRepository(conn=conn)
    data_source = SqliteStockDataSource(conn=conn)
    deps = _DepsBundle(repo=repo, data_source=data_source)

    print("=== 情绪周期回填（10 个交易日 7.20-7.31）===\n")
    print(f"{'trade_date':<10} {'adv':>5} {'decl':>5}  "
          f"{'board':>6} {'trend':>6} {'rebound':>7} {'score':>6}  phase")
    print("-" * 75)

    computed_rows: list[EmotionIndicators] = []
    for trade_date, (adv, decl) in ADV_DECL_DATA.items():
        row = await _backfill_one(trade_date, adv, decl, repo, deps)
        computed_rows.append(row)
        bs = f"{row.board_style_score:.1f}" if row.board_style_score is not None else "None"
        ts = f"{row.trend_style_score:.1f}" if row.trend_style_score is not None else "None"
        rs = f"{row.rebound_style_score:.1f}" if row.rebound_style_score is not None else "None"
        es = f"{row.emotion_score:.1f}" if row.emotion_score is not None else "None"
        print(f"{trade_date:<10} {adv:>5} {decl:>5}  "
              f"{bs:>6} {ts:>6} {rs:>7} {es:>6}  {row.emotion_phase}")

    # 落库前检查今日 8.3 行不受影响
    today_row = _preview_row(repo, "20260803")
    print(f"\n[guard] 20260803（今日，不在回填范围）emotion_score="
          f"{today_row.get('emotion_score')}（应保持 38.0 不变）")

    if not apply:
        print("\n[dry-run] 未落库；传 --apply 实际写入")
        return 0

    # 落库
    print("\n[APPLY] 开始写入 emotion_daily ...")
    for row in computed_rows:
        repo.upsert_emotion_daily(trade_date=row.trade_date, rows=[row])
        print(f"  写入 {row.trade_date}: score={row.emotion_score} "
              f"phase={row.emotion_phase}")

    # 落库后校验
    print("\n[verify] 落库后读回校验：")
    print(f"{'trade_date':<10} {'adv':>5} {'decl':>5}  "
          f"{'score':>6}  phase")
    print("-" * 50)
    for trade_date in ADV_DECL_DATA:
        after = _preview_row(repo, trade_date)
        es = after.get("emotion_score")
        es_str = f"{es:.1f}" if es is not None else "None"
        print(f"{trade_date:<10} {after.get('adv_count'):>5} "
              f"{after.get('decl_count'):>5}  {es_str:>6}  "
              f"{after.get('emotion_phase')}")

    today_after = _preview_row(repo, "20260803")
    print(f"\n[guard] 20260803 emotion_score={today_after.get('emotion_score')}"
          f"（必须仍为 38.0）")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="回填 10 天涨跌家数 + 重算情绪周期字段"
    )
    parser.add_argument(
        "--apply", action="store_true", help="实际写库（默认 dry-run 预览）"
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(_run(args.apply)))


if __name__ == "__main__":
    main()
