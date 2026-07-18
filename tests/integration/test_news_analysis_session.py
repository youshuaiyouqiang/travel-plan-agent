"""Task 2 — 新闻研判锁定会话与热点只读 API 的集成测试。

覆盖范围：
- ``GET /api/v1/news/hotspots`` 只读缓存，不触发外部抓取
- ``POST /api/v1/news/hotspots/{news_id}/analysis-sessions`` 创建 ``news_analysis_locked`` 会话
- 未知 ``news_id`` 返回 404
- 未认证返回 401

业务红线：
- 新闻分析会话必须为 ``news_analysis_locked``、锁定 Agent 为 ``news``，并锚定 ``news_id``。
- ``GET /hotspots`` 只读缓存，严禁发起外部抓取。
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.middleware.auth import auth_middleware
from api.middleware.error_handler import claw_exception_handler, unhandled_exception_handler
from api.v1.news import router as news_router
from application.exceptions.base import ClawException
from application.news.hotspot_service import HotspotService
from application.news.models import NewsItem
from application.session.service import SessionService
from domain.user.auth.auth import UserStore
from domain.user.auth.token import generate_token
from infrastructure.persistence.database import init_db, reset_connection


# ---------------------------------------------------------------------------
# 共享 fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_news_analysis_session.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()


@dataclass
class FakeFetcher:
    items: list[NewsItem]
    calls: int = 0

    async def fetch(self, source) -> list[NewsItem]:
        self.calls += 1
        return list(self.items)


@pytest.fixture
def hotspot_service(db) -> HotspotService:
    from application.news.source_service import SourceService

    service = HotspotService(sources=SourceService(), fetcher=FakeFetcher(items=[]))
    # 预填充缓存供 GET /hotspots 和 POST analysis-sessions 使用
    service.repository.save_items(
        [
            NewsItem(
                id="news-1",
                title="测试热点",
                source="测试来源",
                url="https://example.com/news-1",
                summary="测试摘要",
            )
        ]
    )
    return service


@pytest.fixture
def user_and_token(db):
    store = UserStore()
    user = store.create("alice", "secret123")
    return user.user_id, generate_token(user.user_id)


@pytest_asyncio.fixture
async def app(db, hotspot_service, user_and_token):
    test_app = FastAPI()
    test_app.state.agent = None
    test_app.state.hotspot_service = hotspot_service
    test_app.state.session_service = SessionService(available_agent_ids={"travel", "academic"})
    test_app.middleware("http")(auth_middleware)
    test_app.add_exception_handler(ClawException, claw_exception_handler)
    test_app.add_exception_handler(Exception, unhandled_exception_handler)
    test_app.include_router(news_router, prefix="/api/v1/news")
    return test_app


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# GET /hotspots
# ---------------------------------------------------------------------------


class TestGetHotspots:
    @pytest.mark.asyncio
    async def test_get_hotspots_reads_cache_without_fetch(self, client, user_and_token, hotspot_service):
        user_id, token = user_and_token
        resp = await client.get("/api/v1/news/hotspots", headers=_bearer(token))
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert len(body["items"]) == 1
        assert body["items"][0]["id"] == "news-1"
        # GET /hotspots 不应触发外部抓取
        assert hotspot_service._fetcher.calls == 0

    @pytest.mark.asyncio
    async def test_get_hotspots_requires_auth(self, client):
        resp = await client.get("/api/v1/news/hotspots")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /hotspots/{news_id}/analysis-sessions
# ---------------------------------------------------------------------------


class TestCreateAnalysisSession:
    @pytest.mark.asyncio
    async def test_post_analysis_session_creates_locked_session(self, client, user_and_token):
        user_id, token = user_and_token
        resp = await client.post(
            "/api/v1/news/hotspots/news-1/analysis-sessions",
            headers=_bearer(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["mode"] == "news_analysis_locked"
        assert body["locked_agent_id"] == "news"
        assert body["news_id"] == "news-1"
        assert body["session_id"]

    @pytest.mark.asyncio
    async def test_post_analysis_session_404_for_unknown_news(self, client, user_and_token):
        _, token = user_and_token
        resp = await client.post(
            "/api/v1/news/hotspots/nonexistent/analysis-sessions",
            headers=_bearer(token),
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_post_analysis_session_requires_auth(self, client):
        resp = await client.post("/api/v1/news/hotspots/news-1/analysis-sessions")
        assert resp.status_code == 401
