# 平台安全与调度 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立可持久化、受所有权保护的会话模式，使云合在默认会话中最多委派一个 Agent，并为后续领域 UI 提供安全认证与测试底座。

**Architecture:** API 从认证中间件取得用户身份；应用服务保存并校验会话模式；编排器只根据已持久化的模式做路由；前端仅显示服务端确认的当前处理者。相册已不属于产品范围，所有相册路由直接下线。

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, SQLite, React, TypeScript, pytest, Vitest, Testing Library, jsdom.

## Global Constraints

- 用户 ID 只能从认证中间件取得；未授权资源一律返回 404。
- 新增 DTO 使用 `ConfigDict(extra="forbid")`。
- 默认会话每轮最多委派一个 Agent，委派回复后控制权返回云合；锁定会话不重新路由。
- `news_analysis_locked` 只能由新闻分析服务创建，用户会话 API 不得接受该模式。
- 认证令牌表只存 `sha256(token)`；浏览器不得把长期令牌存入 localStorage 或 sessionStorage。
- 相册、照片文件、EXIF 与相关旧 URL 均应返回 404；既有上传文件暂不删除。

---

### Task 1: 持久化会话模式与用户锁定 API

**Files:**
- Create: `application/session/schema.py`
- Create: `application/session/service.py`
- Modify: `infrastructure/persistence/database.py`
- Modify: `domain/user/session/manager.py`
- Modify: `api/v1/session.py`
- Modify: `frontend/src/hooks/useSessionStore.ts`
- Test: `tests/integration/test_session_modes.py`

**Interfaces:**
- `SessionMode = Literal["yunhe_default", "agent_locked", "news_analysis_locked"]`
- `SessionService.create(user_id: str, mode: SessionMode, locked_agent_id: str | None = None, news_id: str | None = None) -> SessionRecord`
- `SessionService.require_owned(user_id: str, session_id: str) -> SessionRecord`
- `POST /api/v1/sessions` and `PATCH /api/v1/sessions/{session_id}/mode` accept only `yunhe_default` or `agent_locked`.

- [ ] **Step 1: 写失败测试**

```python
def test_news_locked_session_persists_lock_and_anchor(service):
    session = service.create("u1", "news_analysis_locked", "news", "news_123")
    assert session.mode == "news_analysis_locked"
    assert session.locked_agent_id == "news"
    assert session.news_id == "news_123"

@pytest.mark.asyncio
async def test_user_can_lock_only_an_available_agent(client, token):
    response = await client.post(
        "/api/v1/sessions",
        headers=bearer(token),
        json={"mode": "agent_locked", "locked_agent_id": "academic"},
    )
    assert response.status_code == 201
    assert response.json()["data"]["locked_agent_id"] == "academic"
```

- [ ] **Step 2: 运行失败测试**

Run: `pytest tests/integration/test_session_modes.py -v`

Expected: FAIL because the session fields and user-facing mode APIs do not exist.

- [ ] **Step 3: 实现迁移、服务和路由**

```python
SessionMode = Literal["yunhe_default", "agent_locked", "news_analysis_locked"]

@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    user_id: str
    mode: SessionMode
    locked_agent_id: str | None
    news_id: str | None
```

Add migration 11 with `mode`, `locked_agent_id`, and `news_id`. Query owned sessions with `WHERE session_id = ? AND user_id = ?`. Reject `news_analysis_locked` from both user APIs and reject disabled or unavailable locked Agents. Persist the server response in `useSessionStore`; sidebar selection is presentation state only.

- [ ] **Step 4: 验证通过**

Run: `pytest tests/integration/test_session_modes.py tests/integration/test_session.py -v`

Expected: PASS.

- [ ] **Step 5: 提交**

Run: `git add application/session infrastructure/persistence/database.py domain/user/session api/v1/session.py frontend/src/hooks/useSessionStore.ts tests/integration/test_session_modes.py; git commit -m "feat: persist session modes"`

### Task 2: 集中资源授权并关闭 IDOR

**Files:**
- Create: `application/authz/service.py`
- Modify: `api/v1/itinerary.py`
- Modify: `api/v1/session.py`
- Modify: `api/v1/debug.py`
- Test: `tests/integration/test_resource_authorization.py`

**Interfaces:**
- `AuthorizationService.require_itinerary(user_id: str, itinerary_id: str) -> Itinerary`
- `AuthorizationService.require_activity(user_id: str, itinerary_id: str, activity_id: str) -> Activity`
- `AuthorizationService.require_session(user_id: str, session_id: str) -> SessionRecord`

- [ ] **Step 1: 写双用户失败测试**

```python
@pytest.mark.asyncio
async def test_user_cannot_read_other_users_itinerary(client, users):
    owner, other, itinerary = users
    response = await client.get(f"/api/v1/itineraries/{itinerary.id}", headers=bearer(other.token))
    assert response.status_code == 404
```

Repeat the assertion for activity edits, share deletion, session confirmation and debug data.

- [ ] **Step 2: 运行失败测试**

Run: `pytest tests/integration/test_resource_authorization.py -v`

Expected: FAIL on every unguarded resource route.

- [ ] **Step 3: 实现授权服务**

```python
class AuthorizationService:
    def require_itinerary(self, user_id: str, itinerary_id: str) -> Itinerary:
        itinerary = self._itineraries.get(itinerary_id)
        if itinerary is None or itinerary.user_id != user_id:
            raise NotFoundException("itinerary", itinerary_id)
        return itinerary
```

