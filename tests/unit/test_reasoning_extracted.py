"""P6.5 单元测试：覆盖从 engine.py 提取到 json_extract / text_cleaning / decision_parser 的纯函数。

验收要求：
- 新纯函数单测覆盖有效与畸形输入；
- 行为测试覆盖主分支（在 test_reasoning.py 中）；
- engine.py 少于 600 行。
"""

from __future__ import annotations

import json

import pytest

from domain.reasoning.json_extract import (
    extract_json_by_brackets,
    extract_json_object,
    strip_code_fences,
    try_fix_json,
)
from domain.reasoning.text_cleaning import (
    clean_final_answer,
    looks_grounded,
    strip_reasoning_prefix,
    strip_tool_calls_from_text,
)
from domain.reasoning.decision_parser import (
    DecisionParser,
    make_signature,
    parse_kwargs,
)
from domain.shared.llm.ports import LLMResponse, ToolCallResult
from domain.shared.types import Decision, DecisionType, ToolCall
from domain.reasoning.message_builder import (
    MAX_HISTORY_TURNS,
    append_tool_result_messages,
    build_working_messages,
)
from infrastructure.tools.registry import ToolRegistry
from infrastructure.tools.executor import ToolExecutor
from infrastructure.tools.policy import ToolPolicy
from infrastructure.tools.base import ToolSpec, bind_tool


# ── json_extract ──────────────────────────────────────────────────────────


class TestStripCodeFences:
    def test_plain_text(self):
        assert strip_code_fences("hello") == "hello"

    def test_json_fence(self):
        assert strip_code_fences("```json\n{\"a\": 1}\n```") == '{"a": 1}'

    def test_bare_fence(self):
        assert "content" in strip_code_fences("```\ncontent\n```")

    def test_empty(self):
        assert strip_code_fences("") == ""


class TestExtractJsonByBrackets:
    def test_clean_object(self):
        assert extract_json_by_brackets('{"a": 1}') == '{"a": 1}'

    def test_embedded_object(self):
        result = extract_json_by_brackets('prefix {"a": 1} suffix')
        assert result == '{"a": 1}'

    def test_nested_object(self):
        text = '{"a": {"b": {"c": 1}}}'
        assert extract_json_by_brackets(text) == text

    def test_string_with_braces(self):
        text = '{"a": "val{ue}"}'
        assert extract_json_by_brackets(text) == text

    def test_no_object(self):
        assert extract_json_by_brackets("no json here") is None

    def test_unclosed(self):
        assert extract_json_by_brackets('{"a": 1') is None


class TestExtractJsonObject:
    def test_clean(self):
        data = extract_json_object('{"tool_calls": [], "text": "ok"}')
        assert data["text"] == "ok"

    def test_with_fences(self):
        data = extract_json_object('```json\n{"x": 1}\n```')
        assert data["x"] == 1

    def test_embedded(self):
        data = extract_json_object('Here: {"x": 2} done')
        assert data["x"] == 2

    def test_non_dict_raises(self):
        with pytest.raises(ValueError):
            extract_json_object("[1, 2, 3]")

    def test_invalid_raises(self):
        with pytest.raises((json.JSONDecodeError, ValueError)):
            extract_json_object("plain text")


class TestTryFixJson:
    def test_valid_json(self):
        assert try_fix_json('{"a": 1}') == '{"a": 1}'

    def test_truncated_object(self):
        fixed = try_fix_json('{"a": 1')
        assert fixed is not None
        assert json.loads(fixed) == {"a": 1}

    def test_truncated_nested(self):
        fixed = try_fix_json('{"a": {"b": 1')
        assert fixed is not None
        data = json.loads(fixed)
        assert data["a"]["b"] == 1

    def test_unclosed_string(self):
        fixed = try_fix_json('{"a": "hel')
        assert fixed is not None
        data = json.loads(fixed)
        assert data["a"] == "hel"

    def test_empty(self):
        assert try_fix_json("") is None

    def test_none_input(self):
        assert try_fix_json("") is None


# ── text_cleaning ─────────────────────────────────────────────────────────


