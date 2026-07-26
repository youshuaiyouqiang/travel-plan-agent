"""``FeedbackRepositoryPort`` 的 SQLite 实现。

P2.5 将原 ``domain/feedback/repository.py`` 的全部 SQL 收敛到此。
SQL 文本与参数化方式完全保留；不改变表结构或迁移版本。
"""

from __future__ import annotations

import time
from typing import Any

from infrastructure.persistence.connection import get_connection


class SqliteFeedbackRepository:
    """``FeedbackRepositoryPort`` 的 SQLite 实现。

    无状态，可单例复用。通过 ``get_connection()`` 获取当前线程连接，
    支持测试隔离的 ``reset_connection()`` 模式。
    """

    def init_table(self) -> None:
        conn = get_connection()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS quality_issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                rating TEXT NOT NULL DEFAULT 'bad',
                issue_type TEXT NOT NULL DEFAULT 'other',
                comment TEXT DEFAULT '',
                agent_id TEXT DEFAULT '',
                message_snippet TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_quality_issues_user ON quality_issues(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_quality_issues_rating ON quality_issues(rating)")
        conn.commit()

    def record(
        self,
        *,
        session_id: str,
        user_id: str,
        rating: str,
        issue_type: str = "other",
        comment: str = "",
        agent_id: str = "",
        message_snippet: str = "",
    ) -> int:
        """记录一条反馈，返回记录 ID。"""
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        conn = get_connection()
        cursor = conn.execute(
            """INSERT INTO quality_issues
               (session_id, user_id, rating, issue_type, comment, agent_id, message_snippet, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, user_id, rating, issue_type, comment, agent_id, message_snippet[:500], now),
        )
        conn.commit()
        return cursor.lastrowid or 0

    def list_by_user(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """查询用户的反馈记录。"""
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM quality_issues WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def count_by_rating(self, rating: str = "bad") -> int:
        """统计某种评分的数量。"""
        conn = get_connection()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM quality_issues WHERE rating = ?",
            (rating,),
        ).fetchone()
        return row["cnt"] if row else 0


__all__ = ["SqliteFeedbackRepository"]
