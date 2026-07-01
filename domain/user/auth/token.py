from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass


@dataclass
class TokenData:
    user_id: str
    token: str
    expires_at: float


_TOKEN_EXPIRY_SECONDS = 86400 * 7
_token_store: dict[str, TokenData] = {}


def generate_token(user_id: str) -> str:
    raw = f"{user_id}:{os.urandom(16).hex()}:{time.time()}"
    token = hashlib.sha256(raw.encode()).hexdigest()
    expires_at = time.time() + _TOKEN_EXPIRY_SECONDS
    _token_store[token] = TokenData(user_id=user_id, token=token, expires_at=expires_at)
    return token


def verify_token(token: str) -> str | None:
    data = _token_store.get(token)
    if not data:
        return None
    if time.time() > data.expires_at:
        _token_store.pop(token, None)
        return None
    return data.user_id


def revoke_token(token: str) -> None:
    _token_store.pop(token, None)
