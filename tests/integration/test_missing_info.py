"""Tests for incomplete input handling: destination extraction, missing info detection, and preference-based recommendations"""
import pytest
from unittest.mock import MagicMock

from domain.travel.intent.travel_classifier import TravelIntentClassifier, TravelIntentResult
from domain.travel.intent.travel_schema import TravelIntentType
from domain.memory.manager import DualLayerMemoryManager, LongTermMemory, ShortTermMemory
from infrastructure.persistence.database import init_db, reset_connection, _json_dumps


class TestExtractDestination:
    @pytest.fixture
    def classifier(self):
        return TravelIntentClassifier(llm=None)

    def test_extract_destination_with_qu(self, classifier):
        result = classifier._extract_destination("我想去成都旅游")
        assert result == "成都"

    def test_extract_destination_with_dao(self, classifier):
        result = classifier._extract_destination("计划到三亚度假")
        assert result == "三亚"

    def test_extract_destination_with_fei(self, classifier):
        result = classifier._extract_destination("飞昆明")
        assert result == "昆明"

    def test_extract_destination_known_city(self, classifier):
        result = classifier._extract_destination("北京有什么好玩的")
        assert result == "北京"

    def test_extract_destination_overseas(self, classifier):
        result = classifier._extract_destination("泰国旅游攻略")
        assert result == "泰国"

    def test_extract_destination_no_match(self, classifier):
        result = classifier._extract_destination("帮我查一下机票")
        assert result == ""

    def test_extract_destination_multiple_known(self, classifier):
        result = classifier._extract_destination("从上海到丽江")
        assert result in ("上海", "丽江")

    def test_extract_destination_with_pattern(self, classifier):
        result = classifier._extract_destination("想去大理玩")
        assert result == "大理"


class TestMissingInfoDetection:
    @pytest.fixture
    def classifier(self):
        return TravelIntentClassifier(llm=None)

    def test_trip_planning_missing_all(self, classifier):
        missing = classifier._regex_missing_info(
            "帮我规划行程", TravelIntentType.TRIP_PLANNING
        )
        assert "destination" in missing
        assert "duration" in missing
        assert "dates" in missing

    def test_trip_planning_with_destination(self, classifier):
        missing = classifier._regex_missing_info(
            "想去成都玩", TravelIntentType.TRIP_PLANNING
        )
        assert "destination" not in missing
        assert "duration" in missing
        assert "dates" in missing

    def test_trip_planning_complete(self, classifier):
        missing = classifier._regex_missing_info(
            "5月1号从上海去成都玩5天", TravelIntentType.TRIP_PLANNING
        )
        assert "destination" not in missing
        assert "duration" not in missing
        assert "dates" not in missing

    def test_flight_search_missing_origin(self, classifier):
        missing = classifier._regex_missing_info(
            "查一下去昆明的机票", TravelIntentType.FLIGHT_SEARCH
        )
        assert "origin" in missing

    def test_flight_search_with_origin(self, classifier):
        missing = classifier._regex_missing_info(
            "从北京飞昆明的机票", TravelIntentType.FLIGHT_SEARCH
        )
        assert "origin" not in missing

    def test_hotel_search_missing_destination(self, classifier):
        missing = classifier._regex_missing_info(
            "帮我订酒店", TravelIntentType.HOTEL_SEARCH
        )
        assert "destination" in missing

    def test_attraction_search_missing_destination(self, classifier):
        missing = classifier._regex_missing_info(
            "有什么好玩的景点", TravelIntentType.ATTRACTION_SEARCH
        )
        assert "destination" in missing

    def test_attraction_search_with_destination(self, classifier):
        missing = classifier._regex_missing_info(
            "西安有什么景点", TravelIntentType.ATTRACTION_SEARCH
        )
        assert "destination" not in missing


class TestTravelIntentResultDestination:
    @pytest.fixture
    def classifier(self):
        return TravelIntentClassifier(llm=None)

    @pytest.mark.asyncio
    async def test_keyword_classify_with_destination(self, classifier):
        result = await classifier.classify("想去成都旅游5天")
        assert result.detected_destination == "成都"
        assert result.intent == TravelIntentType.TRIP_PLANNING
        assert "duration" not in result.missing_info

    @pytest.mark.asyncio
    async def test_keyword_classify_no_destination(self, classifier):
        result = await classifier.classify("帮我规划行程")
        assert result.detected_destination == ""
        assert "destination" in result.missing_info