class TestLooksGrounded:
    def test_short_text(self):
        assert looks_grounded("short") is False

    def test_weak_pattern(self):
        assert looks_grounded("done") is False
        assert looks_grounded("ok") is False
        assert looks_grounded("task complete") is False

    def test_normal_answer(self):
        assert looks_grounded("This is a detailed answer with enough content.") is True

    def test_confirmation_only(self):
        assert looks_grounded("您对这个行程满意吗") is False

    def test_confirmation_with_content(self):
        text = "第1天：到达北京。您对这个行程满意吗？"
        assert looks_grounded(text) is True


class TestStripReasoningPrefix:
    def test_no_prefix(self):
        assert strip_reasoning_prefix("Hello\nWorld") == "Hello\nWorld"

    def test_key_findings_pattern_matches(self):
        # "Key findings:" 模式没有 (?=\n) 前瞻，逐行匹配时能命中
        text = "Key findings:\nDetails here"
        result = strip_reasoning_prefix(text)
        assert "Key findings" not in result
        assert "Details here" in result

    def test_now_pattern_requires_newline_lookahead(self):
        # 既有行为：含 (?=\n) 的模式在逐行处理时不会命中（行内无 \n）。
        # 这是原始 engine.py 的行为，P6 拆分保持不变。
        text = "Now I have enough information to answer.\nThe answer is 42."
        result = strip_reasoning_prefix(text)
        # 由于 (?=\n) 前瞻在单行中不满足，该行不被剔除
        assert "Now I have enough" in result

    def test_preserves_normal_lines(self):
        text = "Line 1\nLine 2\nLine 3"
        assert strip_reasoning_prefix(text) == "Line 1\nLine 2\nLine 3"


class TestCleanFinalAnswer:
    def test_plain_text(self):
        assert clean_final_answer("Hello world") == "Hello world"

    def test_removes_code_fences(self):
        result = clean_final_answer('```json\n{"text": "answer"}\n```')
        assert result == "answer"

    def test_extracts_text_from_tool_calls_json(self):
        text = json.dumps({"tool_calls": [{"name": "x"}], "text": "real answer"})
        assert clean_final_answer(text) == "real answer"

    def test_removes_tool_calls_fragments(self):
        text = 'Before {"tool_calls": [{"name": "x"}]} After'
        result = clean_final_answer(text)
        assert "tool_calls" not in result
        assert "Before" in result or "After" in result

    def test_removes_xml_tags(self):
        text = "Before <tool_call>something</tool_call> After"
        result = clean_final_answer(text)
        assert "<tool_call" not in result

    def test_empty_tool_calls_text(self):
        text = json.dumps({"tool_calls": [{"name": "x"}], "text": ""})
        result = clean_final_answer(text)
        assert "tool_calls" not in result


class TestStripToolCallsFromText:
    def test_plain_text(self):
        assert strip_tool_calls_from_text("Hello") == "Hello"

    def test_removes_tool_calls_json(self):
        text = '{"tool_calls": [{"name": "x"}], "text": "answer"}'
        result = strip_tool_calls_from_text(text)
        assert "tool_calls" not in result


# ── decision_parser ───────────────────────────────────────────────────────


class TestMakeSignature:
    def test_basic(self):
        call = ToolCall(name="search", arguments={"q": "test"}, call_id="1")
        sig = make_signature(call)
        assert sig.startswith("search:")
        assert "test" in sig

    def test_order_independent(self):
        call1 = ToolCall(name="x", arguments={"a": 1, "b": 2}, call_id="1")
        call2 = ToolCall(name="x", arguments={"b": 2, "a": 1}, call_id="2")
        assert make_signature(call1) == make_signature(call2)

    def test_non_serializable_args(self):
        call = ToolCall(name="x", arguments={"obj": object()}, call_id="1")
        sig = make_signature(call)
        assert sig.startswith("x:")


class TestParseKwargs:
    def test_double_quotes(self):
        result = parse_kwargs('key="value"')
        assert result == {"key": "value"}

    def test_single_quotes(self):
        result = parse_kwargs("key='value'")
        assert result == {"key": "value"}

    def test_multiple(self):
        result = parse_kwargs('a="1" b="2" c=\'3\'')
        assert result == {"a": "1", "b": "2", "c": "3"}

    def test_double_overrides_single(self):
        result = parse_kwargs('key="double" key=\'single\'')
        assert result == {"key": "double"}

    def test_empty(self):
        assert parse_kwargs("") == {}


