from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass

from infrastructure.persistence.database import get_connection


@dataclass
class TokenData:
    user_id: str
    token: str
    expires_at: float


_TOKEN_EXPIRY_SECONDS = 86400 * 7

# Task 4: 令牌安全 — 只存储 sha256(token)，原 token 明文不入库。
# `auth_tokens` 旧表保留兼容（迁移 12 之后由 `auth_token_hashes` 接管），
# 新代码统一使用 `hash_token(token)` 作为数据库 key。


def hash_token(token: str) -> str:
    """计算 token 的 SHA-256 哈希。

    所有数据库写入与查询均以 ``hash_token(token)`` 作为 key，
    原始 token 永不落盘。bearer / cookie 两种认证方式共用同一张表。
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _ensure_table() -> None:
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_token_hashes_user ON auth_token_hashes(user_id)")
    conn.commit()


def generate_token(user_id: str) -> str:
    """生成新 token 并入库其哈希，返回原始 token 给调用方。"""
    raw = f"{user_id}:{os.urandom(16).hex()}:{time.time()}"
    token = hashlib.sha256(raw.encode()).hexdigest()
    expires_at = time.time() + _TOKEN_EXPIRY_SECONDS
    _ensure_table()
    conn = get_connection()
    conn.execute(
        "INSERT INTO auth_token_hashes (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
        (hash_token(token), user_id, expires_at),
    )
    conn.commit()
    return token


def verify_token(token: str) -> str | None:
    """校验 token（先哈希再查询）。返回 user_id 或 None。"""
    if not token:
        return None
    _ensure_table()
    conn = get_connection()
    now = time.time()
    conn.execute("DELETE FROM auth_token_hashes WHERE expires_at < ?", (now,))
    conn.commit()
    row = conn.execute(
        "SELECT user_id, expires_at FROM auth_token_hashes WHERE token_hash = ?",
        (hash_token(token),),
    ).fetchone()
    if not row or time.time() > row["expires_at"]:
        return None
    return row["user_id"]


def revoke_token(token: str) -> None:
    """撤销 token（按哈希删除）。"""
    if not token:
        return
    _ensure_table()
    conn = get_connection()
    conn.execute("DELETE FROM auth_token_hashes WHERE token_hash = ?", (hash_token(token),))
    conn.commit()
