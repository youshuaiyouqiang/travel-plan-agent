# api/middleware/rate_limit.py - 速率限制中间件(可选)
"""
速率限制中间件 - 防止API滥用
职责: 控制用户请求频率,防止恶意攻击
状态: ⚠️ 可选实现(当前未启用)
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from typing import Dict
import time


class RateLimiter:
    """简单的速率限制器"""

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[str, list] = {}

    def is_allowed(self, client_id: str) -> bool:
        """检查是否允许请求"""
        now = time.time()
        window_start = now - self.window_seconds

        # 清理过期记录
        if client_id in self.requests:
            self.requests[client_id] = [
                t for t in self.requests[client_id] if t > window_start
            ]
        else:
            self.requests[client_id] = []

        # 检查是否超限
        if len(self.requests[client_id]) >= self.max_requests:
            return False

        # 记录本次请求
        self.requests[client_id].append(now)
        return True


class RateLimitMiddleware:
    """速率限制中间件"""

    def __init__(self, rate_limiter: RateLimiter = None):
        self.rate_limiter = rate_limiter

    async def dispatch(self, request: Request, call_next):
        """中间件核心逻辑"""

        # 仅对chat接口限流
        if request.url.path == "/api/chat" and self.rate_limiter:
            client_id = request.client.host if request.client else "unknown"

            if not self.rate_limiter.is_allowed(client_id):
                return JSONResponse(
                    status_code=429,
                    content={"detail": "请求过于频繁,请稍后再试"}
                )

        return await call_next(request)


# 导出中间件实例(供server.py注册,当前未启用)
# rate_limit_middleware = RateLimitMiddleware(RateLimiter(max_requests=10, window_seconds=60))