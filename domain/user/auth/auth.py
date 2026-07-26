from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime

from domain.user.auth.ports import (
    PasswordHasherPort,
    UserRepositoryPort,
    get_default_password_hasher,
    get_default_user_repository,
)


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
    """用户存储；通过 ``UserRepositoryPort`` 与 ``PasswordHasherPort`` 访问持久化与哈希。

    P2.3：原直连 ``get_connection()`` 的 SQL 与 ``infrastructure.security.password``
    模块函数已下沉到 infrastructure 层端口实现。本类只负责内存缓存（带 TTL）、
    username 索引与业务逻辑编排（创建、认证、PBKDF2 → bcrypt 自动升级）。
    """

    # P2-1：缓存 TTL（秒），过期后下次 _load_to_cache 重新从 DB 加载
    _CACHE_TTL = 300

    def __init__(
        self,
        repository: UserRepositoryPort | None = None,
        hasher: PasswordHasherPort | None = None,
    ) -> None:
        self._repository = repository or get_default_user_repository()
        self._hasher = hasher or get_default_password_hasher()
        self._cache: dict[str, User] = {}
        self._username_index: dict[str, str] = {}
        self._cache_time: float = 0.0

    def _load_to_cache(self) -> None:
        # P2-1：TTL 过期则清空重载，避免缓存永不刷新
        if self._cache and (time.time() - self._cache_time) < self._CACHE_TTL:
            return
        self._cache.clear()
        self._username_index.clear()
        for user in self._repository.load_all():
            self._cache[user.user_id] = user
            self._username_index[user.username] = user.user_id
        self._cache_time = time.time()

    def create(self, username: str, password: str) -> User:
        self._load_to_cache()
        if username in self._username_index:
            raise ValueError("用户名已存在")
        user_id = os.urandom(8).hex()
        password_hash = self._hasher.hash(password)
        now = datetime.utcnow().isoformat()
        user = User(user_id=user_id, username=username, password_hash=password_hash, created_at=now, updated_at=now)
        self._repository.insert(user)
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
        if not self._hasher.verify(password, user.password_hash):
            return None
        # Auto-upgrade: PBKDF2 → bcrypt
        if self._hasher.needs_upgrade(user.password_hash):
            new_hash = self._hasher.hash(password)
            self._repository.update_password(user.user_id, new_hash, datetime.utcnow().isoformat())
            user.password_hash = new_hash
        return user

    def get_by_id(self, user_id: str) -> User | None:
        self._load_to_cache()
        return self._cache.get(user_id)

    def get_by_username(self, username: str) -> User | None:
        """按 username 查找用户；找不到返回 None。

        供启动期解析 ``YUNHE_ADMIN_USERNAME`` → ``user_id`` 使用。
        """
        self._load_to_cache()
        user_id = self._username_index.get(username)
        if not user_id:
            return None
        return self._cache.get(user_id)
