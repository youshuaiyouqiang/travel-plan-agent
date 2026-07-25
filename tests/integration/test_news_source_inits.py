"""新闻来源初始化事件集成测试。

覆盖：
- ``SourceService.register_builtin_whitelist`` 幂等
- ``SourceService.list_inits`` 列出初始化事件
- ``GET /api/v1/admin/news/source-inits`` 仅管理员可访问（普通用户 403）
- ``POST /api/v1/admin/news/sources/register-builtin`` 仅管理员可访问
- 重复注册同 domain 不创建新 Source，但每次都写一条 init 事件
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.middleware.auth import auth_middleware
from api.middleware.error_handler import (
    unhandled_exception_handler,
    yunhe_exception_handler,
)
from api.v1.admin_news import router as admin_news_router
from application.exceptions.base import YunheException
from application.news.models import NewsSourceInit
from application.news.source_service import BUILTIN_WHITELIST, SourceService
from config import settings
from domain.user.auth.auth import UserStore
from domain.user.auth.token import generate_token
from infrastructure.persistence.database import init_db, reset_connection


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_news_source_inits.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()


@pytest.fixture
def admin_user(db, monkeypatch):
    monkeypatch.setattr(settings, "admin_username", "admin")
    store = UserStore()
    return store.create("admin", "secret123")


@pytest.fixture
def regular_user(db):
    store = UserStore()
    return store.create("alice", "secret123")


@pytest.fixture
def admin_token(admin_user) -> str:
    return generate_token(admin_user.user_id)


@pytest.fixture
def user_token(regular_user) -> str:
    return generate_token(regular_user.user_id)


@pytest_asyncio.fixture
async def app_with_admin(db, admin_user):
    app = FastAPI()
    app.middleware("http")(auth_middleware)
    app.add_exception_handler(YunheException, yunhe_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.include_router(admin_news_router, prefix="/api/v1/admin/news")
    app.state.admin_user_id = admin_user.user_id
    app.state.user_id = admin_user.user_id
    return app


# ---------------------------------------------------------------------------
# SourceService — register_builtin_whitelist
# ---------------------------------------------------------------------------


class TestRegisterBuiltinWhitelist:
    def test_creates_new_source(self, db):
        service = SourceService()
        src = service.register_builtin_whitelist(
            domain="new.example", name="New Source", tier="mainstream"
        )
        assert src.status == "enabled"
        assert src.scoring_mode == "builtin_whitelist"
        assert src.ai_score is None
        assert src.ai_reason == "产品内置白名单"
        assert src.ai_subscores == "{}"
        assert src.tier == "mainstream"
        # init 事件已写
        inits = service.list_inits()
        assert len(inits) == 1
        assert inits[0].source_id == src.id
        assert inits[0].scoring_mode == "builtin_whitelist"
        assert inits[0].tier == "mainstream"
        assert isinstance(inits[0], NewsSourceInit)

    def test_idempotent_returns_existing_source(self, db):
        service = SourceService()
        first = service.register_builtin_whitelist(
            domain="dup.example", name="Dup", tier="mainstream"
        )
        second = service.register_builtin_whitelist(
            domain="dup.example", name="Dup Renamed", tier="aggregator"
        )
        assert second.id == first.id
        # 字段被覆盖到正确状态
        assert second.tier == "aggregator"
        assert second.scoring_mode == "builtin_whitelist"
        assert second.ai_score is None
        # 但每次都写一条 init 事件，便于审计重注册动作
        inits = service.list_inits()
        assert len(inits) == 2
        assert all(i.source_id == first.id for i in inits)

    def test_recovers_existing_legacy_source(self, db):
        """模拟旧版数据：scoring_mode='ai_candidate'、tier='unknown'、ai_score=0.9。

        register_builtin_whitelist 应能将其拉回 builtin_whitelist 的正确状态。
        """
        from application.news.models import Source

        service = SourceService()
        # 旧版脏数据
        legacy = Source(
            id="legacy-1",
            name="legacy",
            domain="legacy.example",
            tier="unknown",
            status="enabled",
            scoring_mode="ai_candidate",
            ai_score=0.9,
            ai_reason="内置默认热搜来源",
            ai_subscores="{}",
            created_at="2026-07-19T00:00:00+00:00",
            updated_at="2026-07-19T00:00:00+00:00",
        )
        service._repo.insert_source(legacy)

        fixed = service.register_builtin_whitelist(
            domain="legacy.example", name="legacy", tier="mainstream"
        )
        assert fixed.id == "legacy-1"
        assert fixed.scoring_mode == "builtin_whitelist"
        assert fixed.tier == "mainstream"
        assert fixed.ai_score is None
        assert fixed.ai_reason == "产品内置白名单"

    def test_builtin_whitelist_constant_is_nonempty(self, db):
        """内置白名单常量必须有内容（产品约束）。"""
        assert len(BUILTIN_WHITELIST) >= 1
        for domain, name, tier in BUILTIN_WHITELIST:
            assert domain and name and tier in {
                "mainstream",
                "aggregator",
                "official",
            }


# ---------------------------------------------------------------------------
# API — /admin/news/source-inits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSourceInitsApi:
    async def test_admin_can_list_inits(self, app_with_admin, admin_token):
        # 先注册一个内置来源
        service = SourceService()
        service.register_builtin_whitelist(
            domain="api-test.example", name="API Test", tier="mainstream"
        )

        async with AsyncClient(
            transport=ASGITransport(app=app_with_admin),
            base_url="http://test",
        ) as client:
            # 模拟 cookie + CSRF：直接调用 bearer token 走 auth 中间件
            res = await client.get(
                "/api/v1/admin/news/source-inits",
                cookies={"auth_token": admin_token},
            )
        assert res.status_code == 200, res.text
        data = res.json()
        assert "items" in data
        assert len(data["items"]) >= 1
        first = data["items"][0]
        assert first["domain"] == "api-test.example"
        assert first["scoring_mode"] == "builtin_whitelist"

    async def test_regular_user_gets_403(self, app_with_admin, user_token):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_admin),
            base_url="http://test",
        ) as client:
            res = await client.get(
                "/api/v1/admin/news/source-inits",
                cookies={"auth_token": user_token},
            )
        assert res.status_code == 403


# ---------------------------------------------------------------------------
# API — /admin/news/sources/register-builtin
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRegisterBuiltinApi:
    @pytest.mark.asyncio
    async def test_admin_can_register(self, app_with_admin, admin_token):
        # POST 必须走 Bearer（cookie 模式需要 CSRF）；与 test_news_admin_api.py 一致
        app_with_admin.state.user_id = admin_token  # 仅占位
        async with AsyncClient(
            transport=ASGITransport(app=app_with_admin),
            base_url="http://test",
        ) as client:
            res = await client.post(
                "/api/v1/admin/news/sources/register-builtin",
                json={
                    "domain": "via-api.example",
                    "name": "Via API",
                    "tier": "mainstream",
                },
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["domain"] == "via-api.example"
        assert body["scoring_mode"] == "builtin_whitelist"
        assert body["tier"] == "mainstream"
        assert body["ai_score"] is None
        assert body["ai_reason"] == "产品内置白名单"

    @pytest.mark.asyncio
    async def test_regular_user_gets_403(self, app_with_admin, user_token):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_admin),
            base_url="http://test",
        ) as client:
            res = await client.post(
                "/api/v1/admin/news/sources/register-builtin",
                json={
                    "domain": "blocked.example",
                    "name": "Blocked",
                    "tier": "mainstream",
                },
                headers={"Authorization": f"Bearer {user_token}"},
            )
        assert res.status_code == 403

    @pytest.mark.asyncio
    async def test_invalid_tier_returns_422(self, app_with_admin, admin_token):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_admin),
            base_url="http://test",
        ) as client:
            res = await client.post(
                "/api/v1/admin/news/sources/register-builtin",
                json={
                    "domain": "bad.example",
                    "name": "Bad",
                    "tier": "not-a-tier",  # type: ignore[arg-type]
                },
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert res.status_code == 422

    @pytest.mark.asyncio
    async def test_extra_fields_rejected(self, app_with_admin, admin_token):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_admin),
            base_url="http://test",
        ) as client:
            res = await client.post(
                "/api/v1/admin/news/sources/register-builtin",
                json={
                    "domain": "x.example",
                    "name": "X",
                    "tier": "mainstream",
                    "unexpected": "field",
                },
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert res.status_code == 422
