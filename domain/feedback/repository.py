"""对话质量反馈 — 👍/👎 + quality_issues 持久化。

社区版核心：反馈是产品迭代的重要数据来源。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from infrastructure.persistence.database import get_connection


@dataclass
class QualityIssue:
    """质量问题记录。"""

    id: int | None = None
    session_id: str = ""
    user_id: str = ""
    rating: str = ""  # "good" | "bad"
    issue_type: str = ""  # "inaccurate" | "tool_error" | "delegation_error" | "other"
    comment: str = ""  # 用户文字反馈
    agent_id: str = ""  # 涉及智能体
    message_snippet: str = ""  # 用户消息片段
    created_at: str = ""


class FeedbackRepository:
    """反馈数据持久化。"""

    def init_table(self) -> None:
        conn = get_connection()
        try:
            conn.execute("""
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
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_quality_issues_user ON quality_issues(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_quality_issues_rating ON quality_issues(rating)")
            conn.commit()
        finally:
            conn.close()

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
        """记录一条反馈。返回记录 ID。"""
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        conn = get_connection()
        try:
            cursor = conn.execute(
                """INSERT INTO quality_issues
                   (session_id, user_id, rating, issue_type, comment, agent_id, message_snippet, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (session_id, user_id, rating, issue_type, comment, agent_id, message_snippet[:500], now),
            )
            conn.commit()
            return cursor.lastrowid or 0
        finally:
            conn.close()

    def list_by_user(self, user_id: str, limit: int = 50) -> list[dict]:
        """查询用户的反馈记录。"""
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM quality_issues WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def count_by_rating(self, rating: str = "bad") -> int:
        """统计某种评分的数量。"""
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM quality_issues WHERE rating = ?",
                (rating,),
            ).fetchone()
            return row["cnt"] if row else 0
        finally:
            conn.close()
