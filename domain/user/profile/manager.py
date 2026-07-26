from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

from domain.user.profile.ports import (
    ProfileRepositoryPort,
    get_default_profile_repository,
)
from domain.user.profile.schema import UserProfile

logger = logging.getLogger(__name__)


class ProfileManager:
    """用户画像管理器；通过 ``ProfileRepositoryPort`` 访问持久化层。

    P2.2：原直连 ``get_connection()`` 的 SQL 已下沉到
    ``infrastructure.persistence.repositories.profile.SqliteProfileRepository``。
    本类只负责内存缓存与业务逻辑编排。
    """

    # P2-1：缓存 TTL（秒），过期后下次 get 重新从 DB 加载
    _CACHE_TTL = 300

    def __init__(self, repository: ProfileRepositoryPort | None = None) -> None:
        self._repository = repository or get_default_profile_repository()
        self._cache: dict[str, UserProfile] = {}
        self._cache_time: dict[str, float] = {}

    def get(self, user_id: str) -> UserProfile:
        now = time.time()
        cached_at = self._cache_time.get(user_id, 0.0)
        if user_id not in self._cache or (now - cached_at) > self._CACHE_TTL:
            self._cache[user_id] = self._load(user_id) or UserProfile(user_id=user_id)
            self._cache_time[user_id] = now
        return self._cache[user_id]

    def update(
        self,
        user_id: str,
        *,
        tags: list[str] | None = None,
        intent: str | None = None,
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
        return self._repository.load_profile(user_id)

    def _save(self, profile: UserProfile) -> None:
        self._repository.save_profile(profile)
