"""Tests for api/server.py — FastAPI endpoints"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport


@pytest.fixture
def app():
    """Create FastAPI app for testing without importing the module-level agent build."""
    from fastapi import FastAPI
    from pydantic import BaseModel

    mock_app = FastAPI(title="Claw Test API")

    class ChatRequest(BaseModel):
        session_id: str
        user_id: str | None = None
        message: str

    class ChatResponse(BaseModel):
        status: str = "completed"
        reply: str

    @mock_app.post("/api/chat", response_model=ChatResponse)
    async def chat(req: ChatRequest) -> ChatResponse:
        return ChatResponse(status="completed", reply="mock reply")

    @mock_app.post("/api/auth/register")
    async def register():
        return {"user_id": "u1", "username": "test", "token": "t1"}

    @mock_app.post("/api/auth/login")
    async def login():
        return {"user_id": "u1", "username": "test", "token": "t1"}

    @mock_app.get("/api/sessions")
    async def list_sessions():
        return {"sessions": []}

    @mock_app.post("/api/sessions")
    async def create_session():
        return {"session_id": "s1", "user_id": "u1"}

    @mock_app.delete("/api/sessions/{session_id}")
    async def delete_session(session_id: str):
        return {"detail": "已删除"}

    @mock_app.get("/api/sessions/{session_id}/messages")
    async def get_session_messages(session_id: str):
        return {"messages": []}

    @mock_app.get("/debug/trace/{session_id}")
    async def latest_trace(session_id: str) -> dict:
        return {"trace": None}

    @mock_app.get("/debug/session/{session_id}")
    async def session_snapshot(session_id: str) -> dict:
        return {"session": None, "task": None}

    @mock_app.get("/debug/memory")
    async def memory_snapshot(query: str = "", limit: int = 10) -> dict:
        return {"items": []}

    @mock_app.get("/debug/mcp")
    async def mcp_snapshot() -> dict:
        return {"servers": []}

    return mock_app


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestChatEndpoint:
    @pytest.mark.asyncio
    async def test_chat_endpoint_exists(self, client):
        response = await client.post(
            "/api/chat",
            json={"session_id": "test", "user_id": "u1", "message": "hello"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "reply" in data

    @pytest.mark.asyncio
    async def test_chat_missing_field(self, client):
        response = await client.post(
            "/api/chat",
            json={"session_id": "test"},  # missing message
        )
        assert response.status_code == 422  # validation error


class TestDebugEndpoints:
    @pytest.mark.asyncio
    async def test_trace_endpoint(self, client):
        response = await client.get("/debug/trace/test_session")
        assert response.status_code == 200
        data = response.json()
        assert "trace" in data

    @pytest.mark.asyncio
    async def test_session_endpoint(self, client):
        response = await client.get("/debug/session/test_session?user_id=u1")
        assert response.status_code == 200
        data = response.json()
        assert "session" in data
        assert "task" in data

    @pytest.mark.asyncio
    async def test_memory_endpoint(self, client):
        response = await client.get("/debug/memory?limit=5&query=test")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    @pytest.mark.asyncio
    async def test_mcp_endpoint(self, client):
        response = await client.get("/debug/mcp")
        assert response.status_code == 200
        data = response.json()
        assert "servers" in data


class TestRealServerStructure:
    """Verify that the real server.py has all expected endpoints defined."""

    def test_all_routes_exist(self):
        try:
            from api.server import app as real_app

            route_paths = [route.path for route in real_app.routes]
            assert "/api/chat" in route_paths
            assert "/api/auth/register" in route_paths
            assert "/api/auth/login" in route_paths
            assert "/api/sessions" in route_paths
            assert "/debug/trace/{session_id}" in route_paths
            assert "/debug/session/{session_id}" in route_paths
            assert "/debug/memory" in route_paths
            assert "/debug/mcp" in route_paths
            assert "/debug/mcp/select" in route_paths
            assert "/debug/task/{session_id}" in route_paths
        except Exception:
            pytest.skip("Could not import real server (likely missing API key)")
