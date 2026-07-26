"""LLM 端口定义 — 供应商无关的生成、流式生成、工具调用接口。

P4.1 引入：domain/application 层只依赖 ``LLMPort``；
``OpenAILLM`` 与 ``FallbackLLM`` 显式满足该端口。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class ToolCallResult:
    """LLM 原生工具调用结果（供应商无关）。"""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """LLM 带工具调用的响应（供应商无关）。"""

    content: str = ""
    tool_calls: list[ToolCallResult] = field(default_factory=list)
    has_tool_calls: bool = False


@runtime_checkable
class LLMPort(Protocol):
    """LLM 供应商无关端口。

    实现方（``OpenAILLM``、``FallbackLLM``）必须提供以下方法；
    输入输出类型由 domain 定义，不得泄漏 OpenAI SDK 类型。
    """

    def set_audit_context(self, *, session_id: str, user_id: str, trace_id: str = "") -> None:
        """设置审计上下文（并发安全，基于 ContextVar）。"""
        ...

    async def complete(self, *, system: str, messages: list[dict[str, Any]]) -> str:
        """同步文本生成。"""
        ...

    def stream_complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
    ) -> AsyncGenerator[str, None]:
        """流式生成，逐 token yield 文本片段。

        实现方使用 ``async def`` + ``yield`` 定义异步生成器；
        端口声明为普通 ``def`` 返回 ``AsyncGenerator`` 以匹配
        异步生成器函数的调用签名（调用即返回 AsyncGenerator，无需 await）。
        """
        ...

    async def complete_with_tools(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        """带工具调用的生成；返回 ``LLMResponse``。"""
        ...

    async def complete_json(self, *, system: str, user: str) -> dict[str, Any]:
        """JSON 生成（带容错解析，失败返回空 dict）。"""
        ...


# ── 默认 LLM 装配（过渡方案，与 P2 仓储端口模式一致） ──────────────────────
#
# P4.1 引入：``ItineraryParser`` / ``TravelIntentClassifier`` 等领域组件
# 历史上在 ``__init__`` 内 ``OpenAILLM()`` 自行构造 LLM。端口化后领域层无法
# 直接 import ``infrastructure.llm.openai``，改为由组合根在启动期调用
# ``configure_default_llm(llm)`` 注册全局默认实现，未显式注入时回退到此默认值。
# P3 收敛组合根后，``app.py`` 的 ``build_orchestrator()`` 是唯一注册点。

_default_llm: LLMPort | None = None


def configure_default_llm(llm: LLMPort | None) -> None:
    """注册全局默认 LLM（由组合根调用）。"""
    global _default_llm
    _default_llm = llm


def get_default_llm() -> LLMPort | None:
    """返回组合根注册的默认 LLM；未注册时返回 ``None``。

    消费方应处理 ``None``（如 ``TravelIntentClassifier`` 回退到关键词分类），
    或在确实需要 LLM 时由调用方显式注入。
    """
    return _default_llm
