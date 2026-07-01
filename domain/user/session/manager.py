from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from infrastructure.persistence.database import get_connection
from domain.user.session.task_state import TaskStateStore


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

    def save(self, session: Session) -> None:
        conn = get_connection()
        now = datetime.utcnow().isoformat()
        session.updated_at = now
        conn.execute(
            "INSERT INTO sessions (session_id, summary, created_at, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET summary=excluded.summary, updated_at=excluded.updated_at",
            (session.session_id, session.summary, session.created_at, session.updated_at),
        )
        conn.execute("DELETE FROM session_turns WHERE session_id = ?", (session.session_id,))
        for turn in session.turns:
            conn.execute(
                "INSERT INTO session_turns (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (session.session_id, turn.role, turn.content, turn.created_at),
            )
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
        return Session(
            session_id=row["session_id"],
            turns=turns,
            summary=row["summary"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


SessionStore = SessionManager
