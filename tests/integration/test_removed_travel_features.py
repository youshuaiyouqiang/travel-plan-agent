"""Task 3 — 已移除的旅行功能（比较、相册、打卡、实际费用）不再暴露。

覆盖范围：
- ``POST /api/v1/itineraries/compare`` 不再暴露（404）
- 相册域代码 ``domain/travel/album/`` 与前端 ``components/album/`` 已删除
- ``ComparePage`` / ``AlbumPage`` / ``useAlbumStore`` 已删除

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
from infrastructure.persistence.database import init_db, reset_connection


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
