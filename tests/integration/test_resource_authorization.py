"""Task 2 集中资源授权并关闭 IDOR 的集成测试。

覆盖范围：
- 行程读取/更新/删除的对象级授权（跨用户访问统一 404，不泄漏存在性）
- 活动删除的对象级授权（checkin / 实际花费端点已在 travel 计划中下线，不再测试）
- 分享链接列表与删除的对象级授权
- 会话方案确认/撤销/查询的对象级授权
- debug 路由对他人 session 数据的访问控制

设计要点：双用户场景（owner 与 other），所有越权访问必须返回 404。
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.middleware.auth import auth_middleware
from api.middleware.error_handler import yunhe_exception_handler, unhandled_exception_handler
from api.v1.debug import router as debug_router
from api.v1.itinerary import router as itinerary_router
from api.v1.session import confirm_router as session_confirm_router
from api.v1.session import router as session_router
from application.exceptions.base import YunheException
from application.session.service import SessionService
from domain.travel.itinerary.repository import ItineraryRepository
from domain.user.auth.auth import UserStore
from domain.user.auth.token import generate_token
from infrastructure.persistence.database import init_db, reset_connection


# ---------------------------------------------------------------------------
# 共享 fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_resource_authorization.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()


@pytest_asyncio.fixture
async def app(db):
    """挂载 itinerary / session / confirm / debug 路由的最小 FastAPI 应用。"""
    test_app = FastAPI()
    test_app.state.session_service = SessionService(available_agent_ids={"travel", "academic"})
    # debug 路由依赖 app.state.agent；本测试用 None 占位，断言在到达 agent 之前就被授权层拦截。
    test_app.state.agent = None
    test_app.middleware("http")(auth_middleware)
    test_app.add_exception_handler(YunheException, yunhe_exception_handler)
    test_app.add_exception_handler(Exception, unhandled_exception_handler)
    test_app.include_router(itinerary_router, prefix="/api/v1/itineraries")
    test_app.include_router(session_router, prefix="/api/v1/sessions")
    test_app.include_router(session_confirm_router, prefix="/api/v1/session")
    test_app.include_router(debug_router, prefix="/api/v1/debug")
    return test_app


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def users(db):
    """创建 owner 与 other 两个真实用户，并返回各自 user_id 与 token。"""
    store = UserStore()
    owner = store.create("owner", "secret123")
    other = store.create("other", "secret123")
    return {
        "owner": {"user_id": owner.user_id, "token": generate_token(owner.user_id)},
        "other": {"user_id": other.user_id, "token": generate_token(other.user_id)},
    }


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def owner_itinerary(db, users):
    """owner 名下的一行程 + 一活动，用于越权测试。"""
    repo = ItineraryRepository()
    itin = repo.create_itinerary(
        user_id=users["owner"]["user_id"],
        title="owner 的成都行程",
        destination="成都",
        start_date="2026-08-01",
        end_date="2026-08-03",
        session_id="",
    )
    day = repo.add_day(itinerary_id=itin.id, day_index=0, date="2026-08-01", title="Day 1")
    act = repo.add_activity(
        day_id=day.id,
        activity_index=0,
        time_slot="09:00-11:00",
        title="宽窄巷子",
        location="成都",
        cost=0,
    )
    return {"itinerary_id": itin.id, "day_id": day.id, "activity_id": act.id}


@pytest.fixture
def owner_share_link(db, users, owner_itinerary):
    """owner 名下行程的分享链接。"""
    repo = ItineraryRepository()
    token = repo.create_share_link(
        itinerary_id=owner_itinerary["itinerary_id"],
        user_id=users["owner"]["user_id"],
    )
    return token


@pytest.fixture
def owner_session(db, users):
    """owner 名下的会话，用于会话确认越权测试。"""
    service = SessionService(available_agent_ids={"travel", "academic"})
    record = service.create(user_id=users["owner"]["user_id"], mode="yunhe_default")
    return record.session_id


# ---------------------------------------------------------------------------
# 行程资源 IDOR
# ---------------------------------------------------------------------------


class TestItineraryAuthorization:
    @pytest.mark.asyncio
    async def test_other_user_cannot_read_itinerary(self, client, users, owner_itinerary):
        response = await client.get(
            f"/api/v1/itineraries/{owner_itinerary['itinerary_id']}",
            headers=_bearer(users["other"]["token"]),
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_other_user_cannot_update_itinerary(self, client, users, owner_itinerary):
        response = await client.put(
            f"/api/v1/itineraries/{owner_itinerary['itinerary_id']}",
            headers={**_bearer(users["other"]["token"]), "Content-Type": "application/json"},
            json={"title": "hijacked"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_other_user_cannot_delete_itinerary(self, client, users, owner_itinerary):
        response = await client.delete(
            f"/api/v1/itineraries/{owner_itinerary['itinerary_id']}",
            headers=_bearer(users["other"]["token"]),
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_owner_can_read_own_itinerary(self, client, users, owner_itinerary):
        response = await client.get(
            f"/api/v1/itineraries/{owner_itinerary['itinerary_id']}",
            headers=_bearer(users["owner"]["token"]),
        )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# 活动资源 IDOR
# ---------------------------------------------------------------------------


class TestActivityAuthorization:
    @pytest.mark.asyncio
    async def test_other_user_cannot_delete_activity(self, client, users, owner_itinerary):
        response = await client.delete(
            f"/api/v1/itineraries/{owner_itinerary['itinerary_id']}"
            f"/activities/{owner_itinerary['activity_id']}",
            headers=_bearer(users["other"]["token"]),
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# 分享链接 IDOR
# ---------------------------------------------------------------------------


class TestShareLinkAuthorization:
    @pytest.mark.asyncio
    async def test_other_user_cannot_list_share_links(self, client, users, owner_itinerary):
        response = await client.get(
            f"/api/v1/itineraries/{owner_itinerary['itinerary_id']}/shares",
            headers=_bearer(users["other"]["token"]),
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_other_user_cannot_delete_share_link(
        self, client, users, owner_itinerary, owner_share_link
    ):
        response = await client.delete(
            f"/api/v1/itineraries/{owner_itinerary['itinerary_id']}/shares/{owner_share_link}",
            headers=_bearer(users["other"]["token"]),
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_other_user_cannot_create_share_link(self, client, users, owner_itinerary):
        response = await client.post(
            f"/api/v1/itineraries/{owner_itinerary['itinerary_id']}/share",
            headers={**_bearer(users["other"]["token"]), "Content-Type": "application/json"},
            json={},
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# 会话确认 IDOR
# ---------------------------------------------------------------------------


class TestSessionConfirmAuthorization:
    @pytest.mark.asyncio
    async def test_other_user_cannot_confirm_plan(self, client, users, owner_session):
        response = await client.post(
            f"/api/v1/session/{owner_session}/confirm-plan",
            headers={**_bearer(users["other"]["token"]), "Content-Type": "application/json"},
            json={"plan_type": "sightseeing", "itinerary_id": ""},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_other_user_cannot_revoke_confirm(self, client, users, owner_session, db):
        # 先以 owner 身份确认，再让 other 尝试撤销
        await client.post(
            f"/api/v1/session/{owner_session}/confirm-plan",
            headers={**_bearer(users["owner"]["token"]), "Content-Type": "application/json"},
            json={"plan_type": "sightseeing", "itinerary_id": ""},
        )
        response = await client.post(
            f"/api/v1/session/{owner_session}/revoke-confirm",
            headers={**_bearer(users["other"]["token"]), "Content-Type": "application/json"},
            json={"itinerary_id": ""},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_other_user_cannot_view_confirm_status(self, client, users, owner_session):
        response = await client.get(
            f"/api/v1/session/{owner_session}/confirm-status",
            headers=_bearer(users["other"]["token"]),
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# debug 路由 IDOR
# ---------------------------------------------------------------------------


class TestDebugAuthorization:
    @pytest.mark.asyncio
    async def test_debug_requires_auth(self, client, owner_session):
        # 无 token 不应放行（debug 路由当前在 auth_middleware 中被列为 public）
        response = await client.get(f"/api/v1/debug/trace/{owner_session}")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_other_user_cannot_view_debug_trace(self, client, users, owner_session):
        response = await client.get(
            f"/api/v1/debug/trace/{owner_session}",
            headers=_bearer(users["other"]["token"]),
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_other_user_cannot_view_debug_session(self, client, users, owner_session):
        response = await client.get(
            f"/api/v1/debug/session/{owner_session}",
            headers=_bearer(users["other"]["token"]),
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_other_user_cannot_view_debug_task(self, client, users, owner_session):
        response = await client.get(
            f"/api/v1/debug/task/{owner_session}",
            headers=_bearer(users["other"]["token"]),
        )
        assert response.status_code == 404
