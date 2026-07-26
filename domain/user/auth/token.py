from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass

from domain.user.auth.ports import TokenRepositoryPort, get_default_token_repository


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

    纯函数，无基础设施依赖；供 domain 层与 infrastructure 仓储实现共用。
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_token(
    user_id: str,
    repository: TokenRepositoryPort | None = None,
) -> str:
    """生成新 token 并入库其哈希，返回原始 token 给调用方。

    Args:
        user_id: 令牌归属用户 ID。
        repository: 可选的令牌仓储；未注入时回退到全局默认实现。
    """
    repo = repository or get_default_token_repository()
    raw = f"{user_id}:{os.urandom(16).hex()}:{time.time()}"
    token = hashlib.sha256(raw.encode()).hexdigest()
    expires_at = time.time() + _TOKEN_EXPIRY_SECONDS
    repo.insert(hash_token(token), user_id, expires_at)
    return token


def verify_token(
    token: str,
    repository: TokenRepositoryPort | None = None,
) -> str | None:
    """校验 token（先哈希再查询）。返回 user_id 或 None。

    Args:
        token: 待校验的原始 token。
        repository: 可选的令牌仓储；未注入时回退到全局默认实现。
    """
    if not token:
        return None
    repo = repository or get_default_token_repository()
    now = time.time()
    repo.delete_expired(now)
    found = repo.find(hash_token(token))
    if not found:
        return None
    user_id, expires_at = found
    if time.time() > expires_at:
        return None
    return user_id


def revoke_token(
    token: str,
    repository: TokenRepositoryPort | None = None,
) -> None:
    """撤销 token（按哈希删除）。

    Args:
        token: 待撤销的原始 token。
        repository: 可选的令牌仓储；未注入时回退到全局默认实现。
    """
    if not token:
        return
    repo = repository or get_default_token_repository()
    repo.delete(hash_token(token))
