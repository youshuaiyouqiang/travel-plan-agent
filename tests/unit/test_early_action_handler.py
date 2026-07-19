"""EarlyActionHandler 单元测试。

覆盖 ``handle`` 与 ``handle_stream`` 各种 early_action kind：
- direct_runtime_answer
- emergency_reply
- fast_reply
- itinerary_confirm
- need_input
- 无 early_action 返回 None
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from domain.travel.services.early_action_handler import EarlyActionHandler
from domain.user.session.manager import Session
from domain.user.session.task_state import TaskRecord, TaskStatus


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


@dataclass
class _Intent:
    intent: Any = None
    goal: str = ""
    fast_reply: bool = False
    force_tool: bool = False
    tool_hints: list = field(default_factory=list)


@dataclass
class _IntentEnum:
    value: str = "task"


@dataclass
class _Prep:
    """模拟 ChatPreparation。"""
    session: Any
    task: Any
    intent: Any
    ops_result: Any = None
    system: str = ""
    tools: list = field(default_factory=list)
    selected_mcp_tools: list = field(default_factory=list)
    connected_mcp_tools: list = field(default_factory=list)
    memory_context: str = ""
    dual_memory_context: str = ""
    mcp_context: str = ""
    profile_context: str = ""
    urgency_context: str = ""
    prompt_context: Any = None
    early_action: tuple[str, Any] | None = None
    conversation_history: list = field(default_factory=list)


def _make_session() -> Session:
    return Session(session_id="s1")


def _make_task() -> TaskRecord:
    return TaskRecord(session_id="s1", user_id="u1")


def _make_handler() -> EarlyActionHandler:
    return EarlyActionHandler(
        llm=MagicMock(),
        memory=MagicMock(),
        session_store=MagicMock(),
        task_store=MagicMock(),
        trace_store=MagicMock(),
        itinerary_generator=MagicMock(),
        memory_processor=MagicMock(),
    )


# ---------------------------------------------------------------------------
# handle()
# ---------------------------------------------------------------------------


class TestEarlyActionHandlerHandle:
    @pytest.mark.asyncio
    async def test_no_early_action_returns_none(self):
        handler = _make_handler()
        prep = _Prep(session=_make_session(), task=_make_task(), intent=_Intent(), early_action=None)
        result = await handler.handle(
            prep=prep, session_id="s1", user_id="u1", memory_scope="u1", message="hi"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_direct_runtime_answer(self):
        handler = _make_handler()
        session = _make_session()
        task = _make_task()
        prep = _Prep(
            session=session,
            task=task,
            intent=_Intent(),
            early_action=("direct_runtime_answer", "今天是 2026-01-01"),
        )
        result = await handler.handle(
            prep=prep, session_id="s1", user_id="u1", memory_scope="u1", message="今天几号"
        )
        assert result == {"status": "completed", "reply": "今天是 2026-01-01"}
        # 验证 session.append / task.mark_finished / save 被调用
        assert any(t.role == "assistant" and t.content == "今天是 2026-01-01" for t in session.turns)
        assert task.status == TaskStatus.COMPLETED
        handler._session_store.save.assert_called()
        handler._task_store.save.assert_called()
        handler._trace_store.put.assert_called()

    @pytest.mark.asyncio
    async def test_emergency_reply(self):
        handler = _make_handler()
        session = _make_session()
        task = _make_task()
        prep = _Prep(
            session=session,
            task=task,
            intent=_Intent(),
            early_action=("emergency_reply", "紧急联系信息"),
        )
        result = await handler.handle(
            prep=prep, session_id="s1", user_id="u1", memory_scope="u1", message="护照丢了"
        )
        assert result == {"status": "completed", "reply": "紧急联系信息"}
        assert any(t.role == "assistant" and t.content == "紧急联系信息" for t in session.turns)
        handler._session_store.save.assert_called()

    @pytest.mark.asyncio
    async def test_fast_reply(self):
        handler = _make_handler()
        handler._llm.complete = AsyncMock(return_value="快速回复")
        session = _make_session()
        task = _make_task()
        intent = _Intent(intent=_IntentEnum("chat"), goal="打招呼", fast_reply=True)
        prep = _Prep(
            session=session,
            task=task,
            intent=intent,
            early_action=("fast_reply", "你是助手"),
        )
        result = await handler.handle(
            prep=prep, session_id="s1", user_id="u1", memory_scope="u1", message="你好"
        )
        assert result == {"status": "completed", "reply": "快速回复"}
        handler._llm.complete.assert_awaited_once()
        assert task.status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_itinerary_confirm_with_id(self):
        handler = _make_handler()
        handler._itinerary_generator.generate_itinerary = AsyncMock(
            return_value=("这是您的行程", "itinerary-123")
        )
        handler._memory_processor.process = AsyncMock()
        session = _make_session()
        task = _make_task()
        intent = _Intent(intent=_IntentEnum("task"), goal="确认行程")
        ops_result = MagicMock()
        prep = _Prep(
            session=session,
            task=task,
            intent=intent,
            ops_result=ops_result,
            early_action=("itinerary_confirm", ops_result),
        )
        result = await handler.handle(
            prep=prep, session_id="s1", user_id="u1", memory_scope="u1", message="确认"
        )
        assert result == {
            "status": "completed",
            "reply": "这是您的行程",
            "itinerary_id": "itinerary-123",
        }
        assert task.metadata.get("last_itinerary_id") == "itinerary-123"
        handler._memory_processor.process.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_itinerary_confirm_without_id(self):
        handler = _make_handler()
        handler._itinerary_generator.generate_itinerary = AsyncMock(
            return_value=("这是您的行程", None)
        )
        handler._memory_processor.process = AsyncMock()
        prep = _Prep(
            session=_make_session(),
            task=_make_task(),
            intent=_Intent(intent=_IntentEnum("task"), goal="确认行程"),
            early_action=("itinerary_confirm", MagicMock()),
        )
        result = await handler.handle(
            prep=prep, session_id="s1", user_id="u1", memory_scope="u1", message="确认"
        )
        assert result == {"status": "completed", "reply": "这是您的行程"}

    @pytest.mark.asyncio
    async def test_need_input(self):
        handler = _make_handler()
        task = _make_task()
        prep = _Prep(
            session=_make_session(),
            task=task,
            intent=_Intent(),
            early_action=("need_input", "请问您想去哪里？"),
        )
        result = await handler.handle(
            prep=prep, session_id="s1", user_id="u1", memory_scope="u1", message="想去旅游"
        )
        assert result == {"status": "needs_user_input", "reply": "请问您想去哪里？"}
        assert task.status == TaskStatus.NEEDS_USER_INPUT
        assert task.pending_prompt == "请问您想去哪里？"

    @pytest.mark.asyncio
    async def test_unknown_kind_returns_none(self):
        handler = _make_handler()
        prep = _Prep(
            session=_make_session(),
            task=_make_task(),
            intent=_Intent(),
            early_action=("unknown_kind", "data"),
        )
        result = await handler.handle(
            prep=prep, session_id="s1", user_id="u1", memory_scope="u1", message="hi"
        )
        assert result is None


# ---------------------------------------------------------------------------
# handle_stream()
# ---------------------------------------------------------------------------


async def _collect(gen: AsyncGenerator[dict, None]) -> list[dict]:
    items: list[dict] = []
    async for ev in gen:
        items.append(ev)
    return items


class TestEarlyActionHandlerHandleStream:
    @pytest.mark.asyncio
    async def test_no_early_action_no_events(self):
        handler = _make_handler()
        prep = _Prep(session=_make_session(), task=_make_task(), intent=_Intent(), early_action=None)
        events = await _collect(
            handler.handle_stream(
                prep=prep, session_id="s1", user_id="u1", memory_scope="u1", message="hi"
            )
        )
        assert events == []

    @pytest.mark.asyncio
    async def test_direct_runtime_answer_stream(self):
        handler = _make_handler()
        prep = _Prep(
            session=_make_session(),
            task=_make_task(),
            intent=_Intent(),
            early_action=("direct_runtime_answer", "今天是 2026-01-01"),
        )
        events = await _collect(
            handler.handle_stream(
                prep=prep, session_id="s1", user_id="u1", memory_scope="u1", message="今天几号"
            )
        )
        assert events == [
            {"type": "chunk", "data": "今天是 2026-01-01"},
            {"type": "done", "data": "completed"},
        ]

    @pytest.mark.asyncio
    async def test_emergency_reply_stream(self):
        handler = _make_handler()
        prep = _Prep(
            session=_make_session(),
            task=_make_task(),
            intent=_Intent(),
            early_action=("emergency_reply", "紧急联系"),
        )
        events = await _collect(
            handler.handle_stream(
                prep=prep, session_id="s1", user_id="u1", memory_scope="u1", message="报警"
            )
        )
        assert events == [
            {"type": "chunk", "data": "紧急联系"},
            {"type": "done", "data": "completed"},
        ]

    @pytest.mark.asyncio
    async def test_fast_reply_stream(self):
        handler = _make_handler()

        async def fake_stream(*, system, messages):
            yield "chunk1"
            yield "chunk2"

        handler._llm.stream_complete = fake_stream
        prep = _Prep(
            session=_make_session(),
            task=_make_task(),
            intent=_Intent(intent=_IntentEnum("chat"), goal="打招呼"),
            early_action=("fast_reply", "你是助手"),
        )
        events = await _collect(
            handler.handle_stream(
                prep=prep, session_id="s1", user_id="u1", memory_scope="u1", message="你好"
            )
        )
        assert events[0] == {"type": "status", "data": "thinking"}
        assert events[1] == {"type": "chunk", "data": "chunk1"}
        assert events[2] == {"type": "chunk", "data": "chunk2"}
        assert events[-1] == {"type": "done", "data": "completed"}

    @pytest.mark.asyncio
    async def test_itinerary_confirm_stream_with_id(self):
        handler = _make_handler()
        handler._itinerary_generator.generate_itinerary = AsyncMock(
            return_value=("您的行程", "it-001")
        )
        handler._memory_processor.process = AsyncMock()
        prep = _Prep(
            session=_make_session(),
            task=_make_task(),
            intent=_Intent(intent=_IntentEnum("task"), goal="确认行程"),
            early_action=("itinerary_confirm", MagicMock()),
        )
        events = await _collect(
            handler.handle_stream(
                prep=prep, session_id="s1", user_id="u1", memory_scope="u1", message="确认"
            )
        )
        assert events[0] == {"type": "status", "data": "thinking"}
        assert events[1] == {"type": "chunk", "data": "您的行程"}
        assert events[2] == {"type": "done", "data": {"status": "completed", "itinerary_id": "it-001"}}

    @pytest.mark.asyncio
    async def test_itinerary_confirm_stream_without_id(self):
        handler = _make_handler()
        handler._itinerary_generator.generate_itinerary = AsyncMock(
            return_value=("您的行程", None)
        )
        handler._memory_processor.process = AsyncMock()
        prep = _Prep(
            session=_make_session(),
            task=_make_task(),
            intent=_Intent(intent=_IntentEnum("task"), goal="确认行程"),
            early_action=("itinerary_confirm", MagicMock()),
        )
        events = await _collect(
            handler.handle_stream(
                prep=prep, session_id="s1", user_id="u1", memory_scope="u1", message="确认"
            )
        )
        assert events[-1] == {"type": "done", "data": "completed"}

    @pytest.mark.asyncio
    async def test_need_input_stream(self):
        handler = _make_handler()
        prep = _Prep(
            session=_make_session(),
            task=_make_task(),
            intent=_Intent(),
            early_action=("need_input", "请补充信息"),
        )
        events = await _collect(
            handler.handle_stream(
                prep=prep, session_id="s1", user_id="u1", memory_scope="u1", message="x"
            )
        )
        assert events[0] == {"type": "status", "data": "thinking"}
        assert events[1] == {"type": "chunk", "data": "请补充信息"}
        assert events[2] == {"type": "done", "data": "needs_user_input"}
