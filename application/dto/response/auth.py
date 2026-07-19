from __future__ import annotations

from pydantic import BaseModel, Field


class AuthResponse(BaseModel):
    """登录/注册成功响应体。

    P0-1 修复：响应体不再包含 ``token`` 字段。浏览器登录凭据以 HttpOnly cookie 形式下发，
    JS 无法读取；前端所有 API 调用通过 ``features/auth/client.ts`` 走 cookie + CSRF 流程。
    非浏览器客户端如需 Bearer token，应使用专门的管理端点或预签发凭据，不在登录响应中暴露。
    """

    user_id: str = Field(description="用户ID")
    username: str = Field(description="用户名")
