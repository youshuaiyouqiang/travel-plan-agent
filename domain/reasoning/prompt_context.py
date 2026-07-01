from __future__ import annotations

from dataclasses import dataclass, field

from domain.reasoning.context_manager import PreparedContext
from domain.shared.types import IntentResult


@dataclass
class PromptContext:
    prepared_context: PreparedContext
    intent: IntentResult
    tools: list[str]
    travel_intent: str = ""
    memory_context: str = ""
    mcp_context: str = ""
    emotion_context: str = ""
    profile_context: str = ""
    cached_tool_context: str = ""
    dual_memory_context: str = ""
    missing_info_context: str = ""
    itinerary_confirm_context: str = ""
