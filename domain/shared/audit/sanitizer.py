from __future__ import annotations

import re
from typing import Any


_PATTERNS: list[tuple[str, str]] = [
    (r"1[3-9]\d{9}", "PHONE_MASKED"),
    (r"\d{17}[\dXx]", "ID_CARD_MASKED"),
    (r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "EMAIL_MASKED"),
    (r"\b\d{16,19}\b", "BANK_CARD_MASKED"),
]


def sanitize(text: str) -> str:
    result = text
    for pattern, replacement in _PATTERNS:
        result = re.sub(pattern, replacement, result)
    return result


def sanitize_dict(data: dict[str, Any]) -> dict[str, Any]:
    sanitized = {}
    for key, value in data.items():
        if isinstance(value, str):
            sanitized[key] = sanitize(value)
        elif isinstance(value, dict):
            sanitized[key] = sanitize_dict(value)
        else:
            sanitized[key] = value
    return sanitized
