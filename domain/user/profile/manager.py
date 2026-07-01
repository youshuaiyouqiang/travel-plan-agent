from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from infrastructure.persistence.database import get_connection, _json_dumps, _json_loads
from domain.user.profile.schema import UserProfile

logger = logging.getLogger(__name__)


class ProfileManager:
    def __init__(self) -> None:
        self._cache: dict[str, UserProfile] = {}

    def get(self, user_id: str) -> UserProfile:
        if user_id not in self._cache:
            self._cache[user_id] = self._load(user_id) or UserProfile(user_id=user_id)
        return self._cache[user_id]

    def update(
        self,
        user_id: str,
        *,
        tags: list[str] | None = None,
        intent: str | None = None,
        emotion: str | None = None,
        category: str | None = None,
        custom: dict[str, Any] | None = None,
    ) -> UserProfile:
        profile = self.get(user_id)
        profile.interaction_count += 1

        if tags:
            for tag in tags:
                if tag not in profile.tags:
                    profile.tags.append(tag)

        if intent:
            profile.last_intent = intent

        if category:
            if category not in profile.preferred_categories:
                profile.preferred_categories.append(category)
            if len(profile.preferred_categories) > 10:
                profile.preferred_categories = profile.preferred_categories[-10:]

        if emotion:
            profile.emotion_history.append(emotion)
            if len(profile.emotion_history) > 20:
                profile.emotion_history = profile.emotion_history[-20:]

        if custom:
            profile.custom_attributes.update(custom)

        profile.updated_at = datetime.utcnow().isoformat()

        self._save(profile)
        return profile

    def build_context(self, user_id: str) -> str:
        profile = self.get(user_id)
        if profile.interaction_count == 0:
            return ""
        lines = [f"用户画像 (交互次数: {profile.interaction_count})"]
        if profile.tags:
            lines.append(f"标签: {', '.join(profile.tags)}")
        if profile.preferred_categories:
            lines.append(f"关注领域: {', '.join(profile.preferred_categories[-5:])}")
        if profile.last_intent:
            lines.append(f"最近意图: {profile.last_intent}")
        return "\n".join(lines)

    def _load(self, user_id: str) -> UserProfile | None:
        conn = get_connection()
        row = conn.execute(
            "SELECT user_id, tags, interaction_count, last_intent, preferred_categories, "
            "emotion_history, custom_attributes, created_at, updated_at "
            "FROM profiles WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            return None
        return UserProfile(
            user_id=row["user_id"],
            tags=_json_loads(row["tags"], []),
            interaction_count=int(row["interaction_count"]),
            last_intent=row["last_intent"],
            preferred_categories=_json_loads(row["preferred_categories"], []),
            emotion_history=_json_loads(row["emotion_history"], []),
            custom_attributes=_json_loads(row["custom_attributes"], {}),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _save(self, profile: UserProfile) -> None:
        conn = get_connection()
        conn.execute(
            "INSERT INTO profiles (user_id, tags, interaction_count, last_intent, preferred_categories, "
            "emotion_history, custom_attributes, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET tags=excluded.tags, interaction_count=excluded.interaction_count, "
            "last_intent=excluded.last_intent, preferred_categories=excluded.preferred_categories, "
            "emotion_history=excluded.emotion_history, "
            "custom_attributes=excluded.custom_attributes, updated_at=excluded.updated_at",
            (
                profile.user_id,
                _json_dumps(profile.tags),
                profile.interaction_count,
                profile.last_intent,
                _json_dumps(profile.preferred_categories),
                _json_dumps(profile.emotion_history),
                _json_dumps(profile.custom_attributes),
                profile.created_at,
                profile.updated_at,
            ),
        )
        conn.commit()
