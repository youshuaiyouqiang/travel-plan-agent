"""Phase 1 已落库数据查看脚本（不触发抓取）。

用法：
    .venv\\Scripts\\python.exe scripts\\inspect_stock_data.py [YYYYMMDD]

直接读 SQLite 展示当日数据样本，用于验证 Phase 1 抓取结果。
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta


def _resolve_trade_date(arg: str | None) -> str:
    if arg:
        s = arg.strip().replace("-", "")
        if len(s) != 8 or not s.isdigit():
            raise ValueError(f"invalid date: {arg!r}")
        return s
    today = datetime.now()
    while today.weekday() >= 5:
        today -= timedelta(days=1)
    return today.strftime("%Y%m%d")


def _main() -> int:
    trade_date = _resolve_trade_date(sys.argv[1] if len(sys.argv) > 1 else None)
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "data", "yunhe.db")
    print(f"=== Phase 1 已落库数据查看 trade_date={trade_date} ===")
    print(f"DB: {db_path}\n")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # 各表行数
    tables = [
        ("limit_stocks_daily", "涨停股池"),
        ("market_index_daily", "大盘指数"),
        ("emotion_daily", "情绪指标"),
        ("sector_daily", "板块日线"),
        ("stock_daily", "个股 K 线"),
        ("board_ladder_daily", "连板高度分层"),
    ]
    print(f"  {'表名':<25} {'全表':>6} {'当日':>6}  说明")
    print(f"  {'-'*25} {'-'*6} {'-'*6}  {'-'*20}")
    for table, desc in tables:
        total = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        today_count = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE trade_date = ?",
            (trade_date,),
        ).fetchone()[0]
        marker = "✓" if today_count > 0 else "✗"
        print(f"  {table:<25} {total:>6}  {marker}{today_count:<5} {desc}")

    print("\n=== 抽样数据 ===")

    print("\n[board_ladder_daily 当日] (Task A2 新增)")
    rows = conn.execute(
        "SELECT boards, count, stock_codes FROM board_ladder_daily "
        "WHERE trade_date = ? ORDER BY boards ASC",
        (trade_date,),
    ).fetchall()
    if rows:
        for r in rows:
            codes_list = json.loads(r["stock_codes"] or "[]")
            preview = ", ".join(codes_list[:5]) + ("..." if len(codes_list) > 5 else "")
            print(f"  {r['boards']}板: {r['count']}只 → {preview}")
    else:
        print("  （无数据）")

    print("\n[emotion_daily 当日] (Task B 修复)")
    row = conn.execute(
        "SELECT limit_up_count, limit_down_count, broken_limit_ratio, "
        "total_volume, volume_change_pct, max_consecutive_boards "
        "FROM emotion_daily WHERE trade_date = ?",
        (trade_date,),
    ).fetchone()
    if row:
        tv = row["total_volume"]
        tv_str = f"{tv/1e8:.2f}亿" if tv else "None（接口失败降级）"
        br = row["broken_limit_ratio"]
        br_str = f"{br:.3f}" if br is not None else "None"
        vc = row["volume_change_pct"]
        vc_str = f"{vc:+.2f}%" if vc is not None else "None"
        print(f"  涨停={row['limit_up_count']} 跌停={row['limit_down_count']} "
              f"炸板率={br_str} 最高连板={row['max_consecutive_boards']}")
        print(f"  两市成交额={tv_str} 量能环比={vc_str}")
    else:
        print("  （无数据）")

    print("\n[market_index_daily 当日 pct_chg] (Task A 修复)")
    rows = conn.execute(
        "SELECT index_code, close, pct_chg FROM market_index_daily "
        "WHERE trade_date = ? ORDER BY index_code",
        (trade_date,),
    ).fetchall()
    if rows:
        for r in rows:
            pc = r["pct_chg"]
            pc_str = f"{pc:+.3f}%" if pc is not None else "None"
            print(f"  {r['index_code']}: close={r['close']:.2f} pct_chg={pc_str}")
    else:
        print("  （无数据）")

    print("\n[sector_daily 当日 Top5 涨幅 / Bottom5 跌幅] (Task C 修复)")
    rows = conn.execute(
        "SELECT sector_name, pct_chg FROM sector_daily "
        "WHERE trade_date = ? ORDER BY pct_chg DESC LIMIT 5",
        (trade_date,),
    ).fetchall()
    if rows:
        print("  涨幅前 5:")
        for r in rows:
            pc = r["pct_chg"]
            pc_str = f"{pc:+.3f}%" if pc is not None else "None"
            print(f"    {r['sector_name']}: {pc_str}")
    rows = conn.execute(
        "SELECT sector_name, pct_chg FROM sector_daily "
        "WHERE trade_date = ? ORDER BY pct_chg ASC LIMIT 5",
        (trade_date,),
    ).fetchall()
    if rows:
        print("  跌幅前 5:")
        for r in rows:
            pc = r["pct_chg"]
            pc_str = f"{pc:+.3f}%" if pc is not None else "None"
            print(f"    {r['sector_name']}: {pc_str}")

    print("\n[stock_daily 当日样本 5 只] (Task D 修复)")
    rows = conn.execute(
        "SELECT stock_code, close, pct_chg, turnover FROM stock_daily "
        "WHERE trade_date = ? LIMIT 5",
        (trade_date,),
    ).fetchall()
    if rows:
        for r in rows:
            pc = r["pct_chg"]
            pc_str = f"{pc:+.3f}%" if pc is not None else "None"
            to = r["turnover"]
            to_str = f"{to/1e8:.2f}亿" if to else "None"
            print(f"  {r['stock_code']}: close={r['close']:.2f} "
                  f"pct_chg={pc_str} turnover={to_str}")
    else:
        print("  （无数据）")

    conn.close()
    print("\n=== 查看完成 ===")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
