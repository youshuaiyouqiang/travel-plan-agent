from __future__ import annotations

from application.exceptions.base import ClawException


class ConflictException(ClawException):
    """资源冲突异常"""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(code=409001, message=message, http_status=409, details=details)
