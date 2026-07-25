"""Task 1 持久化会话模式与用户锁定 API 的集成测试。

覆盖范围：
- ``application.session.service.SessionService`` 的模式持久化与所有权校验
- ``POST /api/v1/sessions`` 接受 ``mode`` 与 ``locked_agent_id``，拒绝 ``news_analysis_locked``
- ``PATCH /api/v1/sessions/{session_id}/mode`` 仅允许 ``yunhe_default`` 或 ``agent_locked``，
  且对其他用户的会话返回 404
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.middleware.auth import auth_middleware
from api.middleware.error_handler import yunhe_exception_handler, unhandled_exception_handler
from api.v1.session import router as session_router
from application.exceptions import NotFoundException, ValidationException
from application.exceptions.base import YunheException
from application.session.schema import SessionRecord
from application.session.service import SessionService
from domain.user.auth.auth import UserStore
from domain.user.auth.token import generate_token
from infrastructure.persistence.database import init_db, reset_connection


# ---------------------------------------------------------------------------
# 共享 fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_session_modes.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()


@pytest.fixture
def service(db) -> SessionService:
    return SessionService(available_agent_ids={"travel", "academic"})


@pytest.fixture
def user_and_token(db):
    store = UserStore()
    user = store.create("alice", "secret123")
    token = generate_token(user.user_id)
    return user.user_id, token


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def app(db):
    test_app = FastAPI()
    test_app.state.session_service = SessionService(available_agent_ids={"travel", "academic"})
    # 现有 GET/DELETE /sessions 路由依赖 app.state.agent；本次 Task 不测试它们。
    test_app.state.agent = None
    test_app.middleware("http")(auth_middleware)
    test_app.add_exception_handler(YunheException, yunhe_exception_handler)
    test_app.add_exception_handler(Exception, unhandled_exception_handler)
    test_app.include_router(session_router, prefix="/api/v1/sessions")
    return test_app


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# 服务层测试
# ---------------------------------------------------------------------------


class TestSessionServiceModes:
    def test_create_default_session(self, service):
        session = service.create(user_id="u1", mode="yunhe_default")
        assert session.mode == "yunhe_default"
        assert session.locked_agent_id is None
        assert session.news_id is None
        assert session.user_id == "u1"
        assert session.session_id

    def test_news_locked_session_persists_lock_and_anchor(self, service):
        session = service.create(
            user_id="u1",
            mode="news_analysis_locked",
            locked_agent_id="news",
            news_id="news_123",
        )
        assert session.mode == "news_analysis_locked"
        assert session.locked_agent_id == "news"
        assert session.news_id == "news_123"

    def test_agent_locked_rejects_unavailable_agent(self, service):
        with pytest.raises(ValidationException):
            service.create(user_id="u1", mode="agent_locked", locked_agent_id="unknown")

    def test_agent_locked_accepts_available_agent(self, service):
        session = service.create(user_id="u1", mode="agent_locked", locked_agent_id="academic")
        assert session.mode == "agent_locked"
        assert session.locked_agent_id == "academic"

    def test_yunhe_default_rejects_stray_lock(self, service):
        with pytest.raises(ValidationException):
            service.create(
                user_id="u1",
                mode="yunhe_default",
                locked_agent_id="academic",
            )

    def test_require_owned_returns_session_for_owner(self, service):
        session = service.create(user_id="u1", mode="yunhe_default")
        fetched = service.require_owned(user_id="u1", session_id=session.session_id)
        assert isinstance(fetched, SessionRecord)
        assert fetched.session_id == session.session_id

    def test_require_owned_404_for_other_user(self, service):
        session = service.create(user_id="u1", mode="yunhe_default")
        with pytest.raises(NotFoundException):
            service.require_owned(user_id="u2", session_id=session.session_id)

    def test_require_owned_404_for_missing_session(self, service):
        with pytest.raises(NotFoundException):
            service.require_owned(user_id="u1", session_id="does-not-exist")

    def test_update_mode_to_agent_locked(self, service):
        session = service.create(user_id="u1", mode="yunhe_default")
        updated = service.update_mode(
            user_id="u1",
            session_id=session.session_id,
            mode="agent_locked",
            locked_agent_id="academic",
        )
        assert updated.mode == "agent_locked"
        assert updated.locked_agent_id == "academic"
        assert updated.news_id is None

        # 重新加载，确认持久化
        reloaded = service.require_owned(user_id="u1", session_id=session.session_id)
        assert reloaded.mode == "agent_locked"
        assert reloaded.locked_agent_id == "academic"

    def test_update_mode_back_to_yunhe_default(self, service):
        session = service.create(user_id="u1", mode="agent_locked", locked_agent_id="academic")
        updated = service.update_mode(
            user_id="u1",
            session_id=session.session_id,
            mode="yunhe_default",
        )
        assert updated.mode == "yunhe_default"
        assert updated.locked_agent_id is None
        assert updated.news_id is None

    def test_update_mode_rejects_news_analysis_locked(self, service):
        session = service.create(user_id="u1", mode="yunhe_default")
        with pytest.raises(ValidationException):
            service.update_mode(
                user_id="u1",
                session_id=session.session_id,
                mode="news_analysis_locked",
                locked_agent_id="news",
            )

    def test_update_mode_rejects_other_user(self, service):
        session = service.create(user_id="u1", mode="yunhe_default")
        with pytest.raises(NotFoundException):
            service.update_mode(
                user_id="u2",
                session_id=session.session_id,
                mode="agent_locked",
                locked_agent_id="academic",
            )


# ---------------------------------------------------------------------------
# API 层测试
# ---------------------------------------------------------------------------


class TestSessionModesAPI:
    @pytest.mark.asyncio
    async def test_unauthenticated_request_rejected(self, client):
        response = await client.post("/api/v1/sessions")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_post_sessions_creates_default_mode(self, client, user_and_token):
        _, token = user_and_token
        response = await client.post("/api/v1/sessions", headers=_bearer(token))
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["mode"] == "yunhe_default"
        assert data["locked_agent_id"] is None
        assert data["news_id"] is None
        assert data["session_id"]
        assert data["user_id"]

    @pytest.mark.asyncio
    async def test_user_can_lock_only_an_available_agent(self, client, user_and_token):
        _, token = user_and_token
        response = await client.post(
            "/api/v1/sessions",
            headers=_bearer(token),
            json={"mode": "agent_locked", "locked_agent_id": "academic"},
        )
        assert response.status_code == 201
        assert response.json()["data"]["locked_agent_id"] == "academic"
        assert response.json()["data"]["mode"] == "agent_locked"

    @pytest.mark.asyncio
    async def test_user_cannot_lock_unknown_agent(self, client, user_and_token):
        _, token = user_and_token
        response = await client.post(
            "/api/v1/sessions",
            headers=_bearer(token),
            json={"mode": "agent_locked", "locked_agent_id": "unknown"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_user_cannot_create_news_analysis_locked(self, client, user_and_token):
        _, token = user_and_token
        response = await client.post(
            "/api/v1/sessions",
            headers=_bearer(token),
            json={"mode": "news_analysis_locked"},
        )
        # Pydantic Literal 校验会直接拒绝，FastAPI 默认 422
        assert response.status_code in (400, 422)

    @pytest.mark.asyncio
    async def test_post_sessions_rejects_news_id_in_body(self, client, user_and_token):
        _, token = user_and_token
        response = await client.post(
            "/api/v1/sessions",
            headers=_bearer(token),
            json={"mode": "yunhe_default", "news_id": "news_123"},
        )
        # extra="forbid" 拒绝多余字段
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_patch_mode_locks_to_agent(self, client, user_and_token):
        _, token = user_and_token
        create_resp = await client.post("/api/v1/sessions", headers=_bearer(token))
        session_id = create_resp.json()["data"]["session_id"]

        response = await client.patch(
            f"/api/v1/sessions/{session_id}/mode",
            headers=_bearer(token),
            json={"mode": "agent_locked", "locked_agent_id": "travel"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["mode"] == "agent_locked"
        assert response.json()["data"]["locked_agent_id"] == "travel"

    @pytest.mark.asyncio
    async def test_patch_mode_back_to_yunhe_default(self, client, user_and_token):
        _, token = user_and_token
        create_resp = await client.post(
            "/api/v1/sessions",
            headers=_bearer(token),
            json={"mode": "agent_locked", "locked_agent_id": "academic"},
        )
        session_id = create_resp.json()["data"]["session_id"]

        response = await client.patch(
            f"/api/v1/sessions/{session_id}/mode",
            headers=_bearer(token),
            json={"mode": "yunhe_default"},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["mode"] == "yunhe_default"
        assert data["locked_agent_id"] is None
        assert data["news_id"] is None

    @pytest.mark.asyncio
    async def test_patch_mode_rejects_news_analysis_locked(self, client, user_and_token):
        _, token = user_and_token
        create_resp = await client.post("/api/v1/sessions", headers=_bearer(token))
        session_id = create_resp.json()["data"]["session_id"]

        response = await client.patch(
            f"/api/v1/sessions/{session_id}/mode",
            headers=_bearer(token),
            json={"mode": "news_analysis_locked"},
        )
        assert response.status_code in (400, 422)

    @pytest.mark.asyncio
    async def test_patch_mode_rejects_unknown_agent(self, client, user_and_token):
        _, token = user_and_token
        create_resp = await client.post("/api/v1/sessions", headers=_bearer(token))
        session_id = create_resp.json()["data"]["session_id"]

        response = await client.patch(
            f"/api/v1/sessions/{session_id}/mode",
            headers=_bearer(token),
            json={"mode": "agent_locked", "locked_agent_id": "ghost"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_patch_mode_rejects_other_users_session(self, client, user_and_token, db):
        _, token = user_and_token
        # 另一个用户创建会话
        store = UserStore()
        other = store.create("bob", "secret123")
        other_service = SessionService(available_agent_ids={"travel", "academic"})
        other_session = other_service.create(user_id=other.user_id, mode="yunhe_default")

        response = await client.patch(
            f"/api/v1/sessions/{other_session.session_id}/mode",
            headers=_bearer(token),
            json={"mode": "agent_locked", "locked_agent_id": "travel"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_patch_mode_rejects_extra_fields(self, client, user_and_token):
        _, token = user_and_token
        create_resp = await client.post("/api/v1/sessions", headers=_bearer(token))
        session_id = create_resp.json()["data"]["session_id"]

        response = await client.patch(
            f"/api/v1/sessions/{session_id}/mode",
            headers=_bearer(token),
            json={"mode": "yunhe_default", "news_id": "news_x"},
        )
        assert response.status_code == 422
