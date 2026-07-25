"""会话持久化 Repository —— 兼容 re-export 层（P2.1 拆分后）。

**历史与现状：** 本文件原为 sessions / tasks / session_turns 三张表的裸 SQL
入口，P2.1 已将其实现迁移至
``infrastructure.persistence.repositories.session.SqliteSessionRepository``。

**兼容承诺：** 既有调用方仍可从 ``infrastructure.persistence.session_repository``
导入 ``SessionRepository``；其静态方法委托到新的实例实现。新代码应直接使用
``SqliteSessionRepository`` 或通过 ``SessionRepositoryPort`` 端口注入。
"""

from __future__ import annotations

from typing import Any

from infrastructure.persistence.repositories.session import SqliteSessionRepository

# 模块级单例，供静态方法委托
_impl = SqliteSessionRepository()


class SessionRepository:
    """兼容外观：将原有静态方法委托到 ``SqliteSessionRepository`` 单例。"""

    @staticmethod
    def create(
        session_id: str,
        user_id: str,
        *,
        summary: str = "",
        created_at: str | None = None,
    ) -> None:
        """新建一个会话（兼容旧签名；新代码用 ``create_session_row``）。"""
        # 旧 create 只写 sessions + tasks 基础字段，不带 mode/lock；
        # 直接调用 SqliteSessionRepository 的对应方法。
        from datetime import datetime

        now = created_at or datetime.utcnow().isoformat()
        from infrastructure.persistence.connection import get_connection

        conn = get_connection()
        conn.execute(
            "INSERT INTO sessions (session_id, summary, created_at, updated_at, user_id) VALUES (?, ?, ?, ?, ?)",
            (session_id, summary, now, now, user_id),
        )
        conn.execute(
            "INSERT INTO tasks (session_id, user_id, status, goal, created_at, updated_at) "
            "VALUES (?, ?, 'idle', '', ?, ?)",
            (session_id, user_id, now, now),
        )
        conn.commit()

    @staticmethod
    def list_by_user(user_id: str) -> list[dict[str, Any]]:
        """列出指定用户的所有会话。"""
        return _impl.list_sessions_by_user(user_id)

    @staticmethod
    def get_messages(session_id: str) -> list[dict[str, Any]]:
        """按时间顺序返回某会话的所有消息。"""
        return _impl.get_session_messages(session_id)

    @staticmethod
    def delete(session_id: str) -> None:
        """级联删除一个会话。"""
        _impl.delete_session(session_id)