Replace route-local ownership checks. Do not mount the debug router in production; in development require administrator identity plus resource ownership.

- [ ] **Step 4: 验证通过**

Run: `pytest tests/integration/test_resource_authorization.py tests/integration/test_itinerary.py -v`

Expected: PASS.

- [ ] **Step 5: 提交**

Run: `git add application/authz api/v1 tests/integration/test_resource_authorization.py; git commit -m "fix: centralize owned-resource authorization"`

### Task 3: 下线相册端点并按会话模式调度

**Files:**
- Delete: `api/v1/album.py`
- Modify: `api/v1/__init__.py`
- Modify: `domain/agent/orchestrator.py`
- Modify: `api/v1/chat.py`
- Modify: `frontend/src/pages/Home.tsx`
- Test: `tests/integration/test_removed_album_routes.py`
- Test: `tests/unit/test_orchestrator_modes.py`

**Interfaces:**
- `RouteDecision(agent_id: str | None, delegated: bool, reason: str)`

- [ ] **Step 1: 写失败测试**

```python
@pytest.mark.asyncio
async def test_album_routes_are_removed(client, token):
    for path in ("/api/v1/album", "/api/v1/itineraries/i1/album", "/api/v1/photos/p1/file"):
        response = await client.get(path, headers=bearer(token))
        assert response.status_code == 404

@pytest.mark.asyncio
async def test_default_mode_returns_to_yunhe_after_single_delegation(orchestrator):
    result = await orchestrator.chat("s1", "u1", "检索 RAG 论文", "yunhe_default", None)
    assert result["handled_by"] == "academic"
    assert result["next_controller"] == "yunhe"
```

- [ ] **Step 2: 运行失败测试**

Run: `pytest tests/integration/test_removed_album_routes.py tests/unit/test_orchestrator_modes.py -v`

Expected: FAIL because album routes remain mounted and routing is travel-backed.

- [ ] **Step 3: 卸载相册接口并实现 mode-first 路由**

```python
async def _select_handler(self, mode, locked_agent_id, message, user_id):
    if mode in {"agent_locked", "news_analysis_locked"}:
        return RouteDecision(locked_agent_id, True, "locked_session")
    if self._is_simple_general_question(message):
        return RouteDecision(None, False, "yunhe_direct")
    return await self._select_one_specialist(message, user_id)
```

Remove the album router and every album/photo file endpoint. Retain existing uploads in controlled storage without exposing or deleting them. Remove `__getattr__` delegation to travel for sessions, traces and routing. Make `activeAgent` display-only in default sessions.

- [ ] **Step 4: 验证通过**

Run: `pytest tests/integration/test_removed_album_routes.py tests/unit/test_orchestrator_modes.py tests/integration/test_chat_session_modes.py -v`

Expected: PASS.

- [ ] **Step 5: 提交**

Run: `git add -A api/v1/album.py api/v1/__init__.py domain/agent/orchestrator.py api/v1/chat.py frontend/src/pages/Home.tsx tests; git commit -m "refactor: remove albums and route agent sessions"`

### Task 4: 认证令牌安全与前端测试底座

**Files:**
- Modify: `infrastructure/persistence/database.py`
- Modify: `domain/user/auth/token.py`
- Modify: `api/v1/auth.py`
- Modify: `api/middleware/auth.py`
- Create: `frontend/src/features/auth/client.ts`
- Modify: `frontend/package.json`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/src/test/setup.ts`
- Test: `tests/integration/test_token_security.py`
- Test: `frontend/src/features/auth/client.test.ts`

**Interfaces:**
- `hash_token(token: str) -> str`
- `AuthClient.request(path: string, init?: RequestInit) -> Promise<Response>`
- `npm run test` runs Vitest using jsdom.

- [ ] **Step 1: 写失败测试**

```python
def test_issued_token_is_not_stored_in_plaintext(token_repository, issued_token):
    assert issued_token not in token_repository.raw_token_values()

def test_revoked_token_is_rejected(client, issued_token):
    revoke(issued_token)
    assert client.get("/api/v1/sessions", headers=bearer(issued_token)).status_code == 401
```

```tsx
it('does not persist an authentication token in browser storage', () => {
  expect(localStorage.getItem('token')).toBeNull()
  expect(sessionStorage.getItem('token')).toBeNull()
})
```

- [ ] **Step 2: 运行失败测试**

Run: `pytest tests/integration/test_token_security.py -v; npm run test -- client.test.ts`

Expected: FAIL until token hashing, cookie/CSRF handling and Vitest are installed.

- [ ] **Step 3: 实现安全认证与测试底座**

Store only `sha256(token)` and hash bearer tokens before lookup. In production issue authentication through `Secure`, `HttpOnly`, `SameSite=Lax` cookies; require a CSRF header for unsafe cookie-authenticated requests. Keep bearer tokens only for documented non-browser clients. Install Vitest, Testing Library and jsdom; configure `npm run test`; make the shared client use credentials and CSRF rather than browser storage.

- [ ] **Step 4: 验证通过**

Run: `pytest tests/integration/test_token_security.py -v; npm run test -- client.test.ts`

Expected: PASS.

- [ ] **Step 5: 提交**

Run: `git add domain/user/auth/token.py api/v1/auth.py api/middleware infrastructure/persistence/database.py frontend/package.json frontend/vitest.config.ts frontend/src/features/auth frontend/src/test tests/integration/test_token_security.py; git commit -m "feat: secure authentication and add frontend tests"`
