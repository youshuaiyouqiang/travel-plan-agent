"""``SessionRepositoryPort`` 的 SQLite 实现。

P2.1 将原本散落在以下位置的裸 SQL 收敛到此：
- ``domain/user/session/manager.py`` — ``SessionManager.save`` / ``_load``
- ``domain/user/session/task_state.py`` — ``TaskStateStore.save`` / ``_load``
- ``application/session/service.py`` — ``SessionService.create`` / ``update_mode`` / ``_get``
- ``infrastructure/persistence/session_repository.py`` — 旧静态方法 ``create`` / ``list_by_user`` / ``get_messages`` / ``delete``

SQL 文本、参数化方式与增量 turn 插入逻辑完全保留；不改变表结构或迁移版本。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from domain.user.session.manager import Session, Turn
from domain.user.session.task_state import TaskRecord, TaskStatus
from infrastructure.persistence.connection import get_connection
from infrastructure.persistence.serialization import _json_dumps, _json_loads

logger = logging.getLogger(__name__)


def _json_loads_list(text: str | None) -> list:
    """兼容旧数据的 JSON 列表解析；失败返回空列表。"""
    if not text:
        return []
    try:
        return _json_loads(text, [])
    except (ValueError, TypeError):
        return []


class SqliteSessionRepository:
    """``SessionRepositoryPort`` 的 SQLite 实现。

    所有方法通过 ``get_connection()`` 获取当前连接，支持测试隔离的
    ``reset_connection()`` 模式。无状态，可单例复用。
    """

    # ── Session 聚合 ────────────────────────────────────────

    def save_session(self, session: Session) -> None:
        """Upsert 会话行并增量插入未持久化的 turns。

        增量逻辑：读取 ``session._last_persisted_turn`` 标记，仅插入
        其后的新 turns；若内存中 turns 被截断（少于已持久化数），
        回退到全量重写。
        """
        conn = get_connection()
        now = datetime.utcnow().isoformat()
        session.updated_at = now

        conn.execute(
            "INSERT INTO sessions (session_id, user_id, summary, created_at, updated_at, "
            "disclosed_tools, delegation_agent_id, delegation_started_at, "
            "delegation_last_interaction, mode, locked_agent_id, news_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET "
            "user_id=excluded.user_id, "
            "summary=excluded.summary, updated_at=excluded.updated_at, "
            "disclosed_tools=excluded.disclosed_tools, "
            "delegation_agent_id=excluded.delegation_agent_id, "
            "delegation_started_at=excluded.delegation_started_at, "
            "delegation_last_interaction=excluded.delegation_last_interaction, "
            "mode=excluded.mode, "
            "locked_agent_id=excluded.locked_agent_id, "
            "news_id=excluded.news_id",
            (
                session.session_id,
                session.user_id,
                session.summary,
                session.created_at,
                session.updated_at,
                _json_dumps(session.disclosed_tools),
                session.delegation_agent_id,
                session.delegation_started_at,
                session.delegation_last_interaction,
                session.mode,
                session.locked_agent_id,
                session.news_id,
            ),
        )

        last_persisted = getattr(session, "_last_persisted_turn", 0)
        if last_persisted > len(session.turns):
            # 内存 turns 被截断：全量重写
            conn.execute("DELETE FROM session_turns WHERE session_id = ?", (session.session_id,))
            for turn in session.turns:
                conn.execute(
                    "INSERT INTO session_turns (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                    (session.session_id, turn.role, turn.content, turn.created_at),
                )
        else:
            for turn in session.turns[last_persisted:]:
                conn.execute(
                    "INSERT INTO session_turns (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                    (session.session_id, turn.role, turn.content, turn.created_at),
                )
        session._last_persisted_turn = len(session.turns)

        conn.commit()

    def load_session(self, session_id: str) -> Session | None:
        """加载会话及其全部 turns。"""
        conn = get_connection()
        row = conn.execute(
            "SELECT session_id, user_id, summary, created_at, updated_at, "
            "disclosed_tools, delegation_agent_id, delegation_started_at, "
            "delegation_last_interaction, mode, locked_agent_id, news_id "
            "FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            return None

        turn_rows = conn.execute(
            "SELECT role, content, created_at FROM session_turns WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
        turns = [Turn(role=tr["role"], content=tr["content"], created_at=tr["created_at"]) for tr in turn_rows]

        # 兼容旧数据库缺列场景：逐字段 try/except
        user_id = _safe_col(row, "user_id", "")
        disclosed_tools = _json_loads_list(_safe_col(row, "disclosed_tools", None))
        delegation_agent_id = _safe_col(row, "delegation_agent_id", None)
        delegation_started_at = _safe_col(row, "delegation_started_at", None)
        delegation_last_interaction = _safe_col(row, "delegation_last_interaction", None)
        mode = _safe_col(row, "mode", "yunhe_default") or "yunhe_default"
        locked_agent_id = _safe_col(row, "locked_agent_id", None)
        news_id = _safe_col(row, "news_id", None)

        session = Session(
            session_id=row["session_id"],
            turns=turns,
            summary=row["summary"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            disclosed_tools=disclosed_tools,
            delegation_agent_id=delegation_agent_id,
            delegation_started_at=delegation_started_at,
            delegation_last_interaction=delegation_last_interaction,
            user_id=user_id,
            mode=mode,
            locked_agent_id=locked_agent_id,
            news_id=news_id,
        )
        session._last_persisted_turn = len(turns)
        return session

    # ── 会话模式记录（供 SessionService）────────────────────

    def create_session_row(
        self,
        *,
        session_id: str,
        user_id: str,
        mode: str,
        locked_agent_id: str | None,
        news_id: str | None,
    ) -> None:
        """新建会话行并同步插入 tasks 行。"""
        now = datetime.utcnow().isoformat()
        conn = get_connection()
        conn.execute(
            "INSERT INTO sessions (session_id, user_id, summary, created_at, updated_at, "
            "mode, locked_agent_id, news_id) VALUES (?, ?, '', ?, ?, ?, ?, ?)",
            (session_id, user_id, now, now, mode, locked_agent_id, news_id),
        )
        conn.execute(
            "INSERT INTO tasks (session_id, user_id, status, goal, created_at, updated_at) "
            "VALUES (?, ?, 'idle', '', ?, ?)",
            (session_id, user_id, now, now),
        )
        conn.commit()

    def get_session_record(self, session_id: str) -> dict[str, Any] | None:
        """读取会话模式/锁定字段。"""
        conn = get_connection()
        row = conn.execute(
            "SELECT session_id, user_id, mode, locked_agent_id, news_id "
            "FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "session_id": row["session_id"],
            "user_id": row["user_id"],
            "mode": row["mode"],
            "locked_agent_id": row["locked_agent_id"],
            "news_id": row["news_id"],
        }

    def update_session_mode(
        self,
        *,
        session_id: str,
        mode: str,
        locked_agent_id: str | None,
        news_id: str | None,
    ) -> None:
        """更新会话模式与锁定字段。"""
        now = datetime.utcnow().isoformat()
        conn = get_connection()
        conn.execute(
            "UPDATE sessions SET mode = ?, locked_agent_id = ?, news_id = NULL, updated_at = ? "
            "WHERE session_id = ?",
            (mode, locked_agent_id, now, session_id),
        )
        conn.commit()

    # ── 方案确认（P3.3b）──────────────────────────────────────

    def get_confirmed_plan(self, session_id: str) -> dict[str, Any] | None:
        """读取会话的 ``confirmed_plan`` / ``confirmed_at`` 字段。"""
        conn = get_connection()
        row = conn.execute(
            "SELECT confirmed_plan, confirmed_at FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "confirmed_plan": row["confirmed_plan"] if "confirmed_plan" in row.keys() else None,
            "confirmed_at": row["confirmed_at"] if "confirmed_at" in row.keys() else None,
        }

    def set_confirmed_plan(self, *, session_id: str, plan_type: str, now: str) -> None:
        """更新会话的 ``confirmed_plan`` 与 ``confirmed_at``。"""
        conn = get_connection()
        conn.execute(
            "UPDATE sessions SET confirmed_plan = ?, confirmed_at = ? WHERE session_id = ?",
            (plan_type, now, session_id),
        )
        conn.commit()

    def clear_confirmed_plan(self, session_id: str) -> None:
        """清空会话的 ``confirmed_plan`` 与 ``confirmed_at``（置 NULL）。"""
        conn = get_connection()
        conn.execute(
            "UPDATE sessions SET confirmed_plan = NULL, confirmed_at = NULL WHERE session_id = ?",
            (session_id,),
        )
        conn.commit()

    # ── 列表与消息 ──────────────────────────────────────────

    def list_sessions_by_user(self, user_id: str) -> list[dict[str, Any]]:
        """列出用户的所有会话，按 updated_at 倒序。

        带 fallback：旧库缺列时回退到全表扫描。
        """
        sessions: list[dict[str, Any]] = []
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
            logger.warning("list_sessions_by_user fallback to full-table scan", exc_info=True)
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

    def get_session_messages(self, session_id: str) -> list[dict[str, Any]]:
        """按时间顺序返回会话的所有消息。"""
        conn = get_connection()
        return [
            dict(row)
            for row in conn.execute(
                "SELECT role, content, created_at FROM session_turns WHERE session_id = ? ORDER BY id",
                (session_id,),
            )
        ]

    def find_session_ids_by_user(self, user_id: str) -> list[str]:
        """列出用户在 ``tasks`` 表中的去重 ``session_id``（排除空字符串）。"""
        conn = get_connection()
        rows = conn.execute(
            "SELECT DISTINCT session_id FROM tasks WHERE user_id = ? AND session_id != ''",
            (user_id,),
        ).fetchall()
        return [row["session_id"] for row in rows if row["session_id"]]

    # ── 删除 ────────────────────────────────────────────────

    def delete_session(self, session_id: str) -> None:
        """级联删除：session_turns → sessions → tasks。"""
        conn = get_connection()
        conn.execute("DELETE FROM session_turns WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM tasks WHERE session_id = ?", (session_id,))
        conn.commit()

    # ── Task 状态 ───────────────────────────────────────────

    def save_task(self, task: TaskRecord) -> None:
        """Upsert 任务状态行。"""
        conn = get_connection()
        task.updated_at = datetime.utcnow().isoformat()
        conn.execute(
            "INSERT INTO tasks (session_id, user_id, status, goal, latest_user_message, latest_reply, "
            "pending_prompt, trace_summary, metadata, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET user_id=excluded.user_id, status=excluded.status, "
            "goal=excluded.goal, latest_user_message=excluded.latest_user_message, "
            "latest_reply=excluded.latest_reply, pending_prompt=excluded.pending_prompt, "
            "trace_summary=excluded.trace_summary, metadata=excluded.metadata, updated_at=excluded.updated_at",
            (
                task.session_id,
                task.user_id,
                task.status.value,
                task.goal,
                task.latest_user_message,
                task.latest_reply,
                task.pending_prompt,
                task.trace_summary,
                _json_dumps(task.metadata),
                task.created_at,
                task.updated_at,
            ),
        )
        conn.commit()

    def load_task(self, session_id: str) -> TaskRecord | None:
        """加载任务状态；不存在返回 None。"""
        conn = get_connection()
        row = conn.execute(
            "SELECT session_id, user_id, status, goal, latest_user_message, latest_reply, "
            "pending_prompt, trace_summary, metadata, created_at, updated_at FROM tasks WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            return None
        try:
            status = TaskStatus(row["status"])
        except ValueError:
            status = TaskStatus.IDLE
        return TaskRecord(
            session_id=row["session_id"],
            user_id=row["user_id"],
            status=status,
            goal=row["goal"],
            latest_user_message=row["latest_user_message"],
            latest_reply=row["latest_reply"],
            pending_prompt=row["pending_prompt"],
            trace_summary=row["trace_summary"],
            metadata=_json_loads(row["metadata"], {}),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


def _safe_col(row: Any, name: str, default: Any) -> Any:
    """安全读取行字段；旧库缺列时返回默认值。"""
    try:
        return row[name] if name in row.keys() else default
    except (KeyError, IndexError):
        return default
