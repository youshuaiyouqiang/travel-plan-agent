"""domain/travel/services/ 单元测试。

覆盖 cache_manager / prompt_helper / itinerary_generator / memory_processor。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

import pytest

from domain.travel.intent.travel_schema import TravelIntentType
from domain.travel.services.cache_manager import CacheManager
from domain.travel.services.itinerary_generator import ItineraryGenerator
from domain.travel.services.memory_processor import MemoryProcessor
from domain.travel.services.prompt_helper import PromptHelper
from domain.user.session.task_state import TaskRecord


# ----------------------------------------------------------------------
# Stubs
# ----------------------------------------------------------------------


@dataclass
class _StubMemory:
    """长期/短期记忆 stub。"""

    _ltm: list = field(default_factory=list)
    _stm: list = field(default_factory=list)

    def get_long_term_memories(self, user_id: str):
        return self._ltm

    def get_short_term_memories(self, user_id: str):
        return self._stm


@dataclass
class _StubMemoryItem:
    content: str = ""
    category: str = ""
    experience_tag: str = ""
    id: int = 0


@dataclass
class _StubIntentResult:
    """TravelIntentResult stub。"""

    intent: TravelIntentType = TravelIntentType.GENERAL_CHAT
    missing_info: list = field(default_factory=list)
    detected_destination: str = ""
    modification_scope: str | None = None
    affected_categories: list = field(default_factory=list)


@dataclass
class _StubOpsResult:
    """对 ops_result 的极简 stub。"""

    intent: Any = None
    missing_info: list = field(default_factory=list)
    detected_destination: str = ""


@dataclass
class _StubTurn:
    role: str
    content: str


@dataclass
class _StubSession:
    turns: list = field(default_factory=list)
    summary: str = ""


# ----------------------------------------------------------------------
# CacheManager
# ----------------------------------------------------------------------


class TestCacheManagerBuildCachedContext:
    def test_returns_empty_when_no_cache(self):
        cm = CacheManager(reasoning=MagicMock(), dual_memory=MagicMock())
        task = TaskRecord(session_id="s1", user_id="u1")
        assert cm.build_cached_context(task) == ""

    def test_returns_empty_when_all_results_empty(self):
        cm = CacheManager(reasoning=MagicMock(), dual_memory=MagicMock())
        task = TaskRecord(session_id="s1", user_id="u1")
        task.cache_tool_result("search_flight", {}, "")
        assert cm.build_cached_context(task) == ""

    def test_renders_categories_with_label(self):
        cm = CacheManager(reasoning=MagicMock(), dual_memory=MagicMock())
        task = TaskRecord(session_id="s1", user_id="u1")
        task.cache_tool_result("search_flight", {"from": "PEK"}, "航班结果示例")
        task.cache_tool_result("search_hotel", {"city": "北京"}, "酒店结果示例")
        ctx = cm.build_cached_context(task)
        assert "机票" in ctx
        assert "航班结果示例" in ctx
        assert "酒店" in ctx
        assert "酒店结果示例" in ctx
        assert "仍然有效" in ctx

    def test_truncates_long_result_to_2000_chars(self):
        cm = CacheManager(reasoning=MagicMock(), dual_memory=MagicMock())
        task = TaskRecord(session_id="s1", user_id="u1")
        long_result = "x" * 5000
        task.cache_tool_result("search_flight", {}, long_result)
        ctx = cm.build_cached_context(task)
        # 应截断到 2000
        assert "x" * 2000 in ctx
        assert "x" * 2001 not in ctx

    def test_unknown_category_uses_raw_name(self):
        cm = CacheManager(reasoning=MagicMock(), dual_memory=MagicMock())
        task = TaskRecord(session_id="s1", user_id="u1")
        task.cache_tool_result("custom_tool", {}, "结果")
        ctx = cm.build_cached_context(task)
        # 未知 category 用原名（custom_tool）
        assert "custom_tool" in ctx
        assert "结果" in ctx


class TestCacheManagerHandleInvalidation:
    def test_noop_when_no_cache(self):
        cm = CacheManager(reasoning=MagicMock(), dual_memory=MagicMock())
        task = TaskRecord(session_id="s1", user_id="u1")
        # 没有 cached_tool_results，应直接 return
        cm.handle_invalidation(task, "随便说", None)
        # 没有抛错即可
        assert task.get_cached_results() == {}

    def test_full_invalidation_via_llm_full_research(self):
        cm = CacheManager(reasoning=MagicMock(), dual_memory=MagicMock())
        task = TaskRecord(session_id="s1", user_id="u1")
        task.cache_tool_result("search_flight", {}, "x")
        task.cache_tool_result("search_hotel", {}, "y")
        ops = _StubIntentResult(
            intent=TravelIntentType.ITINERARY_ADJUST,
            modification_scope="full_research",
        )
        cm.handle_invalidation(task, "换目的地", ops)
        assert task.get_cached_results() == {}

    def test_partial_invalidation_via_llm_partial_research(self):
        cm = CacheManager(reasoning=MagicMock(), dual_memory=MagicMock())
        task = TaskRecord(session_id="s1", user_id="u1")
        task.cache_tool_result("search_flight", {}, "x")
        task.cache_tool_result("search_hotel", {}, "y")
        ops = _StubIntentResult(
            intent=TravelIntentType.ITINERARY_ADJUST,
            modification_scope="partial_research",
            affected_categories=["hotel"],
        )
        cm.handle_invalidation(task, "换酒店", ops)
        cached = task.get_cached_results()
        assert "flight" in cached
        assert "hotel" not in cached

    def test_local_reorder_keeps_cache(self):
        cm = CacheManager(reasoning=MagicMock(), dual_memory=MagicMock())
        task = TaskRecord(session_id="s1", user_id="u1")
        task.cache_tool_result("search_flight", {}, "x")
        task.cache_tool_result("search_hotel", {}, "y")
        ops = _StubIntentResult(
            intent=TravelIntentType.ITINERARY_ADJUST,
            modification_scope="local_reorder",
        )
        cm.handle_invalidation(task, "调换顺序", ops)
        # 缓存不动
        assert len(task.get_cached_results()) == 2

    def test_fallback_full_invalidation_on_core_keywords(self):
        cm = CacheManager(reasoning=MagicMock(), dual_memory=MagicMock())
        task = TaskRecord(session_id="s1", user_id="u1")
        task.cache_tool_result("search_flight", {}, "x")
        # ops_result 没有 modification_scope，应走关键词兜底
        cm.handle_invalidation(task, "换个出发地", _StubIntentResult(intent=TravelIntentType.GENERAL_CHAT))
        assert task.get_cached_results() == {}

    def test_fallback_partial_invalidation_hotel_keyword(self):
        cm = CacheManager(reasoning=MagicMock(), dual_memory=MagicMock())
        task = TaskRecord(session_id="s1", user_id="u1")
        task.cache_tool_result("search_hotel", {}, "x")
        task.cache_tool_result("search_flight", {}, "y")
        cm.handle_invalidation(task, "换个酒店", None)
        cached = task.get_cached_results()
        assert "flight" in cached
        assert "hotel" not in cached

    def test_fallback_partial_invalidation_poi_keyword(self):
        cm = CacheManager(reasoning=MagicMock(), dual_memory=MagicMock())
        task = TaskRecord(session_id="s1", user_id="u1")
        task.cache_tool_result("search_poi", {}, "x")
        task.cache_tool_result("search_flight", {}, "y")
        cm.handle_invalidation(task, "换个景点", None)
        cached = task.get_cached_results()
        assert "flight" in cached
        assert "poi" not in cached

    def test_no_invalidation_for_general_message(self):
        cm = CacheManager(reasoning=MagicMock(), dual_memory=MagicMock())
        task = TaskRecord(session_id="s1", user_id="u1")
        task.cache_tool_result("search_flight", {}, "x")
        cm.handle_invalidation(task, "好的谢谢", None)
        assert task.get_cached_results() != {}


class TestCacheManagerCacheResultsFromTrace:
    def test_skips_when_no_trace(self):
        reasoning = MagicMock()
        reasoning.last_trace = None
        cm = CacheManager(reasoning=reasoning, dual_memory=MagicMock())
        task = TaskRecord(session_id="s1", user_id="u1")
        cm.cache_results_from_trace(task)
        assert task.get_cached_results() == {}

    def test_caches_successful_tool_results(self):
        step = MagicMock()
        step.tool_results = [{"content": "result-1", "is_error": False}]
        step.tool_calls = [{"name": "search_flight", "arguments": {"from": "PEK"}}]
        reasoning = MagicMock()
        reasoning.last_trace = [step]
        cm = CacheManager(reasoning=reasoning, dual_memory=MagicMock())
        task = TaskRecord(session_id="s1", user_id="u1")
        cm.cache_results_from_trace(task)
        cached = task.get_cached_results()
        assert "flight" in cached
        assert cached["flight"]["tool_name"] == "search_flight"
        assert cached["flight"]["result"] == "result-1"

    def test_skips_error_results(self):
        step = MagicMock()
        step.tool_results = [{"content": "error-msg", "is_error": True}]
        step.tool_calls = [{"name": "search_flight", "arguments": {}}]
        reasoning = MagicMock()
        reasoning.last_trace = [step]
        cm = CacheManager(reasoning=reasoning, dual_memory=MagicMock())
        task = TaskRecord(session_id="s1", user_id="u1")
        cm.cache_results_from_trace(task)
        assert task.get_cached_results() == {}

    def test_skips_steps_without_tool_results(self):
        step = MagicMock()
        step.tool_results = []
        reasoning = MagicMock()
        reasoning.last_trace = [step]
        cm = CacheManager(reasoning=reasoning, dual_memory=MagicMock())
        task = TaskRecord(session_id="s1", user_id="u1")
        cm.cache_results_from_trace(task)
        assert task.get_cached_results() == {}


# ----------------------------------------------------------------------
# PromptHelper
# ----------------------------------------------------------------------


class TestPromptHelper:
    def test_build_missing_info_context_returns_empty_when_no_missing(self):
        helper = PromptHelper(dual_memory=_StubMemory())
        result = helper.build_missing_info_context(_StubOpsResult(), "", "u1")
        assert result == ""

    def test_build_missing_info_context_renders_missing_fields(self):
        helper = PromptHelper(dual_memory=_StubMemory())
        ops = _StubOpsResult(missing_info=["destination", "duration"])
        result = helper.build_missing_info_context(ops, "", "u1")
        assert "目的地" in result
        assert "旅行天数" in result

    def test_build_missing_info_context_with_destination(self):
        helper = PromptHelper(dual_memory=_StubMemory())
        ops = _StubOpsResult(missing_info=["duration"], detected_destination="北京")
        result = helper.build_missing_info_context(ops, "", "u1")
        assert "北京" in result

    def test_build_clarification_question_destination_first(self):
        helper = PromptHelper(dual_memory=_StubMemory())
        ops = _StubOpsResult(missing_info=["duration", "destination"])
        q = helper.build_clarification_question(ops)
        assert "去哪个城市" in q

    def test_build_clarification_question_single_missing(self):
        helper = PromptHelper(dual_memory=_StubMemory())
        ops = _StubOpsResult(missing_info=["duration"], detected_destination="北京")
        q = helper.build_clarification_question(ops)
        assert "北京" in q
        assert "几天" in q

    def test_build_clarification_question_multiple_missing(self):
        helper = PromptHelper(dual_memory=_StubMemory())
        ops = _StubOpsResult(
            missing_info=["origin", "duration", "budget"],
            detected_destination="北京",
        )
        q = helper.build_clarification_question(ops)
        assert "北京" in q
        # 多个缺失信息一次性问完
        assert "出发" in q or "几天" in q or "预算" in q


# ----------------------------------------------------------------------
# ItineraryGenerator
# ----------------------------------------------------------------------


class TestItineraryGeneratorBuildConfirmContext:
    def test_returns_empty_when_no_ops_result(self):
        gen = ItineraryGenerator(llm=MagicMock(), session_store=MagicMock(), dual_memory=MagicMock())
        assert gen.build_confirm_context(None, _StubSession(), "", "") == ""

    def test_returns_empty_when_intent_not_confirm(self):
        gen = ItineraryGenerator(llm=MagicMock(), session_store=MagicMock(), dual_memory=MagicMock())
        ops = _StubOpsResult(intent=TravelIntentType.GENERAL_CHAT)
        assert gen.build_confirm_context(ops, _StubSession(), "", "") == ""

    def test_returns_empty_when_no_itinerary_content_in_history(self):
        gen = ItineraryGenerator(llm=MagicMock(), session_store=MagicMock(), dual_memory=MagicMock())
        ops = MagicMock()
        ops.intent = TravelIntentType.ITINERARY_CONFIRM
        session = _StubSession(turns=[_StubTurn(role="assistant", content="短回复")])
        assert gen.build_confirm_context(ops, session, "u1", "s1") == ""

    def test_returns_confirm_prompt_when_itinerary_found(self):
        gen = ItineraryGenerator(llm=MagicMock(), session_store=MagicMock(), dual_memory=MagicMock())
        ops = MagicMock()
        ops.intent = TravelIntentType.ITINERARY_CONFIRM
        long_content = "第1天 上午：故宫；下午：天坛；晚上：王府井。" + "x" * 100
        session = _StubSession(turns=[_StubTurn(role="assistant", content=long_content)])
        result = gen.build_confirm_context(ops, session, "u1", "s1")
        assert "ITINERARY_CONFIRM" in result or "行程确认" in result
        assert "generate_itinerary_overview" in result


class TestItineraryGeneratorGenerateItinerary:
    @pytest.mark.asyncio
    async def test_returns_error_when_no_itinerary_content(self):
        gen = ItineraryGenerator(llm=MagicMock(), session_store=MagicMock(), dual_memory=MagicMock())
        session = _StubSession(turns=[_StubTurn(role="assistant", content="短")])
        reply, itinerary_id = await gen.generate_itinerary(
            session=session, session_id="s1", user_id="u1", ops_result=None
        )
        assert "未能找到行程内容" in reply
        assert itinerary_id == ""

    @pytest.mark.asyncio
    async def test_returns_error_when_tool_raises(self, monkeypatch):
        gen = ItineraryGenerator(llm=MagicMock(), session_store=MagicMock(), dual_memory=MagicMock())
        long_content = "第1天 行程安排：故宫。" + "x" * 100
        session = _StubSession(turns=[_StubTurn(role="assistant", content=long_content)])

        async def _raise(args):
            raise RuntimeError("boom")

        monkeypatch.setattr(
            "domain.travel.services.itinerary_generator._generate_itinerary_overview",
            _raise,
            raising=False,
        )
        # 直接 monkeypatch 内部 import：函数内部 from ... import _generate_itinerary_overview
        # 通过替换模块属性来生效
        import domain.travel.tools.travel_tools as tt

        monkeypatch.setattr(tt, "_generate_itinerary_overview", _raise)
        reply, itinerary_id = await gen.generate_itinerary(
            session=session, session_id="s1", user_id="u1", ops_result=None
        )
        assert "失败" in reply
        assert itinerary_id == ""


# ----------------------------------------------------------------------
# MemoryProcessor
# ----------------------------------------------------------------------


class TestMemoryProcessor:
    @pytest.mark.asyncio
    async def test_skips_when_extraction_disabled(self, monkeypatch):
        from config import settings as cfg

        monkeypatch.setattr(cfg, "memory_extraction_enabled", False)
        processor = MemoryProcessor(
            dual_memory=MagicMock(),
            memory_extractor=MagicMock(),
            memory_distiller=MagicMock(),
        )
        # 不应抛错，直接返回
        await processor.process(_StubSession(), "s1", "u1", "u1")
        # dual_memory.save_conversation 不应被调用
        assert not processor._dual_memory.save_conversation.called

    @pytest.mark.asyncio
    async def test_skips_when_no_user_id(self, monkeypatch):
        from config import settings as cfg

        monkeypatch.setattr(cfg, "memory_extraction_enabled", True)
        processor = MemoryProcessor(
            dual_memory=MagicMock(),
            memory_extractor=MagicMock(),
            memory_distiller=MagicMock(),
        )
        await processor.process(_StubSession(), "s1", "u1", None)
        assert not processor._dual_memory.save_conversation.called

    @pytest.mark.asyncio
    async def test_swallows_exceptions_from_memory_pipeline(self, monkeypatch):
        from config import settings as cfg

        monkeypatch.setattr(cfg, "memory_extraction_enabled", True)
        dual_memory = MagicMock()
        dual_memory.save_conversation.side_effect = RuntimeError("db error")
        processor = MemoryProcessor(
            dual_memory=dual_memory,
            memory_extractor=MagicMock(),
            memory_distiller=MagicMock(),
        )
        # 不应抛出
        await processor.process(_StubSession(), "s1", "u1", "u1")
