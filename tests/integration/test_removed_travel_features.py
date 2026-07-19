"""Task 3 — 已移除的旅行功能（比较、相册、打卡、实际费用）不再暴露。

覆盖范围：
- ``POST /api/v1/itineraries/compare`` 不再暴露（404）
- 相册域代码 ``domain/travel/album/`` 与前端 ``components/album/`` 已删除
- ``ComparePage`` / ``AlbumPage`` / ``useAlbumStore`` 已删除
- P1-1：打卡、实际费用、``checked_in`` 字段从后端、领域模型与数据库契约中完全移除

业务红线：不新增或恢复相册、游记、行程比较、打卡、实际费用、预订或支付流程。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.middleware.auth import auth_middleware
from api.middleware.error_handler import claw_exception_handler, unhandled_exception_handler
from api.v1.itinerary import router as itinerary_router
from application.exceptions.base import ClawException
from domain.user.auth.auth import UserStore
from domain.user.auth.token import generate_token
from infrastructure.persistence.database import get_connection, init_db, reset_connection


# ---------------------------------------------------------------------------
# 共享 fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_removed_travel.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()


@pytest.fixture
def user_and_token(db):
    store = UserStore()
    user = store.create("alice", "secret123")
    return user.user_id, generate_token(user.user_id)


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def app(db):
    test_app = FastAPI()
    test_app.state.agent = None
    test_app.middleware("http")(auth_middleware)
    test_app.add_exception_handler(ClawException, claw_exception_handler)
    test_app.add_exception_handler(Exception, unhandled_exception_handler)
    test_app.include_router(itinerary_router, prefix="/api/v1/itineraries")
    return test_app


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# 比较端点已下线
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compare_route_is_not_exposed(client, user_and_token):
    _, token = user_and_token
    response = await client.post(
        "/api/v1/itineraries/compare",
        headers=_bearer(token),
        json={"ids": ["a", "b"]},
    )
    # FastAPI 可能将 /compare 匹配到 /{itinerary_id} 路径参数并返回 405，
    # 也可能直接返回 404；两者都表明 compare 端点不再暴露。
    assert response.status_code in (404, 405)


# ---------------------------------------------------------------------------
# 相册与比较实现已删除
# ---------------------------------------------------------------------------


def test_travel_album_implementation_is_removed():
    assert not Path("domain/travel/album").exists()
    assert not Path("frontend/src/components/album").exists()


def test_compare_page_and_album_page_are_removed():
    assert not Path("frontend/src/pages/ComparePage.tsx").exists()
    assert not Path("frontend/src/pages/AlbumPage.tsx").exists()


def test_album_store_is_removed():
    assert not Path("frontend/src/hooks/useAlbumStore.ts").exists()


# ---------------------------------------------------------------------------
# P1-1：打卡、实际费用、checked_in 从领域模型与数据库契约中完全移除
# ---------------------------------------------------------------------------


def test_itinerary_repository_does_not_expose_checkin_or_actual_cost():
    """P1-1: ItineraryRepository 不得再暴露打卡/实际费用相关方法。"""
    from domain.travel.itinerary.repository import ItineraryRepository

    repo = ItineraryRepository()
    for forbidden in ("check_in_activity", "uncheck_activity", "update_actual_cost"):
        assert hasattr(repo, forbidden) is False, (
            f"ItineraryRepository 仍暴露已下线方法: {forbidden}"
        )


def test_activity_schema_does_not_carry_checkin_or_actual_cost():
    """P1-1: Activity dataclass 不得再持有 actual_cost / checked_in 字段。"""
    from domain.travel.itinerary.schema import Activity

    sample = Activity(id=1, day_id=1, activity_index=0, title="测试")
    serialised = sample.to_dict()
    assert "actual_cost" not in serialised
    assert "checked_in" not in serialised
    assert not hasattr(sample, "actual_cost")
    assert not hasattr(sample, "checked_in")


def test_itinerary_activities_table_has_no_checkin_or_actual_cost_columns(db):
    """P1-1: itinerary_activities 表不得包含 actual_cost / checked_in 列。"""
    conn = get_connection()
    cols = {row[1] for row in conn.execute("PRAGMA table_info(itinerary_activities)").fetchall()}
    assert "actual_cost" not in cols, "itinerary_activities 仍包含 actual_cost 列"
    assert "checked_in" not in cols, "itinerary_activities 仍包含 checked_in 列"
    # 必要字段保留
    assert {"id", "day_id", "activity_index", "title", "cost"} <= cols


def test_add_activity_does_not_reference_checked_in_column(db):
    """P1-1: ItineraryRepository.add_activity 不得在 SQL 中引用 checked_in 列。"""
    from domain.travel.itinerary.repository import ItineraryRepository

    repo = ItineraryRepository()
    created = repo.create_itinerary(
        user_id="u1",
        title="成都3日游",
        destination="成都",
        start_date="2026-06-01",
        end_date="2026-06-03",
    )
    day = repo.add_day(itinerary_id=created.id, day_index=0)
    # add_activity 在没有 checked_in 列的情况下必须成功
    act = repo.add_activity(day_id=day.id, activity_index=0, title="测试活动", cost=20)
    assert act.id > 0
    fetched = repo.get_activity(act.id)
    assert fetched is not None
    assert fetched.title == "测试活动"
    assert fetched.cost == 20.0


def test_dead_itinerary_components_are_removed():
    """P1-1: 与打卡/实际费用耦合的前端死代码组件必须删除。"""
    base = Path("frontend/src/components/itinerary")
    for forbidden in ("ActivityCard.tsx", "DayCarousel.tsx", "DayBlind.tsx", "BlindSlat.tsx"):
        assert not (base / forbidden).exists(), f"死代码组件未删除: {forbidden}"


def test_travel_api_activity_data_does_not_carry_checkin_fields():
    """P1-1: 前端 ActivityData 类型不得包含 actual_cost / checked_in 字段。"""
    src = Path("frontend/src/features/travel/api.ts").read_text(encoding="utf-8")
    # 类型定义块中不应再声明这两个字段
    assert "actual_cost" not in src, "features/travel/api.ts 仍包含 actual_cost"
    assert "checked_in" not in src, "features/travel/api.ts 仍包含 checked_in"
