"""一次性：删除 limit_stocks_daily 中 ST/*ST/退市股行 + 重算 emotion_daily 核心字段。

删除 ST 后，emotion_daily 的 limit_up_count / valid_limit_up_count /
max_consecutive_boards / top_board_leaders / broken_limit_ratio / authenticity_level
都会变化（普涨停数 ≠ 涨停数），需要一并重算。
"""
import json
import sqlite3
import sys
from pathlib import Path

DB = Path("data/yunhe.db")
repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from infrastructure.persistence.connection import get_connection
from infrastructure.persistence.database import reset_connection
from domain.stock.heuristics import (
    count_valid_limit_ups,
    max_consecutive_boards,
)
from infrastructure.stock.cache_repository import CacheRepository
from infrastructure.stock.emotion_daily_fetcher import (
    compute_authenticity_level,
)

reset_connection()
repo = CacheRepository(get_connection(DB))

conn = sqlite3.connect(DB)
cur = conn.cursor()

# 1) 看 ST 股行
cur.execute(
    "SELECT trade_date, stock_code, stock_name FROM limit_stocks_daily "
    "WHERE stock_name LIKE '%ST%' OR stock_name LIKE '%退%' "
    "ORDER BY trade_date, stock_code"
)
st_rows = cur.fetchall()
print(f"== ST/退市股行 ({len(st_rows)}) ==")
for r in st_rows:
    print(" ", r)

# 2) 删除 ST 行
cur.execute(
    "DELETE FROM limit_stocks_daily "
    "WHERE stock_name LIKE '%ST%' OR stock_name LIKE '%退%'"
)
deleted = cur.rowcount
print(f"\n[DELETE] limit_stocks_daily: removed {deleted} ST/退市股行")

# 3) 重算 emotion_daily 全部 10 行核心字段（基于剔除 ST 后的 limit_stocks_daily）
cur.execute("SELECT DISTINCT trade_date FROM emotion_daily ORDER BY trade_date")
dates = [r[0] for r in cur.fetchall()]

updates = []
for d in dates:
    stocks = repo.select_limit_stocks(trade_date=d)
    ups = [s for s in stocks if s.limit_type == "up"]
    brks = [s for s in stocks if s.limit_type == "broken"]
    valid_count = count_valid_limit_ups(ups)
    max_boards = max_consecutive_boards(ups)
    top_board_leaders = sorted({
        s.stock_code for s in ups
        if s.consecutive_boards == max_boards and max_boards > 0
    })
    broken_ratio = (
        round(len(brks) / (len(ups) + len(brks)), 6)
        if (len(ups) + len(brks)) > 0 else 0.0
    )
    auth = compute_authenticity_level(broken_ratio)
    updates.append((
        len(ups),                  # limit_up_count
        valid_count,               # valid_limit_up_count
        broken_ratio,              # broken_limit_ratio
        max_boards,                # max_consecutive_boards
        json.dumps(top_board_leaders, ensure_ascii=False),
        auth,                      # authenticity_level
        d,
    ))

for tup in updates:
    cur.execute(
        "UPDATE emotion_daily SET "
        "limit_up_count=?, valid_limit_up_count=?, "
        "broken_limit_ratio=?, max_consecutive_boards=?, "
        "top_board_leaders=?, authenticity_level=? "
        "WHERE trade_date=?",
        tup,
    )
conn.commit()

print("\n[UPDATE] emotion_daily 重算:")
for tup in updates:
    print(f"  {tup[6]}: up={tup[0]} valid={tup[1]} brk_ratio={tup[2]} max={tup[3]} leaders={tup[4]} auth={tup[5]}")

conn.close()
