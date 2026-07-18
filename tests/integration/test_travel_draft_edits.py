"""Task 2 手工编辑保护与显式刷新的集成测试。

覆盖范围：
- ``application.travel.service.TravelService.edit_activity`` 标记手工字段
- ``application.travel.service.TravelService.apply_agent_proposal`` 保护手工字段并记录冲突
- ``PATCH /api/v1/travel/drafts/{draft_id}/activities/{activity_id}`` 的认证、所有权与 extra=forbid

业务红线：Agent 不能覆盖手动编辑字段，除非用户在冲突界面明确应用变更。
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.middleware.auth import auth_middleware
from api.middleware.error_handler import claw_exception_handler, unhandled_exception_handler
from api.v1.travel import router as travel_router
from application.exceptions import NotFoundException
from application.exceptions.base import ClawException
from application.travel.service import TravelService
from domain.user.auth.auth import UserStore
from domain.user.auth.token import generate_token
from infrastructure.persistence.database import init_db, reset_connection


# ---------------------------------------------------------------------------
# 共享 fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_travel_draft_edits.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()


@pytest.fixture
def service(db) -> TravelService:
    return TravelService()


@pytest.fixture
def user_and_token(db):
    store = UserStore()
    user = store.create("alice", "secret123")
    token = generate_token(user.user_id)
    return user.user_id, token


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def sample_plan() -> dict:
    """最小可用的行程草稿内容。"""
    return {
        "title": "京都三日游",
        "destination": "京都",
        "days": [
            {
                "day_index": 1,
                "date": "2026-08-01",
                "activities": [
                    {"id": "a1", "title": "清水寺", "time_slot": "上午", "location": "清水道"},
                ],
            },
        ],
    }


def proposal_with_new_title() -> dict:
    """Agent 提议：覆盖 a1 的标题与地点。"""
    return {
        "activities": [
            {"id": "a1", "title": "Agent 推荐的新景点", "location": "Agent 推荐的新地点"},
        ]
    }


@pytest_asyncio.fixture
async def app(db):
    test_app = FastAPI()
    test_app.state.travel_service = TravelService()
    test_app.middleware("http")(auth_middleware)
    test_app.add_exception_handler(ClawException, claw_exception_handler)
    test_app.add_exception_handler(Exception, unhandled_exception_handler)
    test_app.include_router(travel_router, prefix="/api/v1/travel")
    return test_app


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# 服务层：手工编辑保护
# ---------------------------------------------------------------------------


class TestManualEditProtection:
    def test_edit_activity_updates_value(self, service):
        draft = service.save_draft("u1", "s1", sample_plan())
        updated = service.edit_activity("u1", draft.id, "a1", title="用户选定的博物馆")
        assert updated.activity("a1").title == "用户选定的博物馆"

    def test_edit_activity_marks_field_as_manual(self, service):
        draft = service.save_draft("u1", "s1", sample_plan())
        service.edit_activity("u1", draft.id, "a1", title="用户选定的博物馆")
        reloaded = service.require_owned_draft("u1", draft.id)
        assert "a1.title" in reloaded.manual_edit_fields

    def test_agent_proposal_preserves_manual_fields(self, service):
        draft = service.save_draft("u1", "s1", sample_plan())
        service.edit_activity("u1", draft.id, "a1", title="用户选定的博物馆")
        result = service.apply_agent_proposal("u1", draft.id, proposal_with_new_title())
        assert result.activity("a1").title == "用户选定的博物馆"
        assert result.conflicts[0].activity_id == "a1"
        assert result.conflicts[0].fields == {"title"}

    def test_agent_proposal_applies_non_manual_fields(self, service):
        draft = service.save_draft("u1", "s1", sample_plan())
        # 未手工编辑任何字段：Agent 提议应全部应用
        result = service.apply_agent_proposal("u1", draft.id, proposal_with_new_title())
        assert result.activity("a1").title == "Agent 推荐的新景点"
        assert result.activity("a1").location == "Agent 推荐的新地点"
        assert result.conflicts == []

    def test_edit_activity_rejects_other_user(self, service):
        draft = service.save_draft("u1", "s1", sample_plan())
        with pytest.raises(NotFoundException):
            service.edit_activity("u2", draft.id, "a1", title="x")


# ---------------------------------------------------------------------------
# API 层：PATCH 活动
# ---------------------------------------------------------------------------


class TestTravelDraftEditsAPI:
    @pytest.mark.asyncio
    async def test_patch_activity_unauthenticated(self, client, user_and_token):
        _, token = user_and_token
        # 先创建草稿（需要认证），再以无 token 调 PATCH
        create_resp = await client.post(
            "/api/v1/travel/drafts",
            headers=_bearer(token),
            json={"session_id": "s1", "plan": sample_plan()},
        )
        draft_id = create_resp.json()["data"]["id"]
        response = await client.patch(
            f"/api/v1/travel/drafts/{draft_id}/activities/a1",
            json={"title": "新标题"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_patch_activity_success(self, client, user_and_token):
        _, token = user_and_token
        create_resp = await client.post(
            "/api/v1/travel/drafts",
            headers=_bearer(token),
            json={"session_id": "s1", "plan": sample_plan()},
        )
        draft_id = create_resp.json()["data"]["id"]

        response = await client.patch(
            f"/api/v1/travel/drafts/{draft_id}/activities/a1",
            headers=_bearer(token),
            json={"title": "用户选定的博物馆"},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["manual_edit_fields"] == ["a1.title"]

    @pytest.mark.asyncio
    async def test_patch_activity_rejects_other_user(self, client, user_and_token, db):
        _, token = user_and_token
        # 另一个用户创建草稿
        store = UserStore()
        other = store.create("bob", "secret123")
        other_service = TravelService()
        other_draft = other_service.save_draft(other.user_id, "s1", sample_plan())

        response = await client.patch(
            f"/api/v1/travel/drafts/{other_draft.id}/activities/a1",
            headers=_bearer(token),
            json={"title": "x"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_patch_activity_rejects_extra_fields(self, client, user_and_token):
        _, token = user_and_token
        create_resp = await client.post(
            "/api/v1/travel/drafts",
            headers=_bearer(token),
            json={"session_id": "s1", "plan": sample_plan()},
        )
        draft_id = create_resp.json()["data"]["id"]

        response = await client.patch(
            f"/api/v1/travel/drafts/{draft_id}/activities/a1",
            headers=_bearer(token),
            json={"title": "x", "evil": "inject"},
        )
        assert response.status_code == 422
