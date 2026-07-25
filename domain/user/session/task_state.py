from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from domain.user.session.ports import (
    SessionRepositoryPort,
    get_default_session_repository,
)


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
    """任务状态存储；通过 ``SessionRepositoryPort`` 访问持久化层。

    P2.1：原直连 ``get_connection()`` 的 SQL 已下沉到
    ``infrastructure.persistence.repositories.session.SqliteSessionRepository``。
    """

    def __init__(self, repository: SessionRepositoryPort | None = None) -> None:
        self._repository = repository or get_default_session_repository()
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
        self._repository.save_task(task)

    def snapshot(self, session_id: str, *, user_id: str) -> dict[str, Any]:
        from dataclasses import asdict

        task = self.get(session_id, user_id=user_id)
        return asdict(task)

    def _load(self, session_id: str) -> TaskRecord | None:
        return self._repository.load_task(session_id)
