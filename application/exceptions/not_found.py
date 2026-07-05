from __future__ import annotations

from application.exceptions.base import ClawException


class NotFoundException(ClawException):
    """资源未找到异常"""

    def __init__(self, resource: str, resource_id: str | int):
        message = f"{resource}未找到: {resource_id}"
        super().__init__(code=404001, message=message, http_status=404)
