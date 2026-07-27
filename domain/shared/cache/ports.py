"""缓存与限流端口 — 供应商无关的能力抽象。

P7 引入：``api/middleware`` 不再直接导入 ``infrastructure.cache``；
限流器在 ``app.py`` 组合根中实例化，通过 ``app.state`` 暴露给中间件。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class RateLimitPort(Protocol):
    """限流器供应商无关端口。

    实现方（``infrastructure.cache.RateLimiter``）必须提供 ``is_allowed``；
    返回 ``(allowed, info)``，``info`` 至少包含 ``limit``/``remaining``/``reset``。
    """

    def is_allowed(
        self, key: str, limit: int, window: int = 60
    ) -> tuple[bool, dict[str, int | float]]: ...


class NullRateLimiter:
    """``RateLimitPort`` 的空对象实现。

    始终允许请求；用于未配置限流的部署与单测。
    不读 Redis、不维护内存计数器，对中间件透明。
    """

    def is_allowed(
        self, key: str, limit: int, window: int = 60
    ) -> tuple[bool, dict[str, int | float]]:
        return True, {"limit": limit, "remaining": limit, "reset": 0.0}


def as_rate_limit_port(candidate: Any) -> RateLimitPort:
    """将任何具备 ``is_allowed`` 接口的对象视为 ``RateLimitPort``。"""
    if isinstance(candidate, RateLimitPort):
        return candidate
    # 兜底：未实现端口时回退到空对象（始终放行），避免中间件崩溃
    return NullRateLimiter()