class TestDecisionParser:
    """DecisionParser 的集成测试，覆盖 parse_decision 和 llm_response_to_decision。"""

    def _make_parser(self) -> DecisionParser:
        registry = ToolRegistry()
        policy = ToolPolicy()

        async def _echo(arguments: dict) -> dict:
            return {"content": "ok"}

        spec = ToolSpec(name="echo_tool", description="Echo", category="Test")
        registry.register(bind_tool(spec, _echo))
        executor = ToolExecutor(registry=registry, policy=policy)
        return DecisionParser(tool_registry=registry, tool_executor=executor)

    # ── llm_response_to_decision ──

    def test_llm_response_with_native_tool_calls(self):
        parser = self._make_parser()
        resp = LLMResponse(
            content="calling tool",
            tool_calls=[ToolCallResult(id="c1", name="echo_tool", arguments={"text": "hi"})],
            has_tool_calls=True,
        )
        decision = parser.llm_response_to_decision(resp)
        assert decision.decision_type == DecisionType.TOOL_CALLS
        assert len(decision.tool_calls) == 1
        assert decision.tool_calls[0].name == "echo_tool"

    def test_llm_response_final_answer(self):
        parser = self._make_parser()
        resp = LLMResponse(content="The answer is 42.", tool_calls=[], has_tool_calls=False)
        decision = parser.llm_response_to_decision(resp)
        assert decision.decision_type == DecisionType.FINAL_ANSWER
        assert "42" in decision.text

    def test_llm_response_empty(self):
        parser = self._make_parser()
        resp = LLMResponse(content="", tool_calls=[], has_tool_calls=False)
        decision = parser.llm_response_to_decision(resp)
        assert decision.decision_type == DecisionType.FINAL_ANSWER
        assert decision.text == ""

    def test_llm_response_text_with_tool_calls_json(self):
        parser = self._make_parser()
        content = json.dumps({
            "tool_calls": [{"name": "echo_tool", "arguments": {"text": "hi"}}],
            "text": "calling",
        })
        resp = LLMResponse(content=content, tool_calls=[], has_tool_calls=False)
        decision = parser.llm_response_to_decision(resp)
        assert decision.decision_type == DecisionType.TOOL_CALLS
        assert len(decision.tool_calls) == 1

    # ── parse_decision ──

    def test_parse_decision_json_tool_calls(self):
        parser = self._make_parser()
        text = json.dumps({
            "tool_calls": [{"name": "echo_tool", "arguments": {"text": "hi"}}],
            "text": "note",
        })
        decision = parser.parse_decision(text)
        assert decision.decision_type == DecisionType.TOOL_CALLS
        assert len(decision.tool_calls) == 1
        assert decision.tool_calls[0].name == "echo_tool"

    def test_parse_decision_json_final_answer(self):
        parser = self._make_parser()
        text = json.dumps({"text": "final answer"})
        decision = parser.parse_decision(text)
        assert decision.decision_type == DecisionType.FINAL_ANSWER
        assert "final answer" in decision.text

    def test_parse_decision_plain_text(self):
        parser = self._make_parser()
        decision = parser.parse_decision("just plain text answer")
        assert decision.decision_type == DecisionType.FINAL_ANSWER
        assert "plain text" in decision.text

    def test_parse_decision_xml_tool_calls(self):
        parser = self._make_parser()
        text = '<tool_call>echo_tool(text="hi")</tool_call>'
        decision = parser.parse_decision(text)
        assert decision.decision_type == DecisionType.TOOL_CALLS
        assert len(decision.tool_calls) == 1
        assert decision.tool_calls[0].name == "echo_tool"

    def test_parse_decision_xml_unknown_tool_with_prefix(self):
        parser = self._make_parser()
        text = '<tool_call>fliggy_search_flight(from="PEK", to="SHA")</tool_call>'
        decision = parser.parse_decision(text)
        assert decision.decision_type == DecisionType.TOOL_CALLS
        assert decision.tool_calls[0].name == "fliggy_search_flight"

    def test_parse_decision_xml_unknown_tool_no_prefix(self):
        parser = self._make_parser()
        text = '<tool_call>unknown_tool(x="y")</tool_call>'
        decision = parser.parse_decision(text)
        # 未知工具且无前缀 → 不作为工具调用，回退为最终答案
        assert decision.decision_type == DecisionType.FINAL_ANSWER

    def test_parse_decision_regex_tool_calls(self):
        parser = self._make_parser()
        text = '{"tool_calls": [{"name": "echo_tool", "arguments": {"text": "hi"}}]}'
        decision = parser.parse_decision(text)
        assert decision.decision_type == DecisionType.TOOL_CALLS
        assert decision.tool_calls[0].name == "echo_tool"

    def test_parse_decision_loose_truncated_json_falls_back_to_final_answer(self):
        """截断的 JSON 无法被 extract_json_by_brackets 提取（括号不平衡），
        松散解析返回 None，最终回退为 FINAL_ANSWER。这是既有行为。"""
        parser = self._make_parser()
        text = '{"tool_calls": [{"name": "echo_tool", "arguments": {"text": "hi"'
        decision = parser.parse_decision(text)
        assert decision.decision_type == DecisionType.FINAL_ANSWER

    def test_parse_decision_empty_string(self):
        parser = self._make_parser()
        decision = parser.parse_decision("")
        assert decision.decision_type == DecisionType.FINAL_ANSWER

    # ── try_parse_tool_calls_from_text ──

    def test_try_parse_valid_tool_calls(self):
        parser = self._make_parser()
        text = json.dumps({"tool_calls": [{"name": "echo_tool", "arguments": {"x": 1}}]})
        result = parser.try_parse_tool_calls_from_text(text)
        assert result is not None
        assert len(result) == 1
        assert result[0].name == "echo_tool"

    def test_try_parse_unknown_tool_returns_none(self):
        parser = self._make_parser()
        text = json.dumps({"tool_calls": [{"name": "nonexistent_tool", "arguments": {}}]})
        result = parser.try_parse_tool_calls_from_text(text)
        # 已知工具列表非空且工具名不在列表中 → None
        assert result is None

    def test_try_parse_no_tool_calls_key(self):
        parser = self._make_parser()
        result = parser.try_parse_tool_calls_from_text('{"text": "answer"}')
        assert result is None

    def test_try_parse_empty_text(self):
        parser = self._make_parser()
        assert parser.try_parse_tool_calls_from_text("") is None

    def test_try_parse_no_keyword(self):
        parser = self._make_parser()
        assert parser.try_parse_tool_calls_from_text("just plain text") is None


