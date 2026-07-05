from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime

from infrastructure.persistence.database import get_connection
from domain.user.session.task_state import TaskStateStore


def json_dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _json_loads_list(text: str | None) -> list:
    if not text:
        return []
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return []


@dataclass
class Turn:
    role: str
    content: str
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class Session:
    session_id: str
    turns: list[Turn] = field(default_factory=list)
    summary: str = ""
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    disclosed_tools: list[str] = field(default_factory=list)
    delegation_agent_id: str | None = None
    delegation_started_at: float | None = None
    delegation_last_interaction: float | None = None
    user_id: str = ""

    def append(self, role: str, content: str) -> None:
        self.turns.append(Turn(role=role, content=content))
        self.updated_at = datetime.utcnow().isoformat()

    def recent_messages(self, limit: int) -> list[Turn]:
        return self.turns[-limit:]


class SessionManager:
    def __init__(
        self,
        task_store: TaskStateStore | None = None,
        redis_store=None,
    ) -> None:
        self._redis_store = redis_store
        self._sessions: dict[str, Session] = {}
        self._task_store = task_store or TaskStateStore()

    def get(self, session_id: str) -> Session:
        if session_id not in self._sessions:
            if self._redis_store:
                redis_session = self._redis_store.get(session_id)
                if redis_session:
                    self._sessions[session_id] = redis_session
                    return redis_session
            self._sessions[session_id] = self._load(session_id) or Session(session_id=session_id)
        return self._sessions[session_id]

    def save(self, session: Session, user_id: str = "") -> None:
        conn = get_connection()
        now = datetime.utcnow().isoformat()
        session.updated_at = now
        # 若显式传入 user_id 则覆盖 session.user_id（便于调用方在创建会话时即指定归属）
        if user_id:
            session.user_id = user_id
        conn.execute(
            "INSERT INTO sessions (session_id, user_id, summary, created_at, updated_at, "
            "disclosed_tools, delegation_agent_id, delegation_started_at, delegation_last_interaction) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET "
            "user_id=excluded.user_id, "
            "summary=excluded.summary, updated_at=excluded.updated_at, "
            "disclosed_tools=excluded.disclosed_tools, "
            "delegation_agent_id=excluded.delegation_agent_id, "
            "delegation_started_at=excluded.delegation_started_at, "
            "delegation_last_interaction=excluded.delegation_last_interaction",
            (
                session.session_id,
                session.user_id,
                session.summary,
                session.created_at,
                session.updated_at,
                json_dumps(session.disclosed_tools),
                session.delegation_agent_id,
                session.delegation_started_at,
                session.delegation_last_interaction,
            ),
        )

        # P1-5：增量插入新 turns（替代全量 DELETE + INSERT）
        # _last_persisted_turn 由 _load() 在加载时设置，新会话默认 0
        last_persisted = getattr(session, "_last_persisted_turn", 0)
        # 安全检查：若内存中 turns 比已持久化的少（被截断），回退到全量重写
        if last_persisted > len(session.turns):
            conn.execute("DELETE FROM session_turns WHERE session_id = ?", (session.session_id,))
            for turn in session.turns:
                conn.execute(
                    "INSERT INTO session_turns (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                    (session.session_id, turn.role, turn.content, turn.created_at),
                )
        else:
            # 仅插入尚未持久化的 turns
            for turn in session.turns[last_persisted:]:
                conn.execute(
                    "INSERT INTO session_turns (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                    (session.session_id, turn.role, turn.content, turn.created_at),
                )
        session._last_persisted_turn = len(session.turns)

        conn.commit()
        if self._redis_store:
            self._redis_store.save(session)

    def snapshot(self, session_id: str, *, user_id: str | None = None) -> dict | None:
        session = self.get(session_id)
        if not session:
            return None
        from dataclasses import asdict

        return {
            "session_id": session.session_id,
            "summary": session.summary,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "turns": [asdict(turn) for turn in session.turns],
            "task": self._task_store.snapshot(session_id, user_id=user_id or session_id),
        }

    # ===== 渐进式披露：disclosed_tools =====

    def get_disclosed_tools(self, session_id: str) -> list[str]:
        """获取会话中已披露的工具名列表。"""
        session = self.get(session_id)
        return session.disclosed_tools

    def set_disclosed_tools(self, session_id: str, tools: list[str]) -> None:
        """设置会话中已披露的工具名列表并持久化。"""
        session = self.get(session_id)
        session.disclosed_tools = list(tools)
        self.save(session)

    def add_disclosed_tool(self, session_id: str, tool_name: str) -> None:
        """添加一个已披露工具。"""
        session = self.get(session_id)
        if tool_name not in session.disclosed_tools:
            session.disclosed_tools.append(tool_name)
            self.save(session)

    # ===== 委派上下文（Phase 3 使用） =====

    def get_delegation(self, session_id: str) -> dict | None:
        """获取委派上下文。"""
        session = self.get(session_id)
        if not session.delegation_agent_id:
            return None
        return {
            "agent_id": session.delegation_agent_id,
            "started_at": session.delegation_started_at,
            "last_interaction": session.delegation_last_interaction,
        }

    def set_delegation(self, session_id: str, agent_id: str) -> None:
        """设置委派上下文。"""
        import time

        session = self.get(session_id)
        session.delegation_agent_id = agent_id
        session.delegation_started_at = time.time()
        session.delegation_last_interaction = time.time()
        self.save(session)

    def clear_delegation(self, session_id: str) -> None:
        """清除委派上下文。"""
        session = self.get(session_id)
        session.delegation_agent_id = None
        session.delegation_started_at = None
        session.delegation_last_interaction = None
        self.save(session)

    def _load(self, session_id: str) -> Session | None:
        conn = get_connection()
        row = conn.execute(
            "SELECT session_id, summary, created_at, updated_at FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            return None
        turns = []
        turn_rows = conn.execute(
            "SELECT role, content, created_at FROM session_turns WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
        for tr in turn_rows:
            turns.append(Turn(role=tr["role"], content=tr["content"], created_at=tr["created_at"]))

        # 读取 optional 列（try/except 兼容旧数据库无这些列）
        user_id: str = ""
        disclosed_tools: list[str] = []
        delegation_agent_id: str | None = None
        delegation_started_at: float | None = None
        delegation_last_interaction: float | None = None
        try:
            user_id = row["user_id"] if "user_id" in row.keys() else ""
        except (KeyError, IndexError):
            pass
        try:
            dt_val = row["disclosed_tools"] if "disclosed_tools" in row.keys() else None
            disclosed_tools = _json_loads_list(dt_val)
        except (KeyError, IndexError):
            pass
        try:
            delegation_agent_id = row["delegation_agent_id"] if "delegation_agent_id" in row.keys() else None
        except (KeyError, IndexError):
            pass
        try:
            delegation_started_at = row["delegation_started_at"] if "delegation_started_at" in row.keys() else None
        except (KeyError, IndexError):
            pass
        try:
            delegation_last_interaction = (
                row["delegation_last_interaction"] if "delegation_last_interaction" in row.keys() else None
            )
        except (KeyError, IndexError):
            pass

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
        )
        # P1-5：标记已持久化的 turn 数，避免 save() 时重复插入
        session._last_persisted_turn = len(turns)
        return session


SessionStore = SessionManager