class TestBuildMissingInfoContext:
    @pytest.fixture(autouse=True)
    def _setup_db(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.db"
        monkeypatch.setattr("config.settings.database_path", db_path)
        reset_connection()
        init_db(db_path)

    def _make_agent(self):
        from domain.travel.core import Agent
        from infrastructure.llm.openai import OpenAILLM
        from domain.travel.prompting import PromptBuilder
        from domain.user.session.manager import SessionManager
        from infrastructure.tools.registry import ToolRegistry
        from infrastructure.tools.executor import ToolExecutor
        from infrastructure.tools.policy import ToolPolicy

        llm = MagicMock(spec=OpenAILLM)
        registry = ToolRegistry()
        policy = ToolPolicy()
        executor = ToolExecutor(registry=registry, policy=policy)
        agent = Agent(
            llm=llm,
            prompt_builder=PromptBuilder(),
            session_store=SessionManager(),
            tool_registry=registry,
            tool_executor=executor,
        )
        return agent

    def test_no_ops_result(self):
        agent = self._make_agent()
        result = agent._build_missing_info_context(None, "", "u1")
        assert result == ""

    def test_no_missing_info(self):
        agent = self._make_agent()
        ops = TravelIntentResult(
            intent=TravelIntentType.TRIP_PLANNING,
            goal="test",
            missing_info=[],
        )
        result = agent._build_missing_info_context(ops, "", "u1")
        assert result == ""

    def test_missing_info_without_destination(self):
        agent = self._make_agent()
        ops = TravelIntentResult(
            intent=TravelIntentType.TRIP_PLANNING,
            goal="test",
            missing_info=["destination", "duration", "dates"],
            detected_destination="",
        )
        result = agent._build_missing_info_context(ops, "", "u1")
        assert "目的地" in result
        assert "旅行天数" in result
        assert "出发日期" in result
        assert "提醒用户补充" in result

    def test_missing_info_with_destination(self):
        agent = self._make_agent()
        ops = TravelIntentResult(
            intent=TravelIntentType.TRIP_PLANNING,
            goal="test",
            missing_info=["origin", "duration", "dates"],
            detected_destination="成都",
        )
        result = agent._build_missing_info_context(ops, "", "u1")
        assert "成都" in result
        assert "出发地" in result
        assert "推荐" in result

    def test_missing_info_with_user_preferences(self):
        from infrastructure.persistence.database import get_connection
        from datetime import datetime
        conn = get_connection()
        now = datetime.utcnow().isoformat()
        conn.execute(
            "INSERT INTO long_term_memories "
            "(user_id, category, content, source_ids, extraction_count, "
            "last_accessed_at, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("u1", "preference", "喜欢吃辣", "[]", 3, now, "active", now, now),
        )
        conn.commit()

        agent = self._make_agent()
        ops = TravelIntentResult(
            intent=TravelIntentType.TRIP_PLANNING,
            goal="test",
            missing_info=["origin", "dates"],
            detected_destination="成都",
        )
        result = agent._build_missing_info_context(ops, "some memory context", "u1")
        assert "成都" in result
        assert "喜欢吃辣" in result
        assert "偏好" in result

    def test_missing_info_with_short_term_preferences(self):
        from infrastructure.persistence.database import get_connection
        from datetime import datetime
        conn = get_connection()
        now = datetime.utcnow().isoformat()
        conn.execute(
            "INSERT INTO short_term_memories "
            "(user_id, category, content, source_conv_id, experience_tag, "
            "extraction_count, last_accessed_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("u1", "preference", "偏好民宿", 0, "", 0, now, now),
        )
        conn.commit()

        agent = self._make_agent()
        ops = TravelIntentResult(
            intent=TravelIntentType.TRIP_PLANNING,
            goal="test",
            missing_info=["origin", "dates"],
            detected_destination="三亚",
        )
        result = agent._build_missing_info_context(ops, "some memory context", "u1")
        assert "三亚" in result
        assert "偏好民宿" in result


class TestPromptingMissingInfoContext:
    def test_missing_info_context_in_prompt(self):
        from domain.travel.prompting import PromptBuilder
        from domain.travel.prompt_context import PromptContext
        from domain.travel.context_manager import PreparedContext
        from domain.user.session.manager import Session
        from domain.shared.types import IntentResult, IntentType

        session = Session(session_id="s1")
        prepared = PreparedContext(
            recent_turns=session.turns,
            summary="",
            was_trimmed=False,
        )
        ctx = PromptContext(
            prepared_context=prepared,
            intent=IntentResult(intent=IntentType.TASK, goal="test"),
            tools=[],
            missing_info_context="用户缺少以下关键信息：出发地、出发日期\n用户已提供目的地：成都\n请利用你对成都的了解，主动推荐该地的特色景点、美食、文化活动等",
        )

        builder = PromptBuilder()
        system = builder.build_react_system(ctx)
        assert "信息补全引导" in system
        assert "成都" in system
        assert "出发地" in system


class TestItineraryConfirmIntent:
    @pytest.fixture
    def classifier(self):
        return TravelIntentClassifier(llm=None)

    def test_confirm_satisfied(self, classifier):
        result = classifier._keyword_classify("满意")
        assert result is not None
        assert result.intent == TravelIntentType.ITINERARY_CONFIRM

    def test_confirm_ok(self, classifier):
        result = classifier._keyword_classify("可以")
        assert result is not None
        assert result.intent == TravelIntentType.ITINERARY_CONFIRM

    def test_confirm_jiuxing(self, classifier):
        result = classifier._keyword_classify("就这样吧")
        assert result is not None
        assert result.intent == TravelIntentType.ITINERARY_CONFIRM

    def test_confirm_queren(self, classifier):
        result = classifier._keyword_classify("确认")
        assert result is not None
        assert result.intent == TravelIntentType.ITINERARY_CONFIRM

    def test_confirm_no_problem(self, classifier):
        result = classifier._keyword_classify("没问题")
        assert result is not None
        assert result.intent == TravelIntentType.ITINERARY_CONFIRM

    def test_not_confirm_adjust(self, classifier):
        result = classifier._keyword_classify("换计划")
        assert result is not None
        assert result.intent == TravelIntentType.ITINERARY_ADJUST

    def test_not_confirm_chat(self, classifier):
        result = classifier._keyword_classify("你好")
        if result is not None:
            assert result.intent != TravelIntentType.ITINERARY_CONFIRM