# ── message_builder ──────────────────────────────────────────────────────


class TestBuildWorkingMessages:
    def test_no_history_returns_only_user(self):
        result = build_working_messages("hi")
        assert result == [{"role": "user", "content": "hi"}]

    def test_keeps_user_assistant_only(self):
        history = [
            {"role": "system", "content": "ignored"},
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "reply"},
            {"role": "tool", "content": "tool output ignored"},
        ]
        result = build_working_messages("second", history)
        assert result == [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "reply"},
            {"role": "user", "content": "second"},
        ]

    def test_drops_empty_content(self):
        history = [
            {"role": "user", "content": ""},
            {"role": "assistant", "content": "ok"},
        ]
        result = build_working_messages("now", history)
        assert result == [
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "now"},
        ]

    def test_truncates_to_max_history_turns(self):
        history = [
            {"role": "user", "content": f"u{i}"}
            for i in range(MAX_HISTORY_TURNS + 4)
        ]
        result = build_working_messages("latest", history)
        # 只保留最近 MAX_HISTORY_TURNS 条历史 + 当前 user 消息
        assert len(result) == MAX_HISTORY_TURNS + 1
        assert result[0]["content"] == f"u{4}"
        assert result[-1] == {"role": "user", "content": "latest"}

    def test_none_history_treated_as_empty(self):
        result = build_working_messages("hello", None)
        assert result == [{"role": "user", "content": "hello"}]


