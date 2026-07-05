from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from infrastructure.persistence.database import get_connection, _json_dumps, _json_loads


class TaskStatus(str, Enum):
    IDLE = "idle"
    IN_PROGRESS = "in_progress"
    NEEDS_USER_INPUT = "needs_user_input"
    NEEDS_CONFIRMATION = "needs_confirmation"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskRecord:
    session_id: str
    user_id: str
    status: TaskStatus = TaskStatus.IDLE
    goal: str = ""
    latest_user_message: str = ""
    latest_reply: str = ""
    pending_prompt: str = ""
    trace_summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def mark_in_progress(self, *, goal: str, latest_user_message: str) -> None:
        self.status = TaskStatus.IN_PROGRESS
        self.goal = goal
        self.latest_user_message = latest_user_message
        self.updated_at = datetime.utcnow().isoformat()

    def mark_waiting(self, *, status: TaskStatus, prompt: str, reply: str) -> None:
        self.status = status
        self.pending_prompt = prompt
        self.latest_reply = reply
        self.updated_at = datetime.utcnow().isoformat()

    def mark_finished(self, *, status: TaskStatus, reply: str) -> None:
        self.status = status
        self.latest_reply = reply
        if status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.IDLE}:
            self.pending_prompt = ""
        self.updated_at = datetime.utcnow().isoformat()

    def cache_tool_result(self, tool_name: str, args: dict, result: str) -> None:
        if "cached_tool_results" not in self.metadata:
            self.metadata["cached_tool_results"] = {}
        category = self._tool_category(tool_name)
        self.metadata["cached_tool_results"][category] = {
            "tool_name": tool_name,
            "args": args,
            "result": result,
            "updated_at": datetime.utcnow().isoformat(),
        }
        self.updated_at = datetime.utcnow().isoformat()

    def get_cached_results(self) -> dict[str, dict]:
        return self.metadata.get("cached_tool_results", {})

    def invalidate_cache(self, *categories: str) -> None:
        cached = self.metadata.get("cached_tool_results", {})
        if not categories:
            self.metadata.pop("cached_tool_results", None)
        else:
            for cat in categories:
                cached.pop(cat, None)
        self.updated_at = datetime.utcnow().isoformat()

    @staticmethod
    def _tool_category(tool_name: str) -> str:
        if "flight" in tool_name:
            return "flight"
        if "train" in tool_name:
            return "train"
        if "hotel" in tool_name:
            return "hotel"
        if "poi" in tool_name or "search_poi" in tool_name:
            return "poi"
        if "weather" in tool_name:
            return "weather"
        if "route" in tool_name or "plan_route" in tool_name:
            return "route"
        if "keyword_search" in tool_name:
            return "keyword_search"
        return tool_name


class TaskStateStore:
    def __init__(self) -> None:
        self._tasks: dict[str, TaskRecord] = {}

    def get(self, session_id: str, *, user_id: str) -> TaskRecord:
        if session_id not in self._tasks:
            self._tasks[session_id] = self._load(session_id) or TaskRecord(
                session_id=session_id,
                user_id=user_id,
            )
        task = self._tasks[session_id]
        if task.user_id != user_id:
            task.user_id = user_id
            task.updated_at = datetime.utcnow().isoformat()
        return task

    def save(self, task: TaskRecord) -> None:
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

    def snapshot(self, session_id: str, *, user_id: str) -> dict[str, Any]:
        from dataclasses import asdict

        task = self.get(session_id, user_id=user_id)
        return asdict(task)

    def _load(self, session_id: str) -> TaskRecord | None:
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
