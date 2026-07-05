from __future__ import annotations


class ClawException(Exception):
    """业务异常基类"""

    def __init__(
        self,
        code: int,
        message: str,
        http_status: int = 400,
        details: dict | None = None,
    ):
        self.code = code  # 业务错误码（6 位）
        self.message = message
        self.http_status = http_status  # 显式 HTTP 状态码
        self.details = details or {}
        super().__init__(message)
