from __future__ import annotations

import json
import pytest
from datetime import datetime

from infrastructure.persistence.database import get_connection, reset_connection, init_db
from core.itinerary.schema import Itinerary, DayPlan, Activity
from core.itinerary.repository import ItineraryRepository
from core.itinerary.parser import ItineraryParser


@pytest.fixture(autouse=True)
def _setup_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_itinerary.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield
    reset_connection()


class TestItineraryRepository:
    def test_create_and_get_itinerary(self):
        repo = ItineraryRepository()
        created = repo.create_itinerary(
            user_id="u1",
            title="成都5日游",
            destination="成都",
            start_date="2026-06-01",
            end_date="2026-06-05",
            session_id="s1",
            budget="约5000元/人",
        )
        assert created.id
        assert created.title == "成都5日游"
        assert created.destination == "成都"
        assert created.status == "planning"

        fetched = repo.get_itinerary(created.id)
        assert fetched is not None
        assert fetched.title == "成都5日游"
        assert fetched.user_id == "u1"

    def test_list_itineraries(self):
        repo = ItineraryRepository()
        repo.create_itinerary(user_id="u1", title="成都5日游", destination="成都",
                              start_date="2026-06-01", end_date="2026-06-05")
        repo.create_itinerary(user_id="u1", title="杭州3日游", destination="杭州",
                              start_date="2026-07-01", end_date="2026-07-03")
        repo.create_itinerary(user_id="u2", title="北京2日游", destination="北京",
                              start_date="2026-08-01", end_date="2026-08-02")

        items = repo.list_itineraries("u1")
        assert len(items) == 2
        items_u2 = repo.list_itineraries("u2")
        assert len(items_u2) == 1

    def test_update_itinerary(self):
        repo = ItineraryRepository()
        created = repo.create_itinerary(
            user_id="u1", title="成都5日游", destination="成都",
            start_date="2026-06-01", end_date="2026-06-05",
        )
        repo.update_itinerary(created.id, title="成都6日游", status="confirmed")
        updated = repo.get_itinerary(created.id)
        assert updated.title == "成都6日游"
        assert updated.status == "confirmed"

    def test_delete_itinerary(self):
        repo = ItineraryRepository()
        created = repo.create_itinerary(
            user_id="u1", title="成都5日游", destination="成都",
            start_date="2026-06-01", end_date="2026-06-05",
        )
        assert repo.delete_itinerary(created.id) is True
        assert repo.get_itinerary(created.id) is None

    def test_add_day_and_activity(self):
        repo = ItineraryRepository()
        created = repo.create_itinerary(
            user_id="u1", title="成都5日游", destination="成都",
            start_date="2026-06-01", end_date="2026-06-05",
        )
        day = repo.add_day(
            itinerary_id=created.id,
            day_index=0,
            date="2026-06-01",
            title="初识成都",
            summary="宽窄巷子+锦里",
        )
        assert day.id > 0
        assert day.title == "初识成都"

        act = repo.add_activity(
            day_id=day.id,
            activity_index=0,
            time_slot="09:00-11:00",
            title="宽窄巷子漫步",
            location="成都市青羊区宽窄巷子",
            description="感受老成都的悠闲时光",
            cost=0,
            tips="建议早到避开人流",
        )
        assert act.id > 0
        assert act.title == "宽窄巷子漫步"

        fetched = repo.get_itinerary(created.id)
        assert len(fetched.days) == 1
        assert len(fetched.days[0].activities) == 1
        assert fetched.days[0].activities[0].title == "宽窄巷子漫步"

    def test_check_in_activity(self):
        repo = ItineraryRepository()
        created = repo.create_itinerary(
            user_id="u1", title="成都5日游", destination="成都",
            start_date="2026-06-01", end_date="2026-06-05",
        )
        day = repo.add_day(itinerary_id=created.id, day_index=0)
        act = repo.add_activity(day_id=day.id, activity_index=0, title="测试活动")

        assert act.checked_in is False
        repo.check_in_activity(act.id)
        fetched = repo.get_activity(act.id)
        assert fetched.checked_in is True

        repo.uncheck_activity(act.id)
        fetched2 = repo.get_activity(act.id)
        assert fetched2.checked_in is False

    def test_delete_activity(self):
        repo = ItineraryRepository()
        created = repo.create_itinerary(
            user_id="u1", title="成都5日游", destination="成都",
            start_date="2026-06-01", end_date="2026-06-05",
        )
        day = repo.add_day(itinerary_id=created.id, day_index=0)
        act = repo.add_activity(day_id=day.id, activity_index=0, title="测试活动")

        assert repo.delete_activity(act.id) is True
        assert repo.get_activity(act.id) is None

    def test_save_full_itinerary(self):
        repo = ItineraryRepository()
        itinerary = Itinerary(
            user_id="u1",
            session_id="s1",
            title="成都3日游",
            destination="成都",
            start_date="2026-06-01",
            end_date="2026-06-03",
            budget="约3000元/人",
            status="confirmed",
            days=[
                DayPlan(
                    day_index=0,
                    date="2026-06-01",
                    title="初识成都",
                    summary="宽窄巷子+锦里",
                    activities=[
                        Activity(
                            activity_index=0,
                            time_slot="09:00-11:00",
                            title="宽窄巷子漫步",
                            location="成都市青羊区",
                            description="感受老成都",
                            cost=0,
                            tips="建议早到",
                        ),
                        Activity(
                            activity_index=1,
                            time_slot="14:00-17:00",
                            title="锦里古街",
                            location="成都市武侯区",
                            cost=0,
                        ),
                    ],
                ),
                DayPlan(
                    day_index=1,
                    date="2026-06-02",
                    title="大熊猫基地",
                    activities=[
                        Activity(
                            activity_index=0,
                            time_slot="08:00-12:00",
                            title="大熊猫繁育研究基地",
                            cost=55,
                        ),
                    ],
                ),
            ],
        )

        saved = repo.save_full_itinerary(itinerary)
        assert saved.id
        assert len(saved.days) == 2
        assert len(saved.days[0].activities) == 2
        assert len(saved.days[1].activities) == 1
        assert saved.days[0].activities[0].title == "宽窄巷子漫步"
        assert saved.days[1].activities[0].cost == 55

    def test_cascade_delete(self):
        repo = ItineraryRepository()
        created = repo.create_itinerary(
            user_id="u1", title="成都5日游", destination="成都",
            start_date="2026-06-01", end_date="2026-06-05",
        )
        day = repo.add_day(itinerary_id=created.id, day_index=0)
        act = repo.add_activity(day_id=day.id, activity_index=0, title="测试活动")

        repo.delete_itinerary(created.id)
        assert repo.get_activity(act.id) is None


