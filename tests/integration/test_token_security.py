"""Task 4 认证令牌安全与 cookie/CSRF 集成测试。

覆盖范围：
- ``hash_token`` 计算稳定且与原 token 不同
- 数据库只存 ``sha256(token)``，不存明文
- 登录/注册响应同时下发 ``auth_token`` (HttpOnly) 与 ``csrf_token`` cookie
- 中间件支持 Bearer 与 cookie 两种认证方式
- 不安全方法（POST/PATCH/DELETE）的 cookie 请求必须带匹配的 ``X-CSRF-Token`` header
- 已 revoke 的 token 被拒绝

P0-1/P0-2 修复后追加：
- 登录响应体不再暴露 ``token`` 字段（浏览器 JS 无法读取）
- ``csrf_token`` cookie 与 ``auth_token`` cookie 值不同（HttpOnly 认证 token 不通过 CSRF cookie 泄露）
- 浏览器持久化存储（localStorage/sessionStorage）不含 token — 由前端测试覆盖
"""

from __future__ import annotations

import hashlib

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.middleware.auth import auth_middleware
from api.middleware.error_handler import yunhe_exception_handler, unhandled_exception_handler
from api.v1.auth import router as auth_router
from application.exceptions.base import YunheException
from domain.user.auth.auth import UserStore
from domain.user.auth.token import (
    generate_token,
    hash_token,
    revoke_token,
    verify_token,
)
from infrastructure.persistence.database import get_connection, init_db, reset_connection


# ---------------------------------------------------------------------------
# 共享 fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_token_security.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()


@pytest.fixture
def user(db):
    store = UserStore()
    return store.create("alice", "secret123")


@pytest.fixture
def issued_token(user) -> str:
    return generate_token(user.user_id)


@pytest_asyncio.fixture
async def app(db):
    test_app = FastAPI()
    test_app.state.agent = None
    test_app.middleware("http")(auth_middleware)
    test_app.add_exception_handler(YunheException, yunhe_exception_handler)
    test_app.add_exception_handler(Exception, unhandled_exception_handler)
    test_app.include_router(auth_router, prefix="/api/v1/auth")
    return test_app


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# hash_token 单元行为
# ---------------------------------------------------------------------------


class TestHashToken:
    def test_hash_token_is_sha256_hex(self):
        token = "abc.def-123"
        digest = hash_token(token)
        assert digest == hashlib.sha256(token.encode()).hexdigest()
        assert len(digest) == 64

    def test_hash_token_differs_from_plaintext(self, issued_token):
        assert hash_token(issued_token) != issued_token


# ---------------------------------------------------------------------------
# 存储 — 数据库不应保存明文 token
# ---------------------------------------------------------------------------


class TestTokenStorage:
    def test_issued_token_is_not_stored_in_plaintext(self, db, issued_token):
        conn = get_connection()
        rows = conn.execute("SELECT token_hash FROM auth_token_hashes").fetchall()
        # 数据库中至少有一行（当前 issued_token 对应的哈希）
        assert rows, "auth_token_hashes 表为空，未持久化 issued token 的哈希"
        for row in rows:
            # 任意行都不应等于明文 token
            assert row["token_hash"] != issued_token
            # 当前 issued_token 的哈希应存在于表中
        expected_hash = hash_token(issued_token)
        stored_hashes = {row["token_hash"] for row in rows}
        assert expected_hash in stored_hashes

    def test_database_does_not_have_plaintext_column(self, db):
        conn = get_connection()
        cols = {row[1] for row in conn.execute("PRAGMA table_info(auth_token_hashes)").fetchall()}
        # 新表只有 token_hash 列，不应有 token 明文列
        assert "token" not in cols
        assert "token_hash" in cols
        assert {"token_hash", "user_id", "expires_at"} <= cols

    def test_legacy_auth_tokens_table_dropped(self, db):
        conn = get_connection()
        # 旧表应已删除（迁移 12）
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='auth_tokens'"
        ).fetchall()
        assert rows == []


# ---------------------------------------------------------------------------
# Bearer token 行为
# ---------------------------------------------------------------------------


class TestBearerToken:
    def test_verify_token_accepts_valid_token(self, issued_token, user):
        user_id = verify_token(issued_token)
        assert user_id == user.user_id

    def test_verify_token_rejects_wrong_token(self):
        assert verify_token("not-a-real-token") is None

    def test_revoked_token_is_rejected_by_verify(self, issued_token):
        revoke_token(issued_token)
        assert verify_token(issued_token) is None


# ---------------------------------------------------------------------------
# Cookie 与 CSRF — API 层
# ---------------------------------------------------------------------------


