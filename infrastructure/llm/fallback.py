"""LLM Provider 降级链 — 多 provider 自动 fallback。

社区版实用性：用户可能在各种网络环境下用，API 偶尔不可用，降级能提升可用性。
"""

from __future__ import annotations

import logging
from typing import Any

from infrastructure.llm.openai import OpenAILLM, LLMResponse

logger = logging.getLogger(__name__)


class RateLimitError(Exception):
    """LLM Provider 限流异常。"""

    pass


class ServiceUnavailableError(Exception):
    """LLM Provider 服务不可用异常。"""

    pass


class AllProvidersFailedError(Exception):
    """所有 LLM provider 均不可用。"""

    pass


class FallbackLLM:
    """多 LLM provider 降级链。

    按优先级顺序尝试，上一个 provider 失败时自动切换到下一个。

    用法：
        fallback = FallbackLLM([
            OpenAILLM(base_url="https://api.openai.com/v1", api_key=...),
            OpenAILLM(base_url="https://api.azure.com/...", api_key=...),
        ])
        response = await fallback.complete_with_tools(system=..., messages=..., tools=...)
    """

    def __init__(self, providers: list[OpenAILLM]) -> None:
        if not providers:
            raise ValueError("至少需要一个 LLM provider")
        self._providers = providers
        self._primary = providers[0]
        logger.info("FallbackLLM initialized with %d providers", len(providers))

    @property
    def providers(self) -> list[OpenAILLM]:
        return list(self._providers)

    async def complete(self, *, system: str, messages: list[dict], **kwargs) -> str:
        """同步 completion，带降级。"""
        for i, provider in enumerate(self._providers):
            try:
                return await provider.complete(system=system, messages=messages, **kwargs)
            except (RateLimitError, ServiceUnavailableError, ConnectionError, TimeoutError) as e:
                logger.warning("LLM provider #%d failed: %s, trying next...", i + 1, e)
                continue
            except Exception as e:
                if i == len(self._providers) - 1:
                    raise
                logger.warning("LLM provider #%d failed (unexpected): %s, trying next...", i + 1, e)
                continue
        raise AllProvidersFailedError("所有 LLM provider 均不可用")

    async def complete_with_tools(
        self, *, system: str, messages: list[dict], tools: list[dict] | None = None, **kwargs
    ) -> LLMResponse:
        """带工具的 completion，带降级。"""
        for i, provider in enumerate(self._providers):
            try:
                return await provider.complete_with_tools(
                    system=system,
                    messages=messages,
                    tools=tools,
                    **kwargs,
                )
            except (RateLimitError, ServiceUnavailableError, ConnectionError, TimeoutError) as e:
                logger.warning("LLM provider #%d failed (tools): %s, trying next...", i + 1, e)
                continue
            except Exception as e:
                if i == len(self._providers) - 1:
                    raise
                logger.warning("LLM provider #%d failed (tools, unexpected): %s, trying next...", i + 1, e)
                continue
        raise AllProvidersFailedError("所有 LLM provider 均不可用")

    async def stream_complete(self, *, system: str, messages: list[dict], **kwargs) -> Any:
        """流式 completion，带降级（流式失败回退到非流式）。"""
        for i, provider in enumerate(self._providers):
            try:
                async for chunk in provider.stream_complete(system=system, messages=messages, **kwargs):
                    yield chunk
                return
            except (RateLimitError, ServiceUnavailableError, ConnectionError, TimeoutError) as e:
                logger.warning("LLM provider #%d stream failed: %s, trying next...", i + 1, e)
                continue
            except Exception as e:
                if i == len(self._providers) - 1:
                    raise
                logger.warning("LLM provider #%d stream failed: %s, trying next...", i + 1, e)
                continue
        raise AllProvidersFailedError("所有 LLM provider 均不可用")

    async def complete_json(self, *, system: str, user: str) -> dict[str, Any]:
        """JSON completion，带降级。

        P1-15：补齐该方法以覆盖 OpenAILLM 全部接口，
        被 memory_extractor / memory_distiller / itinerary.parser 调用。
        审计日志与 JSON 容错解析由各 provider.complete_json 自身处理，
        此处只负责按 provider 顺序降级。
        """
        for i, provider in enumerate(self._providers):
            try:
                return await provider.complete_json(system=system, user=user)
            except (RateLimitError, ServiceUnavailableError, ConnectionError, TimeoutError) as e:
                logger.warning("LLM provider #%d failed (json): %s, trying next...", i + 1, e)
                continue
            except Exception as e:
                if i == len(self._providers) - 1:
                    raise
                logger.warning("LLM provider #%d failed (json, unexpected): %s, trying next...", i + 1, e)
                continue
        raise AllProvidersFailedError("所有 LLM provider 均不可用")

    def set_audit_context(self, *, session_id: str, user_id: str, trace_id: str = "") -> None:
        """设置审计上下文到所有 provider。"""
        for provider in self._providers:
            provider.set_audit_context(session_id=session_id, user_id=user_id, trace_id=trace_id)
