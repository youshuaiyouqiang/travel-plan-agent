"""Tests for core/reasoning.py — ReasoningEngine, TraceStep, parsing logic"""

import json

import pytest

from domain.reasoning.engine import (
    ReasoningEngine,
    TraceStep,
    AskUserNeeded,
    ConfirmationNeeded,
    _strip_code_fences,
    _extract_json_object,
)
from infrastructure.llm.openai import LLMResponse, ToolCallResult as LLMToolCall
from infrastructure.tools.registry import ToolRegistry
from infrastructure.tools.executor import ToolExecutor
from infrastructure.tools.policy import ToolPolicy
from infrastructure.tools.base import ToolSpec, bind_tool
from unittest.mock import AsyncMock


class TestTraceStep:
    def test_construction(self):
        step = TraceStep(iteration=1, decision_type="tool_calls")
        assert step.iteration == 1
        assert step.decision_type == "tool_calls"
        assert step.text == ""
        assert step.tool_calls == []
        assert step.tool_results == []
        assert step.system_note == ""


class TestAskUserNeeded:
    def test_exception_message(self):
        exc = AskUserNeeded("请问您的地址是？")
        assert exc.question == "请问您的地址是？"
        assert str(exc) == "请问您的地址是？"


class TestConfirmationNeeded:
    def test_exception_message(self):
        exc = ConfirmationNeeded("确认删除文件？")
        assert exc.prompt == "确认删除文件？"
        assert str(exc) == "确认删除文件？"


class TestStripCodeFences:
    def test_no_fences(self):
        assert _strip_code_fences("hello world") == "hello world"

    def test_with_fences(self):
        text = '```json\n{"tool_calls": []}\n```'
        result = _strip_code_fences(text)
        assert "```" not in result

    def test_fences_without_label(self):
        text = '``\n{"answer": "yes"}\n```'
        result = _strip_code_fences(text)
        assert "{" in result


class TestExtractJsonObject:
    def test_clean_json(self):
        data = _extract_json_object('{"tool_calls": [{"name": "run_shell"}], "text": "ok"}')
        assert "tool_calls" in data
        assert len(data["tool_calls"]) == 1

    def test_json_in_text(self):
        text = 'Here is my plan: {"tool_calls": [], "text": "final answer"} done.'
        data = _extract_json_object(text)
        assert data["text"] == "final answer"

    def test_invalid_raises(self):
        with pytest.raises((json.JSONDecodeError, ValueError)):
            _extract_json_object("just plain text, no json")