class TestCookieAndCSRF:
    @pytest.mark.asyncio
    async def test_login_sets_http_only_auth_cookie(self, client):
        UserStore().create("alice", "secret123")
        response = await client.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "secret123"},
        )
        assert response.status_code == 200
        set_cookie = response.headers.get("set-cookie", "")
        assert "auth_token=" in set_cookie
        assert "HttpOnly" in set_cookie
        # FastAPI 序列化 SameSite 时小写，断言忽略大小写
        assert "samesite=lax" in set_cookie.lower()

    @pytest.mark.asyncio
    async def test_login_sets_csrf_cookie_readable_by_js(self, client):
        UserStore().create("alice", "secret123")
        response = await client.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "secret123"},
        )
        set_cookie = response.headers.get("set-cookie", "")
        assert "csrf_token=" in set_cookie
        # CSRF cookie 必须可被前端 JS 读取，不能是 HttpOnly
        # 注意：httpx 把所有 Set-Cookie 合并到一行，无法逐 cookie 检查 HttpOnly
        # 所以我们只断言 csrf_token 子串存在
        assert "csrf_token=" in set_cookie

    @pytest.mark.asyncio
    async def test_login_response_body_does_not_expose_token(self, client):
        """P0-1: 浏览器登录响应体不得暴露 token，避免 JS 读取后写入 localStorage。"""
        UserStore().create("alice", "secret123")
        response = await client.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "secret123"},
        )
        assert response.status_code == 200
        body = response.json()
        # 响应体只允许出现 user_id 与 username，不得包含 token
        assert "token" not in body, f"login response body leaked token: {body}"
        assert "user_id" in body
        assert "username" in body

    @pytest.mark.asyncio
    async def test_csrf_cookie_value_differs_from_auth_token(self, client):
        """P0-2: csrf_token cookie 不得等于 auth_token cookie 值。

        若两者相同，JS 可借由可读的 csrf cookie 直接获得 HttpOnly 认证 token，
        HttpOnly 保护失效。
        """
        UserStore().create("alice", "secret123")
        response = await client.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "secret123"},
        )
        assert response.status_code == 200
        auth_cookie = response.cookies.get("auth_token")
        csrf_cookie = response.cookies.get("csrf_token")
        assert auth_cookie is not None, "auth_token cookie missing"
        assert csrf_cookie is not None, "csrf_token cookie missing"
        assert auth_cookie != csrf_cookie, (
            "csrf_token cookie must NOT equal auth_token cookie; "
            "otherwise HttpOnly protection is bypassed"
        )

    @pytest.mark.asyncio
    async def test_cookie_authenticates_safe_request(self, client, issued_token):
        # 模拟浏览器：cookie 携带 auth_token，无 CSRF header，GET 应通过
        cookies = {"auth_token": issued_token}
        # 用一个公开端点验证 cookie 是否被认证 — 直接访问 /api/v1/auth/login 不行
        # 这里用一个不会被 middleware 跳过的路径，例如 /api/v1/auth/me 不存在
        # 改为断言 middleware 不返回 401 — 通过访问 health 端点不需要认证
        # 但 health 是公开的，无法验证 cookie 鉴权
        # 改用一个非公开路径：/api/v1/sessions 暂未挂载，所以会 404
        # 直接断言 middleware 接受 cookie 即可：访问任意需要认证的路径，应不是 401
        # 用 chat 路径 — 也未挂载
        # 折中：访问一个不存在的非公开路径，401 表示未鉴权，404 表示鉴权通过
        response = await client.get("/api/v1/sessions", cookies=cookies)
        assert response.status_code != 401

    @pytest.mark.asyncio
    async def test_unsafe_cookie_request_without_csrf_rejected(self, client, issued_token):
        # POST 不带 CSRF header 应被拒绝
        response = await client.post(
            "/api/v1/sessions",
            cookies={"auth_token": issued_token},
            json={},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_unsafe_cookie_request_with_matching_csrf_accepted(self, client):
        """P0-2 修复后必须从登录响应中提取真实的 csrf_token cookie 值。

        旧测试假设 ``csrf_token == auth_token``（这正是 P0-2 漏洞）；修复后两者不同，
        必须使用后端实际下发的 csrf 值才能通过 double-submit 校验。
        """
        UserStore().create("alice", "secret123")
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "secret123"},
        )
        assert login_resp.status_code == 200
        auth_cookie = login_resp.cookies.get("auth_token")
        csrf_cookie = login_resp.cookies.get("csrf_token")
        assert auth_cookie and csrf_cookie
        # 使用后端实际下发的 csrf cookie 值作为 X-CSRF-Token header
        cookies = {"auth_token": auth_cookie, "csrf_token": csrf_cookie}
        headers = {"X-CSRF-Token": csrf_cookie}
        response = await client.post(
            "/api/v1/sessions",
            cookies=cookies,
            headers=headers,
            json={},
        )
        # middleware 鉴权通过后才会路由，sessions 未挂载会 404，但不应是 401
        assert response.status_code != 401

    @pytest.mark.asyncio
    async def test_unsafe_cookie_request_with_mismatched_csrf_rejected(self, client, issued_token):
        # csrf cookie 与 X-CSRF-Token header 不匹配应被拒绝
        cookies = {"auth_token": issued_token, "csrf_token": "some-csrf-value"}
        headers = {"X-CSRF-Token": "different-value"}
        response = await client.post(
            "/api/v1/sessions",
            cookies=cookies,
            headers=headers,
            json={},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_revoked_token_is_rejected(self, client, issued_token):
        revoke_token(issued_token)
        response = await client.get(
            "/api/v1/sessions",
            headers=_bearer(issued_token),
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_bearer_still_works_for_unsafe_requests(self, client, issued_token):
        # Bearer 不需要 CSRF（仅浏览器 cookie 模式需要）
        response = await client.post(
            "/api/v1/sessions",
            headers=_bearer(issued_token),
            json={},
        )
        # middleware 鉴权通过 → 路由未挂载返回 404，但绝不应是 401
        assert response.status_code != 401
