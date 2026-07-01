from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime

from infrastructure.persistence.database import get_connection


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


def _hash_password(password: str, salt: str = "") -> str:
    if not salt:
        salt = os.urandom(16).hex()
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return f"{salt}${hashed.hex()}"


def _verify_password(password: str, password_hash: str) -> bool:
    if "$" not in password_hash:
        return False
    salt, _ = password_hash.split("$", 1)
    return _hash_password(password, salt) == password_hash


class UserStore:
    def __init__(self) -> None:
        self._cache: dict[str, User] = {}
        self._username_index: dict[str, str] = {}

    def _load_to_cache(self) -> None:
        if self._cache:
            return
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

    def create(self, username: str, password: str) -> User:
        self._load_to_cache()
        if username in self._username_index:
            raise ValueError("用户名已存在")
        user_id = os.urandom(8).hex()
        password_hash = _hash_password(password)
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
        if not _verify_password(password, user.password_hash):
            return None
        return user

    def get_by_id(self, user_id: str) -> User | None:
        self._load_to_cache()
        return self._cache.get(user_id)
