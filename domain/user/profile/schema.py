from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class UserProfile:
    user_id: str
    tags: list[str] = field(default_factory=list)
    interaction_count: int = 0
    last_intent: str = ""
    preferred_categories: list[str] = field(default_factory=list)
    emotion_history: list[str] = field(default_factory=list)
    custom_attributes: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
