"""Phase 1 真实抓取验证脚本。

用法：
    .venv\\Scripts\\python.exe scripts\\verify_stock_fetch.py [YYYYMMDD]

不传日期则用最近一个交易日（周一到周五，跳过周末）。
脚本会：
1. 调 build_orchestrator() 装配组合根（含 6 个 fetcher）
2. 调 pipeline.run_close(trade_date) 触发全量抓取
3. 直接查 SQLite 验证 6 张表的行数和样本数据
4. 打印汇总报告

不写入任何配置或长期状态；只读 DB 路径来自 config.settings。
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta

# 把项目根加入 sys.path，让 from app import build_orchestrator 可用
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def _resolve_trade_date(arg: str | None) -> str:
    """解析命令行日期参数；不传则取最近一个工作日。"""
    if arg:
        # 接受 YYYYMMDD 或 YYYY-MM-DD
        s = arg.strip().replace("-", "")
        if len(s) != 8 or not s.isdigit():
            raise ValueError(f"invalid date: {arg!r} (expect YYYYMMDD)")
        return s
    today = datetime.now()
    # 周末回退到周五
    while today.weekday() >= 5:  # 5=Sat, 6=Sun
        today -= timedelta(days=1)
    return today.strftime("%Y%m%d")


async def _run() -> int:
    trade_date = _resolve_trade_date(sys.argv[1] if len(sys.argv) > 1 else None)
    print(f"=== Phase 1 验证 trade_date={trade_date} ===\n")

    # 1. 装配组合根（init_db + fetcher 装配 + set_default_pipeline）
    print("[1/3] 装配组合根...")
    from app import build_orchestrator
    container = build_orchestrator()
    pipeline = container.stock_pipeline
    if pipeline is None:
        print("FAIL: stock_pipeline 未装配")
        return 1
    fetcher_names = [f.name for f in pipeline._fetchers]
    print(f"  已装配 {len(fetcher_names)} 个 fetcher: {fetcher_names}\n")

    # 2. 触发收盘管线（run_close 串行调所有 fetcher）
    print("[2/3] 触发 pipeline.run_close()...")
    result = await pipeline.run_close(trade_date=trade_date)
    print(f"  phase={result.phase} written={result.written} "
          f"errors={len(result.errors)} duration={result.duration_ms}ms")
    if result.errors:
        print("  错误列表:")
        for e in result.errors:
            print(f"    - {e}")
    print()

    # 3. 查 SQLite 验证各表实际行数
    print("[3/3] 验证各表数据落库...")
    from infrastructure.persistence.connection import get_connection
    conn = get_connection()
    tables = [
        ("limit_stocks_daily", "涨停股池"),
        ("market_index_daily", "大盘指数"),
        ("emotion_daily", "情绪指标"),
        ("sector_daily", "板块日线"),
        ("stock_daily", "个股 K 线"),
        ("board_ladder_daily", "连板高度分层"),
    ]
    print(f"  {'表名':<25} {'行数':>8}  {'当日':>6}  说明")
    print(f"  {'-'*25} {'-'*8}  {'-'*6}  {'-'*20}")
    for table, desc in tables:
        # 全表行数
        total = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        # 当日行数
        today_count = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE trade_date = ?",
            (trade_date,),
        ).fetchone()[0]
        marker = "✓" if today_count > 0 else "✗"
        print(f"  {table:<25} {total:>8}  {marker}{today_count:<5} {desc}")

    # 4. 抽样数据展示
    print("\n=== 抽样数据 ===")
    print("\n[board_ladder_daily 当日] (Task A2 新增)")
    rows = conn.execute(
        "SELECT boards, count, stock_codes FROM board_ladder_daily "
        "WHERE trade_date = ? ORDER BY boards ASC",
        (trade_date,),
    ).fetchall()
    if rows:
        for r in rows:
            codes_preview = ", ".join(r["stock_codes"][:5] if r["stock_codes"] else [])
            # stock_codes 是 JSON 字符串，截断展示
            import json
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

    print("\n[sector_daily 当日 Top5 涨幅] (Task C 修复)")
    rows = conn.execute(
        "SELECT sector_name, pct_chg FROM sector_daily "
        "WHERE trade_date = ? ORDER BY pct_chg DESC LIMIT 5",
        (trade_date,),
    ).fetchall()
    if rows:
        for r in rows:
            pc = r["pct_chg"]
            pc_str = f"{pc:+.3f}%" if pc is not None else "None"
            print(f"  {r['sector_name']}: {pc_str}")
    else:
        print("  （无数据）")

    print("\n[stock_daily 当日样本] (Task D 修复)")
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

    print("\n=== 验证完成 ===")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
