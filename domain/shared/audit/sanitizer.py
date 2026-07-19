from __future__ import annotations

import re
from typing import Any


_PATTERNS: list[tuple[str, str]] = [
    (r"1[3-9]\d{9}", "PHONE_MASKED"),
    (r"\d{17}[\dXx]", "ID_CARD_MASKED"),
    (r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "EMAIL_MASKED"),
    (r"\b\d{16,19}\b", "BANK_CARD_MASKED"),
    # P2-6：新增护照（中国护照格式：1 字母 + 8 数字）与 IPv4 脱敏
    (r"\b[A-Z]\d{8}\b", "PASSPORT_MASKED"),
    (r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "IP_MASKED"),
]


def sanitize(text: str) -> str:
    result = text
    for pattern, replacement in _PATTERNS:
        result = re.sub(pattern, replacement, result)
    return result


def sanitize_dict(data: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, str):
            sanitized[key] = sanitize(value)
        elif isinstance(value, dict):
            sanitized[key] = sanitize_dict(value)
        else:
            sanitized[key] = value
    return sanitized
