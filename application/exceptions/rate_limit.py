from __future__ import annotations

from application.exceptions.base import ClawException


class RateLimitException(ClawException):
    """请求频率限制异常"""

    def __init__(self, message: str = "请求过于频繁"):
        super().__init__(code=429001, message=message, http_status=429)
