"""一次性脚本：从 akshare.stock_zt_pool_dtgc_em(date) 回填 limit_stocks_daily broken 行。

回填范围（emotion_daily 已存在的 10 个交易日：20260720~20260731）。
回填目标：limit_stocks_daily limit_type='broken' 行 + emotion_daily.broken_limit_ratio。

设计原则（AGENTS.md §3 / §4）：
- 仅动 limit_stocks_daily 与 emotion_daily 两张表
- 默认 dry_run=True 预览；确认后传 --apply 落库
- 应用时开启事务
"""
from __future__ import annotations

import argparse
import asyncio
import sqlite3
import sys
from pathlib import Path

DB = Path("data/yunhe.db")


def _existing_dates(conn: sqlite3.Connection) -> list[str]:
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT trade_date FROM emotion_daily ORDER BY trade_date")
    return [r[0] for r in cur.fetchall()]


def _current_broken(conn: sqlite3.Connection, trade_date: str) -> int:
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM limit_stocks_daily "
        "WHERE trade_date=? AND limit_type='broken'",
        (trade_date,),
    )
    return int(cur.fetchone()[0] or 0)


def _preview(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    """返回 (trade_date, ak_broken_count) 列表。"""
    dates = _existing_dates(conn)
    return _fetch_all(dates)


def _fetch_all(dates: list[str]) -> list[tuple[str, int]]:
    """同步调 akshare 抓每个日期的炸板数。"""
    try:
        import tqdm  # noqa: F401
        sys.modules["tqdm"].tqdm = lambda *a, **k: None
    except KeyError:
        pass
    import akshare as ak

    out: list[tuple[str, int]] = []
    for d in dates:
        try:
            df = ak.stock_zt_pool_dtgc_em(date=d)
        except Exception as e:
            print(f"  {d}: fetch error: {e}")
            out.append((d, -1))
            continue
        n = 0 if df is None else len(df)
        out.append((d, int(n)))
    return out


async def _apply(conn_path: Path, dates: list[str]) -> dict[str, int]:
    """实际写库：跑 limit_broken_fetcher.run + 触发 emotion_daily 重聚合 broken_ratio。"""
    # 重置 module 路径，让 infrastructure.* 可 import
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from infrastructure.persistence.connection import reset_connection
    from infrastructure.stock.cache_repository import CacheRepository
    from infrastructure.stock import limit_broken_fetcher
    from infrastructure.stock.sqlite_data_source import (
        SqliteStockDataSource,
    )

    reset_connection()
    sqlite_conn = sqlite3.connect(conn_path)
    try:
        repo = CacheRepository(sqlite_conn)
        written = 0
        for d in dates:
            count = await limit_broken_fetcher.run(trade_date=d, repo=repo)
            written += int(count)
    finally:
        sqlite_conn.close()

    # 重算 emotion_daily.broken_limit_ratio：基于 limit_stocks_daily 真实数据
    from infrastructure.stock.emotion_daily_fetcher import (
        compute_authenticity_level,
    )
    sqlite_conn = sqlite3.connect(conn_path)
    cur = sqlite_conn.cursor()
    cur.execute("BEGIN")
    try:
        cur.execute(
            """
            UPDATE emotion_daily
            SET broken_limit_ratio = ROUND(
                CAST(
                    (SELECT COUNT(*) FROM limit_stocks_daily l
                     WHERE l.trade_date = emotion_daily.trade_date
                       AND l.limit_type = 'broken') AS REAL
                ) / NULLIF(
                    (SELECT COUNT(*) FROM limit_stocks_daily l
                     WHERE l.trade_date = emotion_daily.trade_date
                       AND l.limit_type IN ('up','broken')), 0
                ), 6
            )
            """
        )
        # 重算 authenticity_level：基于刚更新后的 broken_limit_ratio
        cur.execute(
            "SELECT trade_date, broken_limit_ratio FROM emotion_daily"
        )
        rows = cur.fetchall()
        for trade_date, broken in rows:
            auth = compute_authenticity_level(float(broken))
            cur.execute(
                "UPDATE emotion_daily SET authenticity_level=? WHERE trade_date=?",
                (auth, trade_date),
            )
        sqlite_conn.commit()
    except Exception:
        sqlite_conn.rollback()
        raise
    finally:
        sqlite_conn.close()
    return {"written": written}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="实际写库")
    args = parser.parse_args()

    conn = sqlite3.connect(DB)
    try:
        rows = _preview(conn)
        existing_total = sum(c for _, c in rows if c >= 0)
        print(f"target emotion_daily dates: {len(rows)}")
        for d, c in rows:
            cur = _current_broken(conn, d)
            print(f"  {d}: ak_broken={c} db_current={cur}")
        print(f"expected total broken writes: {existing_total}")
        if args.apply:
            conn.close()
            result = asyncio.run(_apply(DB, [d for d, _ in rows]))
            print(f"\n[APPLIED] broken rows written={result['written']}")
        else:
            print("\n[dry-run] pass --apply to commit")
    finally:
        conn.close()


if __name__ == "__main__":
    main()