"""一次性：v024 迁移 + backfill emotion_daily.top_board_leaders 10 行历史。

- 调 init_db 让 db 应用 v024（emotion_daily ADD COLUMN top_board_leaders）
- 对 10 个交易日的 emotion_daily 行，基于 limit_stocks_daily 真实数据
  聚合 top_board_leaders（max_consecutive_boards 对应的 stock_code 列表）
"""
import json
import sqlite3
import sys
from pathlib import Path

DB = Path("data/yunhe.db")

# 1) 应用 v024 迁移
repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from infrastructure.persistence.database import init_db, reset_connection

reset_connection()
init_db(DB)

# 2) 查 emotion_daily 所有日期
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT DISTINCT trade_date FROM emotion_daily ORDER BY trade_date")
dates = [r[0] for r in cur.fetchall()]

# 3) 对每个日期，limit_stocks_daily 聚合 max_boards → 龙头代码列表
updates = []
for d in dates:
    cur.execute(
        "SELECT MAX(consecutive_boards) FROM limit_stocks_daily "
        "WHERE trade_date=? AND limit_type='up'",
        (d,),
    )
    max_boards = int(cur.fetchone()[0] or 0)
    if max_boards <= 0:
        leaders: list[str] = []
    else:
        cur.execute(
            "SELECT stock_code FROM limit_stocks_daily "
            "WHERE trade_date=? AND limit_type='up' "
            "AND consecutive_boards=? ORDER BY stock_code",
            (d, max_boards),
        )
        leaders = [r[0] for r in cur.fetchall()]
    updates.append((json.dumps(leaders, ensure_ascii=False), d))

# 4) 更新 emotion_daily.top_board_leaders
cur.execute("BEGIN")
try:
    for payload, d in updates:
        cur.execute(
            "UPDATE emotion_daily SET top_board_leaders=? WHERE trade_date=?",
            (payload, d),
        )
    conn.commit()
except Exception:
    conn.rollback()
    raise

print(f"updated {len(updates)} rows")
for d, _ in updates:
    print(f"  {d}: {json.loads(next(p for p, dd in updates if dd == d))}")

conn.close()
print("\n[APPLIED] emotion_daily.top_board_leaders backfilled")
