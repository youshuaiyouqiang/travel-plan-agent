"""domain/travel/agent.py 单元测试。

覆盖 TravelAgent 的 _inject_multi_plan_anchor / _extract_actions / chat / chat_stream。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from domain.travel.agent import TravelAgent


class _StubCoreAgent:
    """底层 Agent 的最小 stub。"""

    def __init__(
        self,
        *,
        chat_result: dict | None = None,
        stream_events: list[dict] | None = None,
    ) -> None:
        self._chat_result = chat_result or {}
        self._stream_events = stream_events or []
        self.chat = AsyncMock(return_value=self._chat_result)

    async def chat_stream(self, *, session_id: str, message: str, user_id: str | None = None) -> AsyncGenerator[dict, None]:
        for event in self._stream_events:
            yield event


class TestInjectMultiPlanAnchor:
    def test_no_injection_when_anchor_already_present(self):
        reply = "方案一\n<!--MULTI_PLAN:plan1=sightseeing-->"
        result = TravelAgent._inject_multi_plan_anchor(reply)
        assert result == reply

    def test_no_injection_when_no_plan1_signal(self):
        reply = "普通的回复内容，没有任何方案信号"
        result = TravelAgent._inject_multi_plan_anchor(reply)
        assert result == reply

    def test_injects_single_plan_when_only_plan1_present(self):
        reply = "方案一：景点打卡型\n第1天 故宫"
        result = TravelAgent._inject_multi_plan_anchor(reply)
        assert "<!--MULTI_PLAN:plan1=sightseeing-->" in result
        assert "plan2" not in result

    def test_injects_multi_plan_when_plan2_present(self):
        reply = "方案一：景点打卡型\n方案二：经济实惠型\n第1天 故宫"
        result = TravelAgent._inject_multi_plan_anchor(reply)
        assert "<!--MULTI_PLAN:plan1=sightseeing,plan2=budget-->" in result

    def test_injection_appends_at_end(self):
        reply = "方案一：景点打卡型"
        result = TravelAgent._inject_multi_plan_anchor(reply)
        assert result.rstrip().endswith("-->")


class TestExtractActions:
    def test_no_actions_when_no_itinerary_id(self):
        agent = TravelAgent(_StubCoreAgent())
        actions = agent._extract_actions("普通回复", structured_data=None)
        assert actions == []

    def test_extracts_actions_from_structured_data(self):
        agent = TravelAgent(_StubCoreAgent())
        actions = agent._extract_actions(
            "行程概览已生成",
            structured_data={"itinerary_id": "abcdef0123456789"},
        )
        assert len(actions) == 1
        assert actions[0]["type"] == "navigate"
        assert "/agent/travel/itinerary/abcdef0123456789" in actions[0]["path"]
        assert actions[0]["agent"] == "travel"

    def test_extracts_actions_from_text_fallback(self):
        agent = TravelAgent(_StubCoreAgent())
        # 文本中含 itinerary_id 标记 + 16 位 hex
        actions = agent._extract_actions("行程概览已生成！itinerary_id: abcdef0123456789")
        assert len(actions) == 1
        assert "abcdef0123456789" in actions[0]["path"]

    def test_no_extraction_when_text_has_no_marker(self):
        agent = TravelAgent(_StubCoreAgent())
        # 16 位 hex 但没有"行程概览已生成"/"itinerary_id"标记
        actions = agent._extract_actions("随机内容 abcdef0123456789 末尾")
        assert actions == []

    def test_includes_plan_type_when_present(self):
        agent = TravelAgent(_StubCoreAgent())
        actions = agent._extract_actions(
            "行程概览已生成",
            structured_data={"itinerary_id": "abcdef0123456789", "plan_type": "sightseeing"},
        )
        assert actions[0]["plan_type"] == "sightseeing"

    def test_no_plan_type_when_absent(self):
        agent = TravelAgent(_StubCoreAgent())
        actions = agent._extract_actions(
            "行程概览已生成",
            structured_data={"itinerary_id": "abcdef0123456789"},
        )
        assert "plan_type" not in actions[0]


class TestTravelAgentChat:
    @pytest.mark.asyncio
    async def test_chat_injects_anchor_when_plan1_present(self):
        core = _StubCoreAgent(chat_result={"reply": "方案一：景点打卡型\n第1天 故宫"})
        agent = TravelAgent(core)
        result = await agent.chat(session_id="s1", message="生成行程", user_id="u1")
        assert "<!--MULTI_PLAN:" in result["reply"]
        assert result["active_agent"] == "travel"
        assert "agent_actions" in result

    @pytest.mark.asyncio
    async def test_chat_does_not_inject_when_no_plan(self):
        core = _StubCoreAgent(chat_result={"reply": "普通回复"})
        agent = TravelAgent(core)
        result = await agent.chat(session_id="s1", message="hi", user_id="u1")
        assert "<!--MULTI_PLAN:" not in result["reply"]
        assert result["agent_actions"] == []

    @pytest.mark.asyncio
    async def test_chat_extracts_actions_from_structured_itinerary_id(self):
        core = _StubCoreAgent(
            chat_result={
                "reply": "行程概览已生成",
                "itinerary_id": "abcdef0123456789",
            }
        )
        agent = TravelAgent(core)
        result = await agent.chat(session_id="s1", message="生成行程", user_id="u1")
        assert len(result["agent_actions"]) == 1
        assert "abcdef0123456789" in result["agent_actions"][0]["path"]


class TestTravelAgentChatStream:
    @pytest.mark.asyncio
    async def test_emits_route_event_first(self):
        core = _StubCoreAgent(
            stream_events=[
                {"type": "chunk", "data": "hello"},
                {"type": "done", "data": "completed"},
            ]
        )
        agent = TravelAgent(core)
        events = []
        async for event in agent.chat_stream(session_id="s1", message="hi", user_id="u1"):
            events.append(event)
        # 第一个事件应是 route
        assert events[0] == {"type": "route", "data": "travel"}
        # 后续是 chunk、done
        assert events[1] == {"type": "chunk", "data": "hello"}
        assert events[2] == {"type": "done", "data": "completed"}

    @pytest.mark.asyncio
    async def test_injects_anchor_as_additional_chunk(self):
        core = _StubCoreAgent(
            stream_events=[
                {"type": "chunk", "data": "方案一：景点打卡型\n第1天 故宫"},
                {"type": "done", "data": "completed"},
            ]
        )
        agent = TravelAgent(core)
        events = []
        async for event in agent.chat_stream(session_id="s1", message="hi", user_id="u1"):
            events.append(event)
        # 应有额外的 chunk 注入锚点
        anchor_chunks = [e for e in events if e.get("type") == "chunk" and "MULTI_PLAN" in e.get("data", "")]
        assert len(anchor_chunks) >= 1

    @pytest.mark.asyncio
    async def test_emits_actions_after_done_when_itinerary_id_in_done_data(self):
        core = _StubCoreAgent(
            stream_events=[
                {"type": "chunk", "data": "生成中"},
                {"type": "done", "data": {"itinerary_id": "abcdef0123456789"}},
            ]
        )
        agent = TravelAgent(core)
        events = []
        async for event in agent.chat_stream(session_id="s1", message="hi", user_id="u1"):
            events.append(event)
        # done 之后应有 actions 事件
        actions_events = [e for e in events if e.get("type") == "actions"]
        assert len(actions_events) == 1
        assert len(actions_events[0]["data"]) == 1


class TestTravelAgentDelegation:
    def test_getattr_delegates_to_core_agent(self):
        core = _StubCoreAgent()
        core.some_method = lambda x: x * 2
        agent = TravelAgent(core)
        assert agent.some_method(5) == 10

    def test_getattr_raises_for_private_attrs(self):
        core = _StubCoreAgent()
        agent = TravelAgent(core)
        with pytest.raises(AttributeError):
            agent._private_attr

    def test_name_property(self):
        agent = TravelAgent(_StubCoreAgent())
        assert agent.name == "travel"

    def test_description_property(self):
        agent = TravelAgent(_StubCoreAgent())
        assert "旅行" in agent.description
