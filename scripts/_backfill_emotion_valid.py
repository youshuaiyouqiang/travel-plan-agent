"""一次性：回填 emotion_daily.valid_limit_up_count（10 行历史遗漏字段）。

之前 _backfill_emotion_daily.py 只覆盖核心 3 字段（limit_up_count /
broken_limit_ratio / max_consecutive_boards），valid_limit_up_count 漏了。
现在基于 limit_stocks_daily 真实数据补算。
"""
import sqlite3
import sys
from pathlib import Path

DB = Path("data/yunhe.db")
repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from infrastructure.persistence.connection import get_connection
from infrastructure.persistence.database import reset_connection
from domain.stock.heuristics import count_valid_limit_ups
from infrastructure.stock.cache_repository import CacheRepository

reset_connection()
repo = CacheRepository(get_connection(DB))

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT trade_date FROM emotion_daily ORDER BY trade_date")
dates = [r[0] for r in cur.fetchall()]

updates = []
for d in dates:
    stocks = repo.select_limit_stocks(trade_date=d)
    v = count_valid_limit_ups(stocks)
    updates.append((v, d))

cur.execute("BEGIN")
try:
    for v, d in updates:
        cur.execute(
            "UPDATE emotion_daily SET valid_limit_up_count=? WHERE trade_date=?",
            (v, d),
        )
    conn.commit()
except Exception:
    conn.rollback()
    raise

print(f"updated {len(updates)} rows:")
for v, d in updates:
    print(f"  {d}: valid_limit_up_count={v}")

conn.close()
