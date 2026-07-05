"""会话持久化 Repository —— 集中 sessions / tasks / session_turns 表的裸 SQL。

P1-10 抽取：把原本散落在 api/server.py 和 domain/travel/core.py 中的直连 DB
操作收敛到此处，让 API/Domain 层只通过 Repository 访问会话数据。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from infrastructure.persistence.database import get_connection

logger = logging.getLogger(__name__)


class SessionRepository:
    """sessions / tasks / session_turns 三张表的访问入口。"""

    # ------------------------------------------------------------------ #
    # 创建
    # ------------------------------------------------------------------ #
    @staticmethod
    def create(
        session_id: str,
        user_id: str,
        *,
        summary: str = "",
        created_at: str | None = None,
    ) -> None:
        """新建一个会话：同时写入 sessions 行和 tasks 行。

        tasks 行是 list_user_sessions 按 user_id 过滤的依据，必须一起插入。
        """
        now = created_at or datetime.utcnow().isoformat()
        conn = get_connection()
        conn.execute(
            "INSERT INTO sessions (session_id, summary, created_at, updated_at, user_id) VALUES (?, ?, ?, ?, ?)",
            (session_id, summary, now, now, user_id),
        )
        conn.execute(
            "INSERT INTO tasks (session_id, user_id, status, goal, created_at, updated_at) "
            "VALUES (?, ?, 'idle', '', ?, ?)",
            (session_id, user_id, now, now),
        )
        conn.commit()

    # ------------------------------------------------------------------ #
    # 查询
    # ------------------------------------------------------------------ #
    @staticmethod
    def list_by_user(user_id: str) -> list[dict]:
        """列出指定用户的所有会话，按 updated_at 倒序。

        返回字段：session_id / title / created_at / updated_at / message_count。
        title 优先用 summary，否则取首条 user 消息前 60 字，再否则 "新对话"。

        带 fallback：如果新列（user_id / 子查询）不可用，回退到全表扫描
        （兼容旧库 / 旧迁移）。
        """
        sessions: list[dict] = []
        try:
            conn = get_connection()
            rows = conn.execute(
                "SELECT s.session_id, s.summary, s.created_at, s.updated_at, "
                "(SELECT COUNT(*) FROM session_turns st WHERE st.session_id = s.session_id) AS turn_count, "
                "(SELECT st2.content FROM session_turns st2 "
                "  WHERE st2.session_id = s.session_id AND st2.role = 'user' "
                "  ORDER BY st2.created_at LIMIT 1) AS first_msg "
                "FROM sessions s "
                "WHERE s.user_id = ? "
                "ORDER BY s.updated_at DESC",
                (user_id,),
            ).fetchall()
            for row in rows:
                first_msg = row[5] if len(row) > 5 else ""
                sessions.append(
                    {
                        "session_id": row[0],
                        "title": row[1] or (first_msg[:60] if first_msg else "新对话"),
                        "created_at": row[2] or "",
                        "updated_at": row[3] or "",
                        "message_count": row[4] if row[4] is not None else 0,
                    }
                )
        except Exception:
            # 兼容旧库：user_id 列不存在等情况
            logger.warning("list_by_user fallback to full-table scan", exc_info=True)
            conn2 = get_connection()
            rows = conn2.execute(
                "SELECT session_id, summary, created_at, updated_at FROM sessions ORDER BY updated_at DESC"
            ).fetchall()
            for row in rows:
                sessions.append(
                    {
                        "session_id": row[0],
                        "title": row[1] or "新对话",
                        "created_at": row[2] or "",
                        "updated_at": row[3] or "",
                        "message_count": 0,
                    }
                )
        return sessions

    @staticmethod
    def get_messages(session_id: str) -> list[dict]:
        """按时间顺序返回某会话的所有消息（role / content / created_at）。"""
        conn = get_connection()
        return [
            dict(row)
            for row in conn.execute(
                "SELECT role, content, created_at FROM session_turns WHERE session_id = ? ORDER BY id",
                (session_id,),
            )
        ]

    # ------------------------------------------------------------------ #
    # 删除
    # ------------------------------------------------------------------ #
    @staticmethod
    def delete(session_id: str) -> None:
        """级联删除一个会话：session_turns → sessions → tasks。"""
        conn = get_connection()
        conn.execute("DELETE FROM session_turns WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM tasks WHERE session_id = ?", (session_id,))
        conn.commit()
