from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from domain.reasoning.engine import TraceStep


@dataclass
class RunTrace:
    session_id: str
    user_message: str
    reply: str
    intent: str
    goal: str
    user_id: str = ""
    tools: list[str] = field(default_factory=list)
    memory_context: str = ""
    trace_steps: list[TraceStep] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "user_message": self.user_message,
            "reply": self.reply,
            "intent": self.intent,
            "goal": self.goal,
            "tools": self.tools,
            "memory_context": self.memory_context,
            "trace_steps": [asdict(step) for step in self.trace_steps],
            "events": self.events,
            "created_at": self.created_at,
        }


class TraceStore:
    def __init__(self) -> None:
        self._latest_by_session: dict[str, RunTrace] = {}

    def put(self, trace: RunTrace) -> None:
        self._latest_by_session[trace.session_id] = trace

    def latest(self, session_id: str) -> RunTrace | None:
        return self._latest_by_session.get(session_id)
