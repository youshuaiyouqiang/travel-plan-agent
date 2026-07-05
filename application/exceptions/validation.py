from __future__ import annotations

from application.exceptions.base import ClawException


class ValidationException(ClawException):
    """参数校验失败异常"""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(code=400001, message=message, http_status=400, details=details)
