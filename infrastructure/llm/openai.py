from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI

from config import settings
from domain.shared.audit.context import AuditContext

logger = logging.getLogger(__name__)


@dataclass
class ToolCallResult:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    content: str = ""
    tool_calls: list[ToolCallResult] = field(default_factory=list)
    has_tool_calls: bool = False


class OpenAILLM:
    def __init__(
        self,
        audit_logger: Any = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        # P1-15：允许注入 api_key/base_url/model，用于构建 FallbackLLM 的备用 provider；
        # 不传则从 settings 读取（保持向后兼容）。
        resolved_key = api_key or settings.api_key or os.getenv(key="DASHSCOPE_API_KEY", default="")
        resolved_base = base_url or settings.base_url
        self._client = AsyncOpenAI(api_key=resolved_key, base_url=resolved_base)
        self.model: str = model or settings.model
        self._audit_logger = audit_logger

    def set_audit_context(self, *, session_id: str, user_id: str, trace_id: str = "") -> None:
        # P0-5：用 ContextVar 替代实例属性，确保 OpenAILLM 单例下并发请求审计上下文隔离
        AuditContext.set(session_id=session_id, user_id=user_id, trace_id=trace_id)

    async def complete(self, *, system: str, messages: list[dict[str, Any]]) -> str:
        start = time.monotonic()
        response = await self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, *messages],
        )
        content = response.choices[0].message.content or ""
        duration_ms = int((time.monotonic() - start) * 1000)

        if self._audit_logger:
            self._audit_logger.log_llm_call(
                session_id=AuditContext.get().session_id,
                user_id=AuditContext.get().user_id,
                trace_id=AuditContext.get().trace_id,
                model=self.model,
                system_prompt=system,
                messages=messages,
                response=content,
                duration_ms=duration_ms,
                tool_calls_mode=False,
            )

        return content

    async def stream_complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
    ) -> AsyncGenerator[str, None]:
        """流式输出，逐 token yield 文本片段。"""
        start = time.monotonic()
        full_content = ""
        stream = await self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, *messages],
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                full_content += delta.content
                yield delta.content
        duration_ms = int((time.monotonic() - start) * 1000)
        if self._audit_logger:
            self._audit_logger.log_llm_call(
                session_id=AuditContext.get().session_id,
                user_id=AuditContext.get().user_id,
                trace_id=AuditContext.get().trace_id,
                model=self.model,
                system_prompt=system,
                messages=messages,
                response=full_content,
                duration_ms=duration_ms,
                tool_calls_mode=False,
            )

    async def complete_with_tools(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        start = time.monotonic()
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, *messages],
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            response = await self._client.chat.completions.create(**kwargs)
        except Exception as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.warning("Native tool calling failed, falling back to text mode: %s", e)
            content = await self.complete(system=system, messages=messages)
            if self._audit_logger:
                self._audit_logger.log_llm_call(
                    session_id=AuditContext.get().session_id,
                    user_id=AuditContext.get().user_id,
                    trace_id=AuditContext.get().trace_id,
                    model=self.model,
                    system_prompt=system,
                    messages=messages,
                    response=f"[FALLBACK] {content}",
                    duration_ms=duration_ms,
                    tool_calls_mode=True,
                )
            return LLMResponse(content=content, tool_calls=[], has_tool_calls=False)

        choice = response.choices[0]
        message = choice.message
        content = message.content or ""
        duration_ms = int((time.monotonic() - start) * 1000)

        native_tool_calls = getattr(message, "tool_calls", None)

        if self._audit_logger:
            raw_output = content
            if native_tool_calls:
                tc_data = [
                    {"id": tc.id, "name": tc.function.name, "arguments": tc.function.arguments}
                    for tc in native_tool_calls
                ]
                raw_output = json.dumps({"content": content, "tool_calls": tc_data}, ensure_ascii=False)
            self._audit_logger.log_llm_call(
                session_id=AuditContext.get().session_id,
                user_id=AuditContext.get().user_id,
                trace_id=AuditContext.get().trace_id,
                model=self.model,
                system_prompt=system,
                messages=messages,
                response=raw_output,
                duration_ms=duration_ms,
                tool_calls_mode=True,
            )

        if not native_tool_calls:
            return LLMResponse(content=content, tool_calls=[], has_tool_calls=False)

        parsed_calls: list[ToolCallResult] = []
        for tc in native_tool_calls:
            try:
                args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            except (json.JSONDecodeError, ValueError):
                args = {}
            parsed_calls.append(ToolCallResult(id=tc.id, name=tc.function.name, arguments=args))

        return LLMResponse(
            content=content,
            tool_calls=parsed_calls,
            has_tool_calls=True,
        )

    async def complete_json(self, *, system: str, user: str) -> dict[str, Any]:
        start = time.monotonic()
        text: str = await self.complete(system=system, messages=[{"role": "user", "content": user}])
        duration_ms = int((time.monotonic() - start) * 1000)

        if self._audit_logger:
            self._audit_logger.log_llm_call(
                session_id=AuditContext.get().session_id,
                user_id=AuditContext.get().user_id,
                trace_id=AuditContext.get().trace_id,
                model=self.model,
                system_prompt=system,
                messages=[{"role": "user", "content": user}],
                response=text,
                duration_ms=duration_ms,
                tool_calls_mode=False,
            )

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start_idx = text.find("{")
            end = text.rfind("}")
            if start_idx != -1 and end != -1:
                try:
                    return json.loads(text[start_idx : end + 1])
                except json.JSONDecodeError:
                    pass
            return {}
