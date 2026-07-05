"""审计上下文 — 基于 contextvars 的并发安全审计上下文（P0-5）。

为什么用 contextvars：
- OpenAILLM / ReasoningEngine / ToolExecutor 在 build_orchestrator 中以单例形式创建
- 若用实例属性存储 session_id/user_id/trace_id，并发请求会互相覆盖
- contextvars.ContextVar 在每个 asyncio task 中有独立副本，天然隔离

用法：
    from domain.shared.audit.context import AuditContext

    # 设置
    AuditContext.set(session_id="s1", user_id="u1", trace_id="t1")

    # 读取
    ctx = AuditContext.get()
    print(ctx.session_id, ctx.user_id, ctx.trace_id)
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass


_audit_ctx: contextvars.ContextVar["AuditContextData"] = contextvars.ContextVar("audit_ctx", default=None)


@dataclass
class AuditContextData:
    session_id: str = ""
    user_id: str = ""
    trace_id: str = ""


class AuditContext:
    """审计上下文存取入口（contextvars 实现，并发安全）。"""

    @staticmethod
    def set(*, session_id: str = "", user_id: str = "", trace_id: str = "") -> None:
        _audit_ctx.set(AuditContextData(session_id=session_id, user_id=user_id, trace_id=trace_id))

    @staticmethod
    def get() -> AuditContextData:
        ctx = _audit_ctx.get()
        return ctx if ctx is not None else AuditContextData()

    @staticmethod
    def clear() -> None:
        _audit_ctx.set(AuditContextData())
