"""重算 8-3 / 8-4 的 emotion_phase（用回填后最新的 day_3d_ago 数据）。

背景：
  8-3 / 8-4 是今日 fetcher 跑的，当时 7-30 / 7-31 的 emotion_score
  还没回填（v025 之前字段为 None）→ momentum=0 → 弱修复（错！）。
  7-30 / 7-31 已回填 emotion_score（commit 18a8cd6 之后），现在重算
  8-3 / 8-4 的 phase：

  8-3: score=38.0, day_3d_ago=7-31=64.0 → momentum=-26.0 < -5 → 强分歧
  8-4: score=40.0, day_3d_ago=7-30=31.8 → momentum=+8.2 > 5 → 强修复

用法：
  .venv\\Scripts\\python.exe scripts/_recalc_today_phase.py
"""
from __future__ import annotations

import os
import sys

# 把项目根加入 sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import sqlite3

from domain.stock.emotion_cycle import compute_raw_phase


def main() -> int:
    db_path = "c:/Users/29105/Desktop/yunhe/data/yunhe.db"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # 8-3: day_3d_ago = 7-31
    cur.execute('SELECT emotion_score FROM emotion_daily WHERE trade_date = "20260731"')
    row = cur.fetchone()
    if row is None:
        print("[ERR] 7-31 emotion_daily 不存在，请先回填")
        conn.close()
        return 1
    s_3d_8_3 = row[0]
    cur.execute('SELECT emotion_score FROM emotion_daily WHERE trade_date = "20260803"')
    row = cur.fetchone()
    if row is None:
        print("[ERR] 8-3 emotion_daily 不存在")
        conn.close()
        return 1
    s_8_3 = row[0]
    new_phase_8_3 = compute_raw_phase(s_8_3, s_3d_8_3)
    print(f"8-3: score={s_8_3}, day_3d_ago={s_3d_8_3}, new phase={new_phase_8_3}")
    cur.execute(
        'UPDATE emotion_daily SET emotion_phase = ? WHERE trade_date = "20260803"',
        (new_phase_8_3,),
    )

    # 8-4: day_3d_ago = 7-30 (8-1, 8-2 周末)
    cur.execute('SELECT emotion_score FROM emotion_daily WHERE trade_date = "20260730"')
    row = cur.fetchone()
    if row is None:
        print("[ERR] 7-30 emotion_daily 不存在")
        conn.close()
        return 1
    s_3d_8_4 = row[0]
    cur.execute('SELECT emotion_score FROM emotion_daily WHERE trade_date = "20260804"')
    row = cur.fetchone()
    if row is None:
        print("[ERR] 8-4 emotion_daily 不存在")
        conn.close()
        return 1
    s_8_4 = row[0]
    new_phase_8_4 = compute_raw_phase(s_8_4, s_3d_8_4)
    print(f"8-4: score={s_8_4}, day_3d_ago={s_3d_8_4}, new phase={new_phase_8_4}")
    cur.execute(
        'UPDATE emotion_daily SET emotion_phase = ? WHERE trade_date = "20260804"',
        (new_phase_8_4,),
    )

    conn.commit()
    conn.close()
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
