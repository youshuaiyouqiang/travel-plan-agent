"""Phase 1 复盘数据源端口验证（不调 LLM）。

直接调 StockDataSource 端口的快照方法，验证 review_service._build_user_prompt
收到的数据是否真的非空——这是 Phase 1 修复的核心目标。

用法：
    .venv\\Scripts\\python.exe scripts\\verify_stock_snapshot.py [YYYYMMDD]
"""

from __future__ import annotations

import asyncio
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


async def _run() -> int:
    trade_date = sys.argv[1] if len(sys.argv) > 1 else "20260731"
    print(f"=== StockDataSource 端口快照验证 trade_date={trade_date} ===\n")

    from app import build_orchestrator
    container = build_orchestrator()
    data = container.stock_data_source  # SqliteStockDataSource

    # 1. market snapshot
    print("[1] get_market_snapshot(date)")
    snap = await data.get_market_snapshot(trade_date)
    if snap is None:
        print("    ✗ 返回 None（review_service 会判 no_data）")
    else:
        print(f"    ✓ trade_date={snap.trade_date}")
        print(f"      sh={snap.sh_index} sz={snap.sz_index} cyb={snap.cyb_index}")
        tv = snap.total_volume
        tv_str = f"{tv:.0f}" if tv is not None else "None"
        vc = snap.volume_change_pct
        vc_str = f"{vc:+.2f}%" if vc is not None else "None"
        print(f"      两市成交额={tv_str} 量能环比={vc_str}")
        print(f"      连续下跌天数={snap.consecutive_down_days} MA20={snap.ma20_status}")

    # 2. emotion trend
    print("\n[2] get_emotion_indicators_trend(end_date, days=10)")
    trend = await data.get_emotion_indicators_trend(end_date=trade_date, days=10)
    print(f"    返回 {len(trend)} 条")
    if trend:
        for t in trend[-3:]:
            print(f"      {t.trade_date}: limit_up={t.limit_up_count} "
                  f"max_boards={t.max_consecutive_boards}")

    # 3. sector rotation
    print("\n[3] get_sector_rotation(date)")
    sectors = await data.get_sector_rotation(trade_date)
    print(f"    返回 {len(sectors)} 条")
    if sectors:
        print(f"    涨幅前 3: {[(s.sector_name, round(s.pct_chg, 2) if s.pct_chg else None) for s in sectors[:3]]}")

    # 4. watchlist
    print("\n[4] get_watchlist()")
    watchlist = await data.get_watchlist()
    print(f"    返回 {len(watchlist)} 条")
    if watchlist:
        print(f"    样本: {[(s.stock_code, s.stock_name) for s in watchlist[:3]]}")
    else:
        print("    （Phase 2 Task G 才会写入观察池）")

    # 5. signal_stocks (stub)
    print("\n[5] get_signal_stocks(date)")
    signals = await data.get_signal_stocks(trade_date)
    print(f"    返回 {len(signals)} 条（Phase 2 Task 才会实现真实算法）")

    print("\n=== 总结 ===")
    print("Phase 1 修复目标：market_snapshot 非 None")
    if snap is not None:
        print("  ✅ 已达成：review_service 不会再判 no_data，会真实调 LLM 生成复盘")
    else:
        print("  ⚠️ 仍可能 no_data：检查 emotion_daily 是否有当日数据")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