class TestItinerarySchema:
    def test_itinerary_to_dict(self):
        itin = Itinerary(
            id="abc123",
            user_id="u1",
            title="成都5日游",
            destination="成都",
            start_date="2026-06-01",
            end_date="2026-06-05",
            days=[
                DayPlan(
                    id=1,
                    itinerary_id="abc123",
                    day_index=0,
                    date="2026-06-01",
                    title="Day 1",
                    activities=[
                        Activity(id=1, day_id=1, activity_index=0, title="景点A"),
                    ],
                ),
            ],
        )
        d = itin.to_dict()
        assert d["id"] == "abc123"
        assert len(d["days"]) == 1
        assert len(d["days"][0]["activities"]) == 1

        d2 = itin.to_list_dict()
        assert "days" not in d2

    def test_activity_from_row(self):
        act = Activity.from_row({
            "id": 1,
            "day_id": 2,
            "activity_index": 0,
            "time_slot": "09:00-11:00",
            "title": "测试",
            "location": "成都",
            "description": "描述",
            "image_url": "",
            "cost": 50,
            "tips": "贴士",
            "checked_in": 1,
        })
        assert act.checked_in is True
        assert act.cost == 50.0


class TestItineraryParserSimple:
    def test_parse_simple_basic(self):
        content = """第1天：初识成都
09:00-11:00 宽窄巷子漫步
14:00-17:00 锦里古街

第2天：大熊猫基地
08:00-12:00 大熊猫繁育研究基地
14:00-16:00 春熙路逛街"""

        result = ItineraryParser.parse_simple(content)
        assert result is not None
        assert len(result.days) == 2
        assert len(result.days[0].activities) == 2
        assert result.days[0].activities[0].title == "宽窄巷子漫步"
        assert result.days[0].activities[0].time_slot == "09:00-11:00"
        assert len(result.days[1].activities) == 2

    def test_parse_simple_day_format(self):
        content = """Day 1: 抵达杭州
10:00-12:00 西湖漫步
Day 2: 灵隐寺
08:00-11:00 灵隐寺祈福"""

        result = ItineraryParser.parse_simple(content)
        assert result is not None
        assert len(result.days) == 2

    def test_parse_simple_empty(self):
        result = ItineraryParser.parse_simple("")
        assert result is None

    def test_parse_simple_no_days(self):
        result = ItineraryParser.parse_simple("这是一段没有行程格式的文本")
        assert result is None

    def test_parse_simple_destination_extraction(self):
        content = """成都旅游行程
第1天：初识成都
09:00-11:00 宽窄巷子"""
        result = ItineraryParser.parse_simple(content)
        assert result is not None
        assert result.destination == "成都"