class TestAppendToolResultMessagesNative:
    def test_native_mode_appends_assistant_tool_calls_and_tool_messages(self):
        decision = _make_decision(
            text="let me check",
            tool_calls=[ToolCall(name="search", arguments={"q": "x"}, call_id="call_1")],
        )
        tool_results = [{"content": "found it", "is_error": False}]
        trace_calls = [{"name": "search", "arguments": {"q": "x"}, "id": "call_1"}]
        working: list[dict] = []

        append_tool_result_messages(
            working, decision, tool_results, trace_calls, decision.text, use_native=True
        )

        assert working[0]["role"] == "assistant"
        assert working[0]["tool_calls"][0]["function"]["name"] == "search"
        assert working[0]["content"] == "let me check"
        assert working[1] == {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": "found it",
        }
        assert working[2]["role"] == "user"
        assert "plain-text final answer" in working[2]["content"]

    def test_native_mode_truncates_tool_content_to_4000_chars(self):
        long_content = "x" * 8000
        decision = _make_decision(
            text="",
            tool_calls=[ToolCall(name="big", arguments={}, call_id="c1")],
        )
        working: list[dict] = []

        append_tool_result_messages(
            working,
            decision,
            [{"content": long_content, "is_error": False}],
            [],
            "",
            use_native=True,
        )

        assert working[1]["content"] == "x" * 4000

    def test_native_mode_serializes_dict_content_to_json(self):
        decision = _make_decision(
            text="",
            tool_calls=[ToolCall(name="lookup", arguments={}, call_id="c1")],
        )
        working: list[dict] = []

        append_tool_result_messages(
            working,
            decision,
            [{"content": {"key": "value"}, "is_error": False}],
            [],
            "",
            use_native=True,
        )

        assert json.loads(working[1]["content"]) == {"key": "value"}


class TestAppendToolResultMessagesNonNative:
    def test_non_native_appends_assistant_payload_and_summaries(self):
        decision = _make_decision(
            text="hello",
            tool_calls=[ToolCall(name="search", arguments={"q": "x"}, call_id="c1")],
        )
        tool_results = [
            {"name": "search", "content": "first result", "is_error": False},
            {"name": "lookup", "content": "boom", "is_error": True},
        ]
        trace_calls = [{"name": "search", "arguments": {"q": "x"}, "id": "c1"}]
        working: list[dict] = []

        append_tool_result_messages(
            working,
            decision,
            tool_results,
            trace_calls,
            decision.text,
            use_native=False,
            include_error_conditional=True,
        )

        # assistant payload
        payload = json.loads(working[0]["content"])
        assert payload == {
            "tool_calls": trace_calls,
            "text": "hello",
        }
        # tool results summary
        assert "[search] OK: first result" in working[1]["content"]
        assert "[lookup] ERROR: boom" in working[1]["content"]
        # error branch: 第三条消息存在并提示错误
        assert any("errors, missing data" in m["content"] for m in working[2:])

    def test_non_native_success_branch_uses_continue_prompt(self):
        decision = _make_decision(
            text="",
            tool_calls=[ToolCall(name="search", arguments={}, call_id="c1")],
        )
        working: list[dict] = []

        append_tool_result_messages(
            working,
            decision,
            [{"name": "search", "content": "ok", "is_error": False}],
            [],
            "",
            use_native=False,
            include_error_conditional=True,
        )

        # 包含成功路径的提示
        assert any("plain-text final answer" in m["content"] for m in working)

    def test_non_native_confirmation_result_uses_error_prompt(self):
        decision = _make_decision(
            text="",
            tool_calls=[ToolCall(name="save", arguments={}, call_id="c1")],
        )
        working: list[dict] = []

        append_tool_result_messages(
            working,
            decision,
            [
                {
                    "name": "save",
                    "content": "needs confirm",
                    "is_error": False,
                    "requires_confirmation": True,
                }
            ],
            [],
            "",
            use_native=False,
            include_error_conditional=True,
        )

        assert any("errors, missing data" in m["content"] for m in working)

    def test_non_native_without_error_conditional_skips_followup(self):
        decision = _make_decision(
            text="",
            tool_calls=[ToolCall(name="search", arguments={}, call_id="c1")],
        )
        working: list[dict] = []

        append_tool_result_messages(
            working,
            decision,
            [{"name": "search", "content": "ok", "is_error": False}],
            [],
            "",
            use_native=False,
            include_error_conditional=False,
        )

        # assistant + summary 两条；不追加 follow-up
        assert len(working) == 2
        assert working[0]["role"] == "assistant"
        assert working[1]["role"] == "user"
        assert working[1]["content"].startswith("Tool results:")


# ── helpers ──────────────────────────────────────────────────────────────


def _make_decision(*, text: str, tool_calls: list[ToolCall]) -> Decision:
    return Decision(decision_type=DecisionType.TOOL_CALLS, text=text, tool_calls=tool_calls)
