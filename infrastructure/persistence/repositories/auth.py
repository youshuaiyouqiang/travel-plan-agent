"""``UserRepositoryPort`` 与 ``TokenRepositoryPort`` 的 SQLite 实现。

P2.3 将原本散落在以下位置的裸 SQL 收敛到此：
- ``domain/user/auth/auth.py`` — ``UserStore._load_to_cache`` / ``create`` / ``authenticate``（升级路径）
- ``domain/user/auth/token.py`` — ``_ensure_table`` / ``generate_token`` / ``verify_token`` / ``revoke_token``

SQL 文本、参数化方式与防御性 ``CREATE TABLE IF NOT EXISTS`` 完全保留；
不改变表结构或迁移版本（迁移 12 已建 ``auth_token_hashes`` 表）。
"""

from __future__ import annotations

from domain.user.auth.auth import User
from infrastructure.persistence.connection import get_connection


class SqliteUserRepository:
    """``UserRepositoryPort`` 的 SQLite 实现。

    无状态，可单例复用。通过 ``get_connection()`` 获取当前连接，
    支持测试隔离的 ``reset_connection()`` 模式。
    """

    def load_all(self) -> list[User]:
        """加载全部用户行；用于 UserStore 的 TTL 缓存重建。"""
        conn = get_connection()
        rows = conn.execute(
            "SELECT user_id, username, password_hash, created_at, updated_at FROM users"
        ).fetchall()
        return [
            User(
                user_id=row["user_id"],
                username=row["username"],
                password_hash=row["password_hash"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def insert(self, user: User) -> None:
        """插入新用户行。"""
        conn = get_connection()
        conn.execute(
            "INSERT INTO users (user_id, username, password_hash, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user.user_id, user.username, user.password_hash, user.created_at, user.updated_at),
        )
        conn.commit()

    def update_password(self, user_id: str, password_hash: str, updated_at: str) -> None:
        """更新指定用户的密码哈希与 updated_at。"""
        conn = get_connection()
        conn.execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE user_id = ?",
            (password_hash, updated_at, user_id),
        )
        conn.commit()


class SqliteTokenRepository:
    """``TokenRepositoryPort`` 的 SQLite 实现。

    保留原 ``token._ensure_table()`` 的防御性建表逻辑：迁移 12 已创建
    ``auth_token_hashes`` 表，此处 ``CREATE TABLE IF NOT EXISTS`` 仅在
    表缺失时（如未执行 ``init_db`` 的边缘场景）兜底，幂等无副作用。
    """

    def _ensure_table(self) -> None:
        """防御性建表；迁移 12 已建表，此处仅兜底。"""
        conn = get_connection()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_token_hashes (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                expires_at REAL NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_auth_token_hashes_user ON auth_token_hashes(user_id)"
        )
        conn.commit()

    def insert(self, token_hash: str, user_id: str, expires_at: float) -> None:
        """插入新 token 哈希行。"""
        self._ensure_table()
        conn = get_connection()
        conn.execute(
            "INSERT INTO auth_token_hashes (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (token_hash, user_id, expires_at),
        )
        conn.commit()

    def find(self, token_hash: str) -> tuple[str, float] | None:
        """按 token 哈希查询 (user_id, expires_at)；不存在返回 None。"""
        self._ensure_table()
        conn = get_connection()
        row = conn.execute(
            "SELECT user_id, expires_at FROM auth_token_hashes WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()
        if not row:
            return None
        return row["user_id"], row["expires_at"]

    def delete_expired(self, now: float) -> None:
        """删除所有 expires_at < now 的过期行。"""
        self._ensure_table()
        conn = get_connection()
        conn.execute("DELETE FROM auth_token_hashes WHERE expires_at < ?", (now,))
        conn.commit()

    def delete(self, token_hash: str) -> None:
        """按 token 哈希删除单行（撤销 token）。"""
        self._ensure_table()
        conn = get_connection()
        conn.execute("DELETE FROM auth_token_hashes WHERE token_hash = ?", (token_hash,))
        conn.commit()


__all__ = [
    "SqliteTokenRepository",
    "SqliteUserRepository",
]