class TestReasoningEngine:
    def _make_engine(self):
        """Create a ReasoningEngine with mock LLM and real tools."""
        mock_llm = AsyncMock()
        registry = ToolRegistry()
        policy = ToolPolicy()

        async def _echo_handler(arguments: dict) -> dict:
            return {"content": f"echo: {arguments.get('text', '')}"}

        spec = ToolSpec(name="echo_tool", description="Echo input", category="Test")
        registry.register(bind_tool(spec, _echo_handler))

        executor = ToolExecutor(registry=registry, policy=policy)
        engine = ReasoningEngine(
            llm=mock_llm,
            tool_registry=registry,
            tool_executor=executor,
        )
        return engine, mock_llm

    @staticmethod
    def _text_to_llm_response(text: str) -> LLMResponse:
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "tool_calls" in data:
                tool_calls = [
                    LLMToolCall(
                        id=tc.get("id", f"call_{i}"),
                        name=tc["name"],
                        arguments=tc.get("arguments", {}),
                    )
                    for i, tc in enumerate(data["tool_calls"])
                ]
                return LLMResponse(
                    content=data.get("text", ""),
                    tool_calls=tool_calls,
                    has_tool_calls=True,
                )
        except (json.JSONDecodeError, ValueError):
            pass
        return LLMResponse(content=text, tool_calls=[], has_tool_calls=False)

    def _setup_mock_responses(self, mock_llm, text_responses):
        mock_llm.complete.side_effect = text_responses
        mock_llm.complete_with_tools.side_effect = [self._text_to_llm_response(t) for t in text_responses]

    @pytest.mark.asyncio
    async def test_final_answer_immediately(self):
        """LLM returns a final answer without tool calls."""
        engine, mock_llm = self._make_engine()
        self._setup_mock_responses(mock_llm, ["The answer is 42."])

        result = await engine.run(
            system_prompt="You are a helpful assistant.",
            user_message="What is 6*7?",
            force_tool=False,
        )
        assert result == "The answer is 42."
        assert len(engine.last_trace) >= 1
        assert engine.last_trace[-1].decision_type == "final_answer"

    @pytest.mark.asyncio
    async def test_tool_call_then_answer(self):
        """LLM calls a tool, then returns a final answer."""
        engine, mock_llm = self._make_engine()

        tool_call_response = json.dumps(
            {
                "tool_calls": [{"name": "echo_tool", "arguments": {"text": "hello"}}],
                "text": "Let me echo that",
            }
        )
        final_response = "The echo result is: echo: hello"

        self._setup_mock_responses(mock_llm, [tool_call_response, final_response])

        result = await engine.run(
            system_prompt="You are a helpful assistant.",
            user_message="Echo hello",
            force_tool=False,
        )
        assert "hello" in result
        assert len(engine.last_trace) >= 2

    @pytest.mark.asyncio
    async def test_force_tool_retry(self):
        """When force_tool=True and LLM gives final answer without tools,
        engine should retry to force tool usage."""
        engine, mock_llm = self._make_engine()

        self._setup_mock_responses(
            mock_llm,
            [
                "Just a short answer.",
                "Still no tool used but longer grounded answer.",
                "Final accepted answer after forced retries.",
            ],
        )

        result = await engine.run(
            system_prompt="You are a helpful assistant.",
            user_message="Do something",
            force_tool=True,
        )
        assert result
        assert len(engine.last_trace) >= 2

    @pytest.mark.asyncio
    async def test_ask_user_needed_raises(self):
        """When tool result has ask_user=True, AskUserNeeded should be raised."""
        engine, mock_llm = self._make_engine()

        async def _ask_handler(arguments: dict) -> dict:
            return {"content": "What is your name?", "ask_user": True, "question": "What is your name?"}

        ask_spec = ToolSpec(name="ask_user_tool", description="Ask user", category="Ask User")
        engine._tool_registry.register(bind_tool(ask_spec, _ask_handler))

        tool_call_response = json.dumps(
            {
                "tool_calls": [{"name": "ask_user_tool", "arguments": {"question": "name?"}}],
                "text": "Need more info",
            }
        )
        self._setup_mock_responses(mock_llm, [tool_call_response])

        with pytest.raises(AskUserNeeded) as exc_info:
            await engine.run(
                system_prompt="You are a helpful assistant.",
                user_message="Help me",
                force_tool=False,
            )
        assert "What is your name?" in exc_info.value.question

    @pytest.mark.asyncio
    async def test_confirmation_needed_raises(self):
        """When tool result has requires_confirmation=True, ConfirmationNeeded should be raised."""
        engine, mock_llm = self._make_engine()

        async def _risky_handler(arguments: dict) -> dict:
            return {"content": "Command output"}

        risky_spec = ToolSpec(name="run_shell", description="Run shell", category="Shell")
        engine._tool_registry.register(bind_tool(risky_spec, _risky_handler))

        tool_call_response = json.dumps(
            {
                "tool_calls": [{"name": "run_shell", "arguments": {"command": "rm test.txt"}}],
                "text": "Will delete file",
            }
        )
        self._setup_mock_responses(mock_llm, [tool_call_response])

        with pytest.raises(ConfirmationNeeded) as exc_info:
            await engine.run(
                system_prompt="You are a helpful assistant.",
                user_message="Delete a file",
                force_tool=False,
            )
        assert "risky" in exc_info.value.prompt.lower() or "confirmation" in exc_info.value.prompt.lower()

    @pytest.mark.asyncio
    async def test_duplicate_tool_detection(self):
        """When the same tool call pattern is repeated 3+ times, engine should detect it."""
        engine, mock_llm = self._make_engine()

        same_call = json.dumps(
            {
                "tool_calls": [{"name": "echo_tool", "arguments": {"text": "same"}}],
                "text": "Trying again",
            }
        )
        self._setup_mock_responses(mock_llm, [same_call, same_call, same_call, "Final answer after duplicates"])

        result = await engine.run(
            system_prompt="You are a helpful assistant.",
            user_message="Echo same",
            force_tool=False,
        )
        duplicate_notes = [step for step in engine.last_trace if "duplicate" in step.system_note]
        assert len(duplicate_notes) >= 1

    @pytest.mark.asyncio
    async def test_max_iterations_limit(self):
        """When max iterations is reached, should return a stop message."""
        engine, mock_llm = self._make_engine()

        responses = [
            json.dumps(
                {
                    "tool_calls": [{"name": "echo_tool", "arguments": {"text": f"call {i}"}}],
                    "text": "Keep going",
                }
            )
            for i in range(20)
        ]
        self._setup_mock_responses(mock_llm, responses)

        result = await engine.run(
            system_prompt="You are a helpful assistant.",
            user_message="Keep calling tools",
            force_tool=False,
        )
        assert "Stopped" in result or "maximum" in result.lower()

    @pytest.mark.asyncio
    async def test_run_tool_failure_continues(self):
        """P6 前置：工具执行失败时，引擎应将错误结果反馈给 LLM 并继续推理。"""
        engine, mock_llm = self._make_engine()

        async def _failing_handler(arguments: dict) -> dict:
            raise RuntimeError("simulated tool failure")

        fail_spec = ToolSpec(name="failing_tool", description="Always fails", category="Test")
        engine._tool_registry.register(bind_tool(fail_spec, _failing_handler))

        tool_call_response = json.dumps(
            {
                "tool_calls": [{"name": "failing_tool", "arguments": {"text": "go"}}],
                "text": "Let me try this tool",
            }
        )
        final_response = "The tool failed, but here is my best answer based on what I know."
        self._setup_mock_responses(mock_llm, [tool_call_response, final_response])

        result = await engine.run(
            system_prompt="You are a helpful assistant.",
            user_message="Use the failing tool",
            force_tool=False,
        )
        assert "best answer" in result
        # 工具失败结果应记录在 trace 中
        tool_traces = [t for t in engine.last_trace if t.tool_results]
        assert len(tool_traces) >= 1
        assert any(r.get("is_error") for r in tool_traces[-1].tool_results)

    @pytest.mark.asyncio
    async def test_run_invalid_decision_falls_back_to_final_answer(self):
        """P6 前置：LLM 输出无法解析为工具调用时，应回退为最终答案。"""
        engine, mock_llm = self._make_engine()

        # 既不是合法 JSON，也不包含可识别的 tool_call 模式
        garbage_response = "This is just plain text with no structure whatsoever."
        self._setup_mock_responses(mock_llm, [garbage_response])

        result = await engine.run(
            system_prompt="You are a helpful assistant.",
            user_message="Tell me something",
            force_tool=False,
        )
        assert "plain text" in result or "structure" in result
        assert engine.last_trace[-1].decision_type == "final_answer"

    @pytest.mark.asyncio
    async def test_run_stream_final_answer_immediately(self):
        """P6 前置：run_stream 在无工具调用时应流式输出最终答案。"""
        engine, mock_llm = self._make_engine()
        self._setup_mock_responses(mock_llm, ["The streaming answer is 42."])

        # stream_complete 需要 mock
        async def _fake_stream(*, system: str, messages: list):
            for chunk in ["The ", "streaming ", "answer ", "is ", "42."]:
                yield chunk

        mock_llm.stream_complete = _fake_stream

        chunks: list[str] = []
        async for chunk in engine.run_stream(
            system_prompt="You are a helpful assistant.",
            user_message="What is the answer?",
            force_tool=False,
        ):
            if not chunk.startswith("__status__:"):
                chunks.append(chunk)

        result = "".join(chunks)
        assert "42" in result

    @pytest.mark.asyncio
    async def test_run_stream_tool_call_then_answer(self):
        """P6 前置：run_stream 在工具调用后应输出最终答案。"""
        engine, mock_llm = self._make_engine()

        tool_call_response = json.dumps(
            {
                "tool_calls": [{"name": "echo_tool", "arguments": {"text": "stream"}}],
                "text": "Calling echo",
            }
        )
        final_response = "Echo result: echo: stream"
        self._setup_mock_responses(mock_llm, [tool_call_response, final_response])

        chunks: list[str] = []
        statuses: list[str] = []
        async for chunk in engine.run_stream(
            system_prompt="You are a helpful assistant.",
            user_message="Echo stream",
            force_tool=False,
        ):
            if chunk.startswith("__status__:"):
                statuses.append(chunk)
            else:
                chunks.append(chunk)

        result = "".join(chunks)
        assert "echo: stream" in result
        # 应该有工具状态通知
        assert any("echo_tool" in s or "thinking" in s for s in statuses)

    @pytest.mark.asyncio
    async def test_run_stream_cancellation(self):
        """P6 前置：run_stream 应支持消费者提前取消（GeneratorExit 不抛出未处理异常）。"""
        engine, mock_llm = self._make_engine()
        self._setup_mock_responses(mock_llm, ["A long final answer that should be streamed."])

        async def _fake_stream(*, system: str, messages: list):
            for chunk in ["chunk1", "chunk2", "chunk3", "chunk4", "chunk5"]:
                yield chunk

        mock_llm.stream_complete = _fake_stream

        gen = engine.run_stream(
            system_prompt="You are a helpful assistant.",
            user_message="Stream something",
            force_tool=False,
        )
        # 消费少量 chunk 后提前退出，触发 GeneratorExit
        consumed: list[str] = []
        async for chunk in gen:
            if not chunk.startswith("__status__:"):
                consumed.append(chunk)
            if len(consumed) >= 2:
                break
        # 验证没有未处理异常，且消费了部分输出
        assert len(consumed) >= 1
