"""一次性脚本：从 limit_stocks_daily 真实聚合，回填 emotion_daily 核心字段。

回填范围：limit_up_count、broken_limit_ratio、max_consecutive_boards。
其他维度（adv_count/breadth/phase/style 等）置 NULL，等待 fetcher 重跑覆盖。

设计原则（AGENTS.md §3 / §4）：
- 仅动 emotion_daily 表，不动其它表。
- 在事务中执行：DELETE 10 行 → INSERT 10 行。
- 默认 dry_run=True，打印预览；确认后传 --apply 落库。
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

DB = Path("data/yunhe.db")


def _aggregate(conn: sqlite3.Connection, trade_date: str) -> dict[str, int | float | None]:
    """从 limit_stocks_daily 聚合涨停/炸板/最高板。"""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            SUM(CASE WHEN limit_type = 'up' THEN 1 ELSE 0 END) AS up_count,
            SUM(CASE WHEN limit_type = 'broken' THEN 1 ELSE 0 END) AS broken_count,
            MAX(consecutive_boards) AS max_boards
        FROM limit_stocks_daily
        WHERE trade_date = ?
        """,
        (trade_date,),
    )
    row = cur.fetchone()
    up_count = int(row[0] or 0)
    broken_count = int(row[1] or 0)
    max_boards = int(row[2] or 0)
    total = up_count + broken_count
    broken_ratio = (broken_count / total) if total > 0 else 0.0
    return {
        "limit_up_count": up_count,
        "broken_limit_ratio": round(broken_ratio, 6),
        "max_consecutive_boards": max_boards,
    }


def _preview(conn: sqlite3.Connection) -> list[tuple[str, dict[str, int | float | None]]]:
    cur = conn.cursor()
    cur.execute("SELECT trade_date FROM emotion_daily ORDER BY trade_date")
    dates = [r[0] for r in cur.fetchall()]
    return [(d, _aggregate(conn, d)) for d in dates]


def _apply(conn: sqlite3.Connection) -> int:
    cur = conn.cursor()
    rows = _preview(conn)
    try:
        cur.execute("BEGIN")
        for trade_date, agg in rows:
            cur.execute("DELETE FROM emotion_daily WHERE trade_date = ?", (trade_date,))
            cur.execute(
                """
                INSERT INTO emotion_daily (
                    trade_date,
                    limit_up_count,
                    limit_down_count,
                    valid_limit_up_count,
                    broken_limit_ratio,
                    max_consecutive_boards
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    trade_date,
                    agg["limit_up_count"],
                    0,
                    0,
                    agg["broken_limit_ratio"],
                    agg["max_consecutive_boards"],
                ),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="实际写库")
    args = parser.parse_args()

    conn = sqlite3.connect(DB)
    try:
        rows = _preview(conn)
        print(f"target emotion_daily rows: {len(rows)}")
        for trade_date, agg in rows:
            print(f"  {trade_date}: {agg}")
        if args.apply:
            n = _apply(conn)
            print(f"\n[APPLIED] rewrote {n} rows in emotion_daily")
        else:
            print("\n[dry-run] pass --apply to commit")
    finally:
        conn.close()


if __name__ == "__main__":
    main()