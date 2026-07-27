"""infrastructure/llm/fallback.py 单元测试。

覆盖 FallbackLLM 的降级链：
- complete / complete_with_tools / stream_complete / complete_json
- 各种异常路径（RateLimitError / 通用 Exception / AllProvidersFailedError）
- set_audit_context 委托到所有 provider
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest

from infrastructure.llm.fallback import (
    AllProvidersFailedError,
    FallbackLLM,
    RateLimitError,
    ServiceUnavailableError,
)
from infrastructure.llm.openai import LLMResponse


class _ProviderStub:
    """OpenAILLM 接口的最小 stub。"""

    def __init__(
        self,
        *,
        complete_side_effect=None,
        complete_return_value: str = "ok",
        complete_with_tools_side_effect=None,
        complete_with_tools_return_value=None,
        stream_chunks: list[str] | None = None,
        stream_side_effect=None,
        complete_json_side_effect=None,
        complete_json_return_value=None,
    ) -> None:
        if complete_side_effect is not None:
            self.complete = AsyncMock(side_effect=complete_side_effect)
        else:
            self.complete = AsyncMock(return_value=complete_return_value)
        if complete_with_tools_side_effect is not None:
            self.complete_with_tools = AsyncMock(side_effect=complete_with_tools_side_effect)
        else:
            self.complete_with_tools = AsyncMock(return_value=complete_with_tools_return_value)
        self._stream_chunks = stream_chunks
        self._stream_side_effect = stream_side_effect
        if complete_json_side_effect is not None:
            self.complete_json = AsyncMock(side_effect=complete_json_side_effect)
        else:
            self.complete_json = AsyncMock(return_value=complete_json_return_value or {})
        self.set_audit_context = MagicMock()

    async def stream_complete(self, *, system: str, messages: list[dict], **kwargs) -> AsyncGenerator[str, None]:
        if self._stream_side_effect is not None:
            raise self._stream_side_effect
        for chunk in self._stream_chunks or []:
            yield chunk


class TestFallbackLLMInit:
    def test_requires_at_least_one_provider(self):
        with pytest.raises(ValueError, match="至少需要"):
            FallbackLLM(providers=[])

    def test_primary_is_first_provider(self):
        p1 = _ProviderStub()
        p2 = _ProviderStub()
        fb = FallbackLLM(providers=[p1, p2])
        assert fb.providers[0] is p1
        # providers 是副本，不应暴露内部 list
        assert fb.providers is not fb._providers

    def test_set_audit_context_propagates_to_all_providers(self):
        p1 = _ProviderStub()
        p2 = _ProviderStub()
        fb = FallbackLLM(providers=[p1, p2])
        fb.set_audit_context(session_id="s1", user_id="u1", trace_id="t1")
        p1.set_audit_context.assert_called_once_with(session_id="s1", user_id="u1", trace_id="t1")
        p2.set_audit_context.assert_called_once_with(session_id="s1", user_id="u1", trace_id="t1")


class TestFallbackLLMComplete:
    @pytest.mark.asyncio
    async def test_uses_primary_on_success(self):
        p1 = _ProviderStub(complete_return_value="primary-reply")
        fb = FallbackLLM(providers=[p1])
        result = await fb.complete(system="s", messages=[{"role": "user", "content": "hi"}])
        assert result == "primary-reply"
        p1.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_falls_back_on_rate_limit(self):
        p1 = _ProviderStub(complete_side_effect=RateLimitError("rate limited"))
        p2 = _ProviderStub(complete_return_value="secondary-reply")
        fb = FallbackLLM(providers=[p1, p2])
        result = await fb.complete(system="s", messages=[])
        assert result == "secondary-reply"

    @pytest.mark.asyncio
    async def test_falls_back_on_connection_error(self):
        p1 = _ProviderStub(complete_side_effect=ConnectionError("network down"))
        p2 = _ProviderStub(complete_return_value="secondary-reply")
        fb = FallbackLLM(providers=[p1, p2])
        result = await fb.complete(system="s", messages=[])
        assert result == "secondary-reply"

    @pytest.mark.asyncio
    async def test_falls_back_on_timeout(self):
        p1 = _ProviderStub(complete_side_effect=TimeoutError("timeout"))
        p2 = _ProviderStub(complete_return_value="secondary-reply")
        fb = FallbackLLM(providers=[p1, p2])
        result = await fb.complete(system="s", messages=[])
        assert result == "secondary-reply"

    @pytest.mark.asyncio
    async def test_falls_back_on_service_unavailable(self):
        p1 = _ProviderStub(complete_side_effect=ServiceUnavailableError("503"))
        p2 = _ProviderStub(complete_return_value="secondary-reply")
        fb = FallbackLLM(providers=[p1, p2])
        result = await fb.complete(system="s", messages=[])
        assert result == "secondary-reply"

    @pytest.mark.asyncio
    async def test_unexpected_error_propagates_on_last_provider(self):
        p1 = _ProviderStub(complete_side_effect=ValueError("bad input"))
        fb = FallbackLLM(providers=[p1])
        with pytest.raises(ValueError, match="bad input"):
            await fb.complete(system="s", messages=[])

    @pytest.mark.asyncio
    async def test_unexpected_error_falls_back_when_not_last_provider(self):
        p1 = _ProviderStub(complete_side_effect=ValueError("bad input"))
        p2 = _ProviderStub(complete_return_value="secondary-reply")
        fb = FallbackLLM(providers=[p1, p2])
        result = await fb.complete(system="s", messages=[])
        assert result == "secondary-reply"

    @pytest.mark.asyncio
    async def test_all_providers_fail_raises_all_providers_failed(self):
        p1 = _ProviderStub(complete_side_effect=RateLimitError("limited"))
        p2 = _ProviderStub(complete_side_effect=ServiceUnavailableError("unavailable"))
        fb = FallbackLLM(providers=[p1, p2])
        with pytest.raises(AllProvidersFailedError):
            await fb.complete(system="s", messages=[])


class TestFallbackLLMCompleteWithTools:
    @pytest.mark.asyncio
    async def test_uses_primary_on_success(self):
        resp = LLMResponse(content="ok", tool_calls=[])
        p1 = _ProviderStub(complete_with_tools_return_value=resp)
        fb = FallbackLLM(providers=[p1])
        result = await fb.complete_with_tools(system="s", messages=[], tools=[])
        assert result is resp

    @pytest.mark.asyncio
    async def test_falls_back_on_rate_limit(self):
        resp = LLMResponse(content="ok", tool_calls=[])
        p1 = _ProviderStub(complete_with_tools_side_effect=RateLimitError("limited"))
        p2 = _ProviderStub(complete_with_tools_return_value=resp)
        fb = FallbackLLM(providers=[p1, p2])
        result = await fb.complete_with_tools(system="s", messages=[], tools=[])
        assert result is resp

    @pytest.mark.asyncio
    async def test_all_providers_fail(self):
        p1 = _ProviderStub(complete_with_tools_side_effect=RateLimitError("limited"))
        p2 = _ProviderStub(complete_with_tools_side_effect=ConnectionError("network"))
        fb = FallbackLLM(providers=[p1, p2])
        with pytest.raises(AllProvidersFailedError):
            await fb.complete_with_tools(system="s", messages=[], tools=[])


class TestFallbackLLMStreamComplete:
    @pytest.mark.asyncio
    async def test_streams_from_primary(self):
        p1 = _ProviderStub(stream_chunks=["a", "b", "c"])
        fb = FallbackLLM(providers=[p1])
        chunks = []
        async for chunk in fb.stream_complete(system="s", messages=[]):
            chunks.append(chunk)
        assert chunks == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_falls_back_on_stream_error(self):
        p1 = _ProviderStub(stream_side_effect=RateLimitError("limited"))
        p2 = _ProviderStub(stream_chunks=["fallback"])
        fb = FallbackLLM(providers=[p1, p2])
        chunks = []
        async for chunk in fb.stream_complete(system="s", messages=[]):
            chunks.append(chunk)
        assert chunks == ["fallback"]

    @pytest.mark.asyncio
    async def test_all_providers_stream_fail(self):
        p1 = _ProviderStub(stream_side_effect=RateLimitError("limited"))
        p2 = _ProviderStub(stream_side_effect=ConnectionError("network"))
        fb = FallbackLLM(providers=[p1, p2])
        with pytest.raises(AllProvidersFailedError):
            async for _ in fb.stream_complete(system="s", messages=[]):
                pass


class TestFallbackLLMCompleteJson:
    @pytest.mark.asyncio
    async def test_uses_primary_on_success(self):
        p1 = _ProviderStub(complete_json_return_value={"key": "value"})
        fb = FallbackLLM(providers=[p1])
        result = await fb.complete_json(system="s", user="u")
        assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_falls_back_on_rate_limit(self):
        p1 = _ProviderStub(complete_json_side_effect=RateLimitError("limited"))
        p2 = _ProviderStub(complete_json_return_value={"key": "fallback"})
        fb = FallbackLLM(providers=[p1, p2])
        result = await fb.complete_json(system="s", user="u")
        assert result == {"key": "fallback"}

    @pytest.mark.asyncio
    async def test_all_providers_fail_json(self):
        p1 = _ProviderStub(complete_json_side_effect=RateLimitError("limited"))
        p2 = _ProviderStub(complete_json_side_effect=TimeoutError("timeout"))
        fb = FallbackLLM(providers=[p1, p2])
        with pytest.raises(AllProvidersFailedError):
            await fb.complete_json(system="s", user="u")
