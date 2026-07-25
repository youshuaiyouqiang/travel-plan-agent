"""Task 1 — 新闻来源管理员 API 的集成测试。

覆盖范围：
- ``GET /api/v1/admin/news/sources`` 仅管理员可访问；普通用户 403
- ``POST /api/v1/admin/news/sources/{id}/review`` 仅管理员可审核；普通用户 403，管理员 200
- ``GET /api/v1/admin/news/source-audits`` 仅管理员可访问；返回审核记录

业务红线：
- 单一系统管理员由启动配置 ``YUNHE_ADMIN_USERNAME`` 解析，不从 HTTP 请求接收。
- 管理员身份以 ``app.state.admin_user_id`` 为准，与 ``request.state.user_id`` 比对。
- 非管理员访问管理员端点统一返回 403，不泄漏资源存在性。
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.middleware.auth import auth_middleware
from api.middleware.error_handler import yunhe_exception_handler, unhandled_exception_handler
from api.v1.admin_news import router as admin_news_router
from application.exceptions.base import YunheException
from application.news.source_service import SourceService
from config import settings
from domain.user.auth.auth import UserStore
from domain.user.auth.token import generate_token
from infrastructure.persistence.database import init_db, reset_connection


# ---------------------------------------------------------------------------
# 共享 fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_news_admin_api.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()


@pytest.fixture
def admin_user(db, monkeypatch):
    """创建管理员账户，并通过 ``YUNHE_ADMIN_USERNAME`` 锚定其 username。"""
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


@pytest.fixture
def source_id(db) -> str:
    """创建一个 pending 候选来源，返回其 ID 供审核测试使用。"""
    service = SourceService()
    created = service.create_candidate("example.com", 0.6, "initial")
    return created.id


@pytest_asyncio.fixture
async def app(db, admin_user):
    test_app = FastAPI()
    test_app.state.agent = None
    # 启动期解析 ``YUNHE_ADMIN_USERNAME`` → user_id；端点仅信任此值
    test_app.state.admin_user_id = admin_user.user_id
    test_app.middleware("http")(auth_middleware)
    test_app.add_exception_handler(YunheException, yunhe_exception_handler)
    test_app.add_exception_handler(Exception, unhandled_exception_handler)
    test_app.include_router(admin_news_router, prefix="/api/v1/admin/news")
    return test_app


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# GET /admin/news/sources
# ---------------------------------------------------------------------------


class TestListSources:
    @pytest.mark.asyncio
    async def test_admin_can_list_sources(self, client, admin_token):
        resp = await client.get("/api/v1/admin/news/sources", headers=_bearer(admin_token))
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert isinstance(body["items"], list)

    @pytest.mark.asyncio
    async def test_regular_user_cannot_list_sources(self, client, user_token):
        resp = await client.get("/api/v1/admin/news/sources", headers=_bearer(user_token))
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /admin/news/sources/{id}/review
# ---------------------------------------------------------------------------


class TestReviewSource:
    @pytest.mark.asyncio
    async def test_only_admin_can_review_source(self, client, user_token, admin_token, source_id):
        forbidden = await client.post(
            f"/api/v1/admin/news/sources/{source_id}/review",
            headers=_bearer(user_token),
            json={"decision": "enabled", "reason": "x"},
        )
        accepted = await client.post(
            f"/api/v1/admin/news/sources/{source_id}/review",
            headers=_bearer(admin_token),
            json={"decision": "enabled", "reason": "verified"},
        )
        assert forbidden.status_code == 403
        assert accepted.status_code == 200
        body = accepted.json()
        assert body["status"] == "enabled"
        assert body["id"] == source_id

    @pytest.mark.asyncio
    async def test_review_records_audit_visible_in_audits_endpoint(
        self, client, admin_token, source_id
    ):
        reviewed = await client.post(
            f"/api/v1/admin/news/sources/{source_id}/review",
            headers=_bearer(admin_token),
            json={"decision": "enabled", "reason": "verified"},
        )
        assert reviewed.status_code == 200

        audits = await client.get(
            "/api/v1/admin/news/source-audits",
            headers=_bearer(admin_token),
        )
        assert audits.status_code == 200
        items = audits.json()["items"]
        assert any(a["source_id"] == source_id for a in items)

    @pytest.mark.asyncio
    async def test_review_unknown_source_returns_404(self, client, admin_token):
        resp = await client.post(
            "/api/v1/admin/news/sources/nonexistent-id/review",
            headers=_bearer(admin_token),
            json={"decision": "enabled", "reason": "x"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_review_invalid_decision_returns_422(self, client, admin_token, source_id):
        resp = await client.post(
            f"/api/v1/admin/news/sources/{source_id}/review",
            headers=_bearer(admin_token),
            json={"decision": "garbage", "reason": "x"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /admin/news/source-audits
# ---------------------------------------------------------------------------


class TestListAudits:
    @pytest.mark.asyncio
    async def test_admin_can_list_audits(self, client, admin_token):
        resp = await client.get("/api/v1/admin/news/source-audits", headers=_bearer(admin_token))
        assert resp.status_code == 200
        assert "items" in resp.json()

    @pytest.mark.asyncio
    async def test_regular_user_cannot_list_audits(self, client, user_token):
        resp = await client.get("/api/v1/admin/news/source-audits", headers=_bearer(user_token))
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_audits_join_source_name_and_domain(
        self, client, admin_token, source_id
    ):
        """审核记录响应必须 JOIN 来源的 name 与 domain，否则审计无解读价值。

        业务背景：审计列表里只有状态流转无法回答"审了哪家来源"；
        后端必须把 news_sources 的 name/domain 拼到审计行里。
        """
        # 先产生一条审计
        await client.post(
            f"/api/v1/admin/news/sources/{source_id}/review",
            headers=_bearer(admin_token),
            json={"decision": "enabled", "reason": "verified"},
        )
        # 再读取
        resp = await client.get(
            "/api/v1/admin/news/source-audits",
            headers=_bearer(admin_token),
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        match = [a for a in items if a["source_id"] == source_id]
        assert match, f"未找到 source_id={source_id} 的审计行"
        audit = match[0]
        # JOIN 字段必须存在且非空
        assert "source_domain" in audit
        assert "source_name" in audit
        # 候选来源 name 默认等于 domain（create_candidate 行 174），
        # domain 在 fixture 里固定为 "example.com"
        assert audit["source_domain"] == "example.com"
        assert audit["source_name"] == "example.com"
        # 状态流转与理由仍保留
        assert audit["previous_status"] == "pending"
        assert audit["decision"] == "enabled"
        assert audit["reason"] == "verified"

    @pytest.mark.asyncio
    async def test_audits_handle_missing_source_gracefully(
        self, client, admin_token
    ):
        """来源被删除（极少见）时，审计仍返回，但 name/domain 留空。

        直接往审计表写一条孤儿 source_id，验证不会因此 500。
        """
        from application.news.models import SourceAudit
        from application.news.source_service import SourceService

        service = SourceService()
        audit = SourceAudit(
            id="orphan-audit-id",
            source_id="ghost-source-id",
            admin_id="admin-1",
            previous_status="pending",
            decision="enabled",
            reason="test-orphan",
            created_at="2026-07-25T10:00:00+00:00",
        )
        service._repo.insert_audit(audit)

        resp = await client.get(
            "/api/v1/admin/news/source-audits",
            headers=_bearer(admin_token),
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        orphan = [a for a in items if a["id"] == "orphan-audit-id"]
        assert orphan, "未找到孤儿审计行"
        # JOIN 字段为空串而非 None，便于前端稳定渲染
        assert orphan[0]["source_name"] == ""
        assert orphan[0]["source_domain"] == ""
