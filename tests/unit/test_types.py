"""Tests for core/types.py — IntentType, DecisionType, ToolCall, Decision, TraceEvent"""
from domain.shared.types import (
    IntentType,
    IntentResult,
    DecisionType,
    ToolCall,
    Decision,
    TraceEvent,
)


class TestIntentType:
    def test_enum_values(self):
        assert IntentType.CHAT.value == "chat"
        assert IntentType.QUERY.value == "query"
        assert IntentType.TASK.value == "task"
        assert IntentType.FOLLOW_UP.value == "follow_up"

    def test_from_string(self):
        assert IntentType("chat") == IntentType.CHAT
        assert IntentType("task") == IntentType.TASK

    def test_invalid_string_raises(self):
        import pytest
        with pytest.raises(ValueError):
            IntentType("unknown_intent")


class TestIntentResult:
    def test_defaults(self):
        result = IntentResult(intent=IntentType.CHAT, goal="casual reply")
        assert result.fast_reply is False
        assert result.force_tool is False
        assert result.tool_hints == []

    def test_full_construction(self):
        result = IntentResult(
            intent=IntentType.TASK,
            goal="create a document",
            fast_reply=False,
            force_tool=True,
            tool_hints=["File System", "Shell"],
        )
        assert result.intent == IntentType.TASK
        assert result.goal == "create a document"
        assert result.force_tool is True
        assert result.tool_hints == ["File System", "Shell"]


class TestDecisionType:
    def test_enum_values(self):
        assert DecisionType.FINAL_ANSWER.value == "final_answer"
        assert DecisionType.TOOL_CALLS.value == "tool_calls"


class TestToolCall:
    def test_construction(self):
        call = ToolCall(name="run_shell", arguments={"command": "ls"}, call_id="abc123")
        assert call.name == "run_shell"
        assert call.arguments == {"command": "ls"}
        assert call.call_id == "abc123"


class TestDecision:
    def test_final_answer_decision(self):
        decision = Decision(decision_type=DecisionType.FINAL_ANSWER, text="Here is the answer.")
        assert decision.decision_type == DecisionType.FINAL_ANSWER
        assert decision.text == "Here is the answer."
        assert decision.tool_calls == []
        assert decision.raw is None

    def test_tool_calls_decision(self):
        calls = [ToolCall(name="run_shell", arguments={"command": "echo hello"}, call_id="id1")]
        decision = Decision(
            decision_type=DecisionType.TOOL_CALLS,
            text="I will run a command",
            tool_calls=calls,
            raw={"tool_calls": [{"name": "run_shell"}]},
        )
        assert decision.decision_type == DecisionType.TOOL_CALLS
        assert len(decision.tool_calls) == 1
        assert decision.raw is not None


class TestTraceEvent:
    def test_construction(self):
        event = TraceEvent(kind="tool_call", message="Called run_shell", payload={"iteration": 1})
        assert event.kind == "tool_call"
        assert event.message == "Called run_shell"
        assert event.payload == {"iteration": 1}
        assert event.created_at == ""

    def test_defaults(self):
        event = TraceEvent(kind="result", message="Done")
        assert event.payload == {}
        assert event.created_at == ""