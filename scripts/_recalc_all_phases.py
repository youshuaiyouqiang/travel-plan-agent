"""用修复后的 compute_raw_phase 重算 7-20~8-4 的 emotion_phase。

原因：原 compute_raw_phase 在 score ∈ [60, 80) 且 momentum <= 0 时
返回"高潮"（紫色），但语义错——这是"从高潮掉下来"应该是"弱分歧"。
修复后该区间 momentum<0 → 弱分歧（浅绿）。

8-3 / 8-4 emotion_score 不变（akshare 实时截面无变化），仅 phase 修正。
"""
from __future__ import annotations

import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import sqlite3

from domain.stock.emotion_cycle import compute_raw_phase


def main() -> int:
    db_path = "c:/Users/29105/Desktop/yunhe/data/yunhe.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 取所有 emotion_daily
    cur.execute(
        'SELECT trade_date, emotion_score FROM emotion_daily '
        'WHERE trade_date BETWEEN "20260720" AND "20260804" ORDER BY trade_date'
    )
    rows = [dict(r) for r in cur.fetchall()]

    print(f"{'date':<10} {'score':>7} {'3dAgo':>7} {'momentum':>9}  new_phase")
    print("-" * 55)

    for i, r in enumerate(rows):
        score = r["emotion_score"]
        # 3 日前 = i - 3
        if i >= 3:
            score_3d_ago = rows[i - 3]["emotion_score"]
        else:
            score_3d_ago = None
        momentum = (score - score_3d_ago) if score_3d_ago is not None else 0.0
        new_phase = compute_raw_phase(score, score_3d_ago)
        m_str = f"{momentum:+.1f}" if score_3d_ago is not None else "None"
        s3_str = f"{score_3d_ago:.1f}" if score_3d_ago is not None else "None"
        print(f"{r['trade_date']:<10} {score:>7.1f} {s3_str:>7} {m_str:>9}  {new_phase}")
        cur.execute(
            "UPDATE emotion_daily SET emotion_phase = ? WHERE trade_date = ?",
            (new_phase, r["trade_date"]),
        )

    conn.commit()
    conn.close()
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
