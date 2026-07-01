from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class AuditEvent:
    event_id: str
    event_type: str
    session_id: str
    user_id: str
    trace_id: str = ""
    tool_name: str = ""
    action: str = ""
    input_summary: str = ""
    output_summary: str = ""
    risk_level: str = "low"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    llm_input: str = ""
    llm_output: str = ""
    duration_ms: int = 0
