# api/middleware/auth.py - 认证中间件
"""
认证中间件 - 提取自server.py
职责: 验证Token,保护私有接口,白名单路径管理
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from typing import Set

from domain.user.auth.token import verify_token


class AuthMiddleware:
    """认证中间件"""

    # 公开路径白名单(无需Token验证)
    PUBLIC_PATHS: Set[str] = {
        "/api/auth/register",
        "/api/auth/login",
        "/api/trending",
        "/health",
        "/metrics",
        "/api/shared"
    }

    async def dispatch(self, request: Request, call_next):
        """中间件核心逻辑"""

        # OPTIONS请求直接放行(CORS预检)
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path

        # 公开路径放行
        if (
            path.startswith("/debug")
            or path in self.PUBLIC_PATHS
            or path.startswith("/api/auth")
            or path.startswith("/api/shared")
        ):
            return await call_next(request)

        # Token验证逻辑
        auth_header = request.headers.get("Authorization", "")
        token = ""

        # 提取Bearer Token
        if auth_header.startswith("Bearer "):
            token = auth_header.removeprefix("Bearer ").strip()

        # 兜底:从query参数提取Token
        if not token:
            token = request.query_params.get("token", "")

        # 验证Token
        if token:
            user_id = verify_token(token)
            if user_id:
                # Token有效,注入user_id到request.state
                request.state.user_id = user_id
                return await call_next(request)

        # Token无效或缺失,返回401
        return JSONResponse(
            status_code=401,
            content={"detail": "未登录或登录已过期"}
        )


# 导出中间件实例(供server.py注册)
auth_middleware = AuthMiddleware()