"""``ProfileRepositoryPort`` 的 SQLite 实现。

P2.2 将原本在 ``domain/user/profile/manager.py`` 中的裸 SQL 收敛到此。
SQL 文本和参数化方式完全保留；不改变表结构或迁移版本。
"""

from __future__ import annotations

from domain.user.profile.schema import UserProfile
from infrastructure.persistence.connection import get_connection
from infrastructure.persistence.serialization import _json_dumps, _json_loads


class SqliteProfileRepository:
    """``ProfileRepositoryPort`` 的 SQLite 实现。

    无状态，可单例复用。通过 ``get_connection()`` 获取当前连接，
    支持测试隔离的 ``reset_connection()`` 模式。
    """

    def load_profile(self, user_id: str) -> UserProfile | None:
        """加载用户画像；不存在返回 None。"""
        conn = get_connection()
        row = conn.execute(
            "SELECT user_id, tags, interaction_count, last_intent, preferred_categories, "
            "custom_attributes, created_at, updated_at "
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
            custom_attributes=_json_loads(row["custom_attributes"], {}),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def save_profile(self, profile: UserProfile) -> None:
        """Upsert 用户画像行。"""
        conn = get_connection()
        conn.execute(
            "INSERT INTO profiles (user_id, tags, interaction_count, last_intent, preferred_categories, "
            "custom_attributes, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET tags=excluded.tags, interaction_count=excluded.interaction_count, "
            "last_intent=excluded.last_intent, preferred_categories=excluded.preferred_categories, "
            "custom_attributes=excluded.custom_attributes, updated_at=excluded.updated_at",
            (
                profile.user_id,
                _json_dumps(profile.tags),
                profile.interaction_count,
                profile.last_intent,
                _json_dumps(profile.preferred_categories),
                _json_dumps(profile.custom_attributes),
                profile.created_at,
                profile.updated_at,
            ),
        )
        conn.commit()
