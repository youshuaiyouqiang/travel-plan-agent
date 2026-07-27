"""domain/travel/tools/travel_tools.py 单元测试。

覆盖 _save_itinerary、_generate_itinerary_overview、_extract_plan_content、get_travel_specs/handlers。
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from domain.travel.tools.travel_tools import (
    _extract_plan_content,
    _generate_itinerary_overview,
    _save_itinerary,
    get_travel_handlers,
    get_travel_specs,
)
from infrastructure.persistence.database import init_db, reset_connection


class TestSaveItinerary:
    @pytest.mark.asyncio
    async def test_returns_error_when_content_empty(self, tmp_path, monkeypatch):
        from config import settings

        monkeypatch.setattr(settings, "project_root", tmp_path)
        result = await _save_itinerary({"title": "t", "content": ""})
        assert result["is_error"] is True
        assert "missing" in result["content"]

    @pytest.mark.asyncio
    async def test_writes_file_when_content_present(self, tmp_path, monkeypatch):
        from config import settings

        monkeypatch.setattr(settings, "project_root", tmp_path)
        result = await _save_itinerary({"title": "trip1", "content": "第1天 故宫"})
        # 成功时不返回 is_error，只返回 content 描述
        assert "is_error" not in result or result["is_error"] is False
        assert "wrote" in result["content"]
        written_path = tmp_path / "itineraries" / "trip1.md"
        assert written_path.exists()
        assert written_path.read_text(encoding="utf-8") == "第1天 故宫"


class TestExtractPlanContent:
    def test_returns_original_when_no_plan_type(self):
        content = "原始内容"
        assert _extract_plan_content(content, "") == content

    def test_returns_original_when_marker_not_found(self):
        content = "原始内容，没有方案标记"
        assert _extract_plan_content(content, "sightseeing") == content

    def test_extracts_sightseeing_plan(self):
        content = (
            "前导内容\n"
            "## 📋 方案一：景点打卡型\n"
            "第1天 故宫 长城\n" + "x" * 250 + "\n"
            "## 📋 方案二：经济实惠型\n"
            "其他内容"
        )
        result = _extract_plan_content(content, "sightseeing")
        assert "方案一" in result
        assert "方案二" not in result
        # 提取的内容应足够长
        assert len(result) >= 200

    def test_extracts_budget_plan(self):
        content = (
            "前导内容\n"
            "## 📋 方案一：景点打卡型\n" + "x" * 250 + "\n"
            "## 📋 方案二：经济实惠型\n" + "y" * 250 + "\n"
            "## 🏆 推荐方案\n"
            "其他"
        )
        result = _extract_plan_content(content, "budget")
        assert "方案二" in result
        assert "方案一" not in result
        assert "推荐方案" not in result

    def test_returns_original_when_extracted_too_short(self):
        content = "## 📋 方案一：景点打卡型\n短内容"
        result = _extract_plan_content(content, "sightseeing")
        # 提取太短应返回原文
        assert result == content


class TestGenerateItineraryOverview:
    @pytest.fixture(autouse=True)
    def _setup_db(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.db"
        monkeypatch.setattr("config.settings.database_path", db_path)
        reset_connection()
        init_db(db_path)

    @pytest.mark.asyncio
    async def test_returns_error_when_no_content_and_no_session(self):
        result = await _generate_itinerary_overview({"title": "t"})
        assert result["is_error"] is True
        assert "missing" in result["content"]

    @pytest.mark.asyncio
    async def test_returns_error_when_parse_fails(self, monkeypatch):
        # 提供 content，但让 ItineraryParser.parse 抛错且 parse_simple 返回 None
        async def _raise_parse(*args, **kwargs):
            raise RuntimeError("parse failed")

        monkeypatch.setattr(
            "domain.travel.itinerary.parser.ItineraryParser.parse",
            _raise_parse,
        )
        monkeypatch.setattr(
            "domain.travel.itinerary.parser.ItineraryParser.parse_simple",
            lambda _: None,
        )

        result = await _generate_itinerary_overview(
            {"title": "t", "content": "无效内容", "session_id": "s1", "user_id": "u1"}
        )
        assert result["is_error"] is True
        assert "failed to parse" in result["content"]

    @pytest.mark.asyncio
    async def test_generates_itinerary_successfully(self, monkeypatch):
        # 准备一个可解析的 itinerary mock
        mock_itinerary = MagicMock()
        mock_itinerary.id = "abc123"
        mock_itinerary.title = "测试行程"
        mock_itinerary.destination = "北京"
        mock_itinerary.days = [MagicMock(activities=[MagicMock(), MagicMock()])]

        async def _fake_parse(*args, **kwargs):
            return mock_itinerary

        monkeypatch.setattr(
            "domain.travel.itinerary.parser.ItineraryParser.parse",
            _fake_parse,
        )

        # mock repository save_full_itinerary
        mock_repo = MagicMock()
        saved = MagicMock()
        saved.id = "itinerary-id-001"
        saved.title = "测试行程"
        saved.destination = "北京"
        saved.days = [MagicMock(activities=[MagicMock()])]
        mock_repo.save_full_itinerary = MagicMock(return_value=saved)
        # travel_tools 已通过 ``from ... import get_default_itinerary_repository``
        # 把名称导入到模块作用域；必须 patch travel_tools 模块内的名称
        # 才能拦截实际调用。
        monkeypatch.setattr(
            "domain.travel.tools.travel_tools.get_default_itinerary_repository",
            lambda: mock_repo,
        )

        result = await _generate_itinerary_overview(
            {
                "title": "测试行程",
                "content": "第1天 故宫 长城",
                "session_id": "s1",
                "user_id": "u1",
                "destination": "北京",
            }
        )
        assert result["is_error"] is False
        data = json.loads(result["content"])
        assert data["itinerary_id"] == "itinerary-id-001"
        assert data["title"] == "测试行程"
        assert data["destination"] == "北京"


class TestTravelSpecsAndHandlers:
    def test_get_travel_specs_returns_two_specs(self):
        specs = get_travel_specs()
        assert len(specs) == 2
        names = {s.name for s in specs}
        assert "save_itinerary" in names
        assert "generate_itinerary_overview" in names

    def test_get_travel_handlers_returns_two_handlers(self):
        handlers = get_travel_handlers()
        assert "save_itinerary" in handlers
        assert "generate_itinerary_overview" in handlers
        assert callable(handlers["save_itinerary"])
        assert callable(handlers["generate_itinerary_overview"])

    def test_generate_itinerary_overview_spec_has_required_params(self):
        specs = get_travel_specs()
        gen_spec = next(s for s in specs if s.name == "generate_itinerary_overview")
        required = set(gen_spec.parameters.get("required", []))
        assert "title" in required
        assert "session_id" in required

    def test_generate_itinerary_overview_spec_supports_plan_type(self):
        specs = get_travel_specs()
        gen_spec = next(s for s in specs if s.name == "generate_itinerary_overview")
        plan_type_prop = gen_spec.parameters["properties"]["plan_type"]
        assert "sightseeing" in plan_type_prop["enum"]
        assert "budget" in plan_type_prop["enum"]
