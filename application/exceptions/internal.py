from __future__ import annotations

from application.exceptions.base import ClawException


class InternalException(ClawException):
    """服务器内部错误异常"""

    def __init__(self, message: str = "服务器内部错误"):
        super().__init__(code=500001, message=message, http_status=500)


class ServiceUnavailableException(ClawException):
    """服务暂不可用异常"""

    def __init__(self, message: str = "服务暂不可用"):
        super().__init__(code=503001, message=message, http_status=503)
