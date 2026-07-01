from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

class IntentType(str,Enum):
    CHAT = "chat"
    QUERY = "query"
    TASK = "task"
    FOLLOW_UP = "follow_up"

@dataclass
class IntentResult:
    intent: IntentType
    goal:str
    fast_reply:bool = False
    force_tool:bool = False
    tool_hints:list[str] = field(default_factory = list)

class DecisionType(str,Enum):
    FINAL_ANSWER = "final_answer"
    TOOL_CALLS = "tool_calls"

@dataclass
class ToolCall:
    name:str
    arguments: dict[str,Any]
    call_id:str

@dataclass
class Decision:
    decision_type:DecisionType
    text: str = ""
    tool_calls:list[ToolCall] = field(default_factory = list)
    raw: Any = None

@dataclass
class TraceEvent:
    kind: str
    message: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""


