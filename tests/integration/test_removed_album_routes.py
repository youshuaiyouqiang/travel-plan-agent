"""Task 3 验证相册相关路由已下线。

覆盖范围：
- ``/api/v1/album/...`` 文件服务路由返回 404
- ``/api/v1/itineraries/{id}/photos`` 及子路径返回 404
- ``/api/v1/itineraries/{id}/travelogue`` 返回 404
- 旧版 ``/api/album/...`` 前缀同样返回 404（向后兼容挂载也必须移除）

设计要点：相册已不属于产品范围；既有上传文件保留在受控存储中但不通过 HTTP 暴露。
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.middleware.auth import auth_middleware
from api.middleware.error_handler import yunhe_exception_handler, unhandled_exception_handler
from api.v1 import router as v1_router
from application.exceptions.base import YunheException
from domain.user.auth.auth import UserStore
from domain.user.auth.token import generate_token
from infrastructure.persistence.database import init_db, reset_connection


# ---------------------------------------------------------------------------
# 共享 fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_removed_album_routes.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()


@pytest_asyncio.fixture
async def app(db):
    """挂载完整 v1 路由聚合，验证相册路由在聚合层已被移除。"""
    test_app = FastAPI()
    # session 路由会读 app.state.agent，这里用 None 占位；本测试不触发那些路径。
    test_app.state.agent = None
    test_app.middleware("http")(auth_middleware)
    test_app.add_exception_handler(YunheException, yunhe_exception_handler)
    test_app.add_exception_handler(Exception, unhandled_exception_handler)
    test_app.include_router(v1_router, prefix="/api/v1")
    test_app.include_router(v1_router, prefix="/api")
    return test_app


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def token(db):
    store = UserStore()
    user = store.create("alice", "secret123")
    return generate_token(user.user_id)


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------


class TestAlbumRoutesRemoved:
    """相册与照片文件路由必须全部返回 404。"""

    @pytest.mark.asyncio
    async def test_album_serve_prefix_returns_404(self, client, token):
        # /api/v1/album/{file_path} 已下线
        response = await client.get("/api/v1/album/some/file.jpg", headers=_bearer(token))
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_album_root_returns_404(self, client, token):
        # 计划文档列出的代表性路径之一
        response = await client.get("/api/v1/album", headers=_bearer(token))
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_itinerary_album_subpath_returns_404(self, client, token):
        # /api/v1/itineraries/{id}/album 不存在
        response = await client.get("/api/v1/itineraries/i1/album", headers=_bearer(token))
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_photos_file_path_returns_404(self, client, token):
        # 旧版 /api/v1/photos/p1/file 已不存在
        response = await client.get("/api/v1/photos/p1/file", headers=_bearer(token))
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_itinerary_photos_endpoints_removed(self, client, token):
        # 所有 /itineraries/{id}/photos* 端点必须返回 404
        paths = [
            "/api/v1/itineraries/i1/photos",
            "/api/v1/itineraries/i1/photos/1",
            "/api/v1/itineraries/i1/photos/1/cover",
            "/api/v1/itineraries/i1/photos/map",
        ]
        for path in paths:
            response = await client.get(path, headers=_bearer(token))
            assert response.status_code == 404, f"{path} 应返回 404"

    @pytest.mark.asyncio
    async def test_travelogue_endpoint_removed(self, client, token):
        response = await client.post(
            "/api/v1/itineraries/i1/travelogue",
            headers=_bearer(token),
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_legacy_api_prefix_album_also_removed(self, client, token):
        # 旧前缀 /api/album/... 同样不能暴露
        response = await client.get("/api/album/legacy.jpg", headers=_bearer(token))
        assert response.status_code == 404
