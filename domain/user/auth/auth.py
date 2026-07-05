from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime

from infrastructure.persistence.database import get_connection
from infrastructure.security.password import hash_password, verify_password, needs_upgrade


@dataclass
class User:
    user_id: str
    username: str
    password_hash: str
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at





class UserStore:
    # P2-1：缓存 TTL（秒），过期后下次 _load_to_cache 重新从 DB 加载
    _CACHE_TTL = 300

    def __init__(self) -> None:
        self._cache: dict[str, User] = {}
        self._username_index: dict[str, str] = {}
        self._cache_time: float = 0.0

    def _load_to_cache(self) -> None:
        # P2-1：TTL 过期则清空重载，避免缓存永不刷新
        if self._cache and (time.time() - self._cache_time) < self._CACHE_TTL:
            return
        self._cache.clear()
        self._username_index.clear()
        conn = get_connection()
        rows = conn.execute("SELECT user_id, username, password_hash, created_at, updated_at FROM users").fetchall()
        for row in rows:
            user = User(
                user_id=row["user_id"],
                username=row["username"],
                password_hash=row["password_hash"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            self._cache[user.user_id] = user
            self._username_index[user.username] = user.user_id
        self._cache_time = time.time()

    def create(self, username: str, password: str) -> User:
        self._load_to_cache()
        if username in self._username_index:
            raise ValueError("用户名已存在")
        user_id = os.urandom(8).hex()
        password_hash = hash_password(password)
        now = datetime.utcnow().isoformat()
        user = User(user_id=user_id, username=username, password_hash=password_hash, created_at=now, updated_at=now)
        conn = get_connection()
        conn.execute(
            "INSERT INTO users (user_id, username, password_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (user.user_id, user.username, user.password_hash, user.created_at, user.updated_at),
        )
        conn.commit()
        self._cache[user.user_id] = user
        self._username_index[user.username] = user.user_id
        return user

    def authenticate(self, username: str, password: str) -> User | None:
        self._load_to_cache()
        user_id = self._username_index.get(username)
        if not user_id:
            return None
        user = self._cache.get(user_id)
        if not user:
            return None
        if not verify_password(password, user.password_hash):
            return None
        # Auto-upgrade: PBKDF2 → bcrypt
        if needs_upgrade(user.password_hash):
            new_hash = hash_password(password)
            conn = get_connection()
            conn.execute(
                "UPDATE users SET password_hash = ?, updated_at = ? WHERE user_id = ?",
                (new_hash, datetime.utcnow().isoformat(), user.user_id),
            )
            conn.commit()
            user.password_hash = new_hash
        return user

    def get_by_id(self, user_id: str) -> User | None:
        self._load_to_cache()
        return self._cache.get(user_id)
