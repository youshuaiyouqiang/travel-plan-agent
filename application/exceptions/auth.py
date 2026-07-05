from __future__ import annotations

from application.exceptions.base import ClawException


class UnauthorizedException(ClawException):
    """未登录或登录已过期异常"""

    def __init__(self, message: str = "未登录或登录已过期"):
        super().__init__(code=401001, message=message, http_status=401)


class ForbiddenException(ClawException):
    """权限不足异常"""

    def __init__(self, message: str = "权限不足"):
        super().__init__(code=403001, message=message, http_status=403)
