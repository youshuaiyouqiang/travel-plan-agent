"""news_analysis_locked 会话下 chat 端点自动注入完整研判上下文的集成测试。

覆盖范围：
- 在 ``news_analysis_locked`` 会话下，``POST /api/v1/chat/stream`` 和
  ``POST /api/v1/chat`` 都会把会话锚定的热点元数据（标题/来源/链接/摘要/发布时间）
  + 证据卡片（verified / conflicted）+ 未核实线索，按"锚点 → 证据 → 线索 →
  用户问题"四段拼接到用户消息前面，再传给 agent。
- NewsAnalysisService 注入真实证据时，agent 收到的 message 包含 [证据卡片] 与
  [未核实线索] 段；空证据时显示"暂无证据或线索"占位。
- 其他模式（``yunhe_default``、``agent_locked``）下消息原样转发，不注入上下文。
- 锚点已从热点池过期时（``get_by_id`` 返回 None）消息原样转发，不注入。
- NewsAnalysisService 未注入时（仅 hotspot_service）仍注入锚点，但 evidence 段
  显示占位（降级路径）。

业务红线：
- 注入内容只含元数据，绝不含新闻全文字段。
- 锁定 Agent 在 chat 端点由后端按 session 模式决定，客户端不能通过 ``agent_id``
  字段覆盖路由。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.middleware.auth import auth_middleware
from api.middleware.error_handler import yunhe_exception_handler, unhandled_exception_handler
from api.v1.chat import router as chat_router
from application.exceptions.base import YunheException
from application.news.analysis_service import NewsAnalysisService
from application.news.hotspot_service import HotspotService
from application.news.models import (
    Evidence,
    NewsAnchor,
    NewsItem,
)
from application.news.source_service import SourceService
from application.session.service import SessionService
from domain.user.auth.auth import UserStore
from domain.user.auth.token import generate_token
from infrastructure.persistence.database import init_db, reset_connection


# ---------------------------------------------------------------------------
# 共享 fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_chat_news_anchor.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()


@dataclass
class _StubFetcher:
    items: list[NewsItem]
    calls: int = 0

    async def fetch(self, source) -> list[NewsItem]:
        self.calls += 1
        return list(self.items)


class _StubEvidenceProvider:
    """返回预设证据列表的假证据提供者（不读数据库）。"""

    def __init__(self, evidence: list[Evidence] | None = None) -> None:
        self.evidence = list(evidence or [])

    def get_evidence(self, anchor: NewsAnchor) -> list[Evidence]:
        return list(self.evidence)


class _RecordingAgent:
    """记录 chat / chat_stream 收到的 message，便于断言上下文是否完整注入。"""

    def __init__(self) -> None:
        self.last_message: str = ""
        self.last_mode: str = ""
        self.last_locked_agent_id: str | None = None
        self.last_user_id: str | None = None
        self.last_session_id: str = ""

    async def chat(
        self,
        *,
        session_id: str,
        user_id: str | None,
        message: str,
        mode: str = "yunhe_default",
        locked_agent_id: str | None = None,
        **_kwargs,
    ) -> dict:
        self.last_session_id = session_id
        self.last_user_id = user_id
        self.last_message = message
        self.last_mode = mode
        self.last_locked_agent_id = locked_agent_id
        return {"status": "final_answer", "reply": "ok"}

    async def chat_stream(
        self,
        *,
        session_id: str,
        user_id: str | None,
        message: str,
        mode: str = "yunhe_default",
        locked_agent_id: str | None = None,
        **_kwargs,
    ) -> AsyncGenerator[dict, None]:
        self.last_session_id = session_id
        self.last_user_id = user_id
        self.last_message = message
        self.last_mode = mode
        self.last_locked_agent_id = locked_agent_id
        yield {"type": "chunk", "data": "ok"}
        yield {"type": "done", "data": "final_answer"}


@pytest.fixture
def hotspot_service(db) -> HotspotService:
    service = HotspotService(
        sources=SourceService(), fetcher=_StubFetcher(items=[])
    )
    service.repository.save_items(
        [
            NewsItem(
                id="news-1",
                title="某热点事件",
                source="某权威来源",
                url="https://example.com/news-1",
                summary="简短摘要",
                published_at="2026-07-25T10:00:00Z",
            )
        ]
    )
    return service


@pytest.fixture
def news_analysis_service_empty() -> NewsAnalysisService:
    """空证据 NewsAnalysisService。"""
    return NewsAnalysisService(
        sources=SourceService(), evidence_provider=_StubEvidenceProvider(evidence=[])
    )


@pytest.fixture
def news_analysis_service_with_evidence() -> NewsAnalysisService:
    """带真实证据的 NewsAnalysisService：1 张 verified + 1 张 conflicted + 1 条 lead。

    依赖同一个内存 SQLite 数据库（``db`` fixture）；为便于隔离，**不**复用
    ``db``，而是直接通过 ``SourceService._repo.insert_source`` 把两个 enabled
    来源与一个 pending 来源预先注入；这样 NewsAnalysisService.analyze 会按
    来源状态把它们分类为 enabled 证据 / unverified_leads。
    """
    from application.news.models import Source

    sources = SourceService()
    now = "2026-07-25T10:00:00+00:00"
    for sid, name in [("src-1", "src-a"), ("src-2", "src-b")]:
        sources._repo.insert_source(
            Source(
                id=sid,
                name=name,
                domain=f"{name}.example",
                tier="tier1",
                status="enabled",
                scoring_mode="ai_candidate",
                ai_score=0.9,
                ai_reason="pre-enabled for test",
                ai_subscores="{}",
                created_at=now,
                updated_at=now,
            )
        )
    sources._repo.insert_source(
        Source(
            id="src-pending",
            name="X 平台",
            domain="x.example",
            tier="tier3",
            status="pending",
            scoring_mode="ai_candidate",
            ai_score=0.3,
            ai_reason="pre-pending for test",
            ai_subscores="{}",
            created_at=now,
            updated_at=now,
        )
    )
    return NewsAnalysisService(
        sources=sources,
        evidence_provider=_StubEvidenceProvider(
            evidence=[
                Evidence(
                    source_id="src-1",
                    source_name="src-a",
                    url="https://a/x",
                    claim="已核实说法",
                ),
                Evidence(
                    source_id="src-2",
                    source_name="src-b",
                    url="https://b/x",
                    claim="另一种说法",
                ),
                Evidence(
                    source_id="src-pending",
                    source_name="X 平台",
                    url="https://x/p",
                    claim="未核实消息",
                ),
            ]
        ),
    )


@pytest.fixture
def session_service(db) -> SessionService:
    return SessionService(available_agent_ids={"travel", "academic"})


@pytest.fixture
def user_and_token(db):
    store = UserStore()
    user = store.create("alice", "secret123")
    return user.user_id, generate_token(user.user_id)


@pytest.fixture
def agent() -> _RecordingAgent:
    return _RecordingAgent()


def _make_app(
    agent: _RecordingAgent,
    hotspot_service: HotspotService,
    session_service: SessionService,
    analysis_service: NewsAnalysisService | None,
) -> FastAPI:
    test_app = FastAPI()
    test_app.state.agent = agent
    test_app.state.hotspot_service = hotspot_service
    test_app.state.session_service = session_service
    if analysis_service is not None:
        test_app.state.news_analysis_service = analysis_service
    test_app.middleware("http")(auth_middleware)
    test_app.add_exception_handler(YunheException, yunhe_exception_handler)
    test_app.add_exception_handler(Exception, unhandled_exception_handler)
    test_app.include_router(chat_router, prefix="/api/v1/chat")
    return test_app


@pytest_asyncio.fixture
async def client_with_analysis(
    db, hotspot_service, news_analysis_service_empty, session_service, user_and_token, agent
):
    test_app = _make_app(
        agent, hotspot_service, session_service, news_analysis_service_empty
    )
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def client_with_evidence(
    db, hotspot_service, news_analysis_service_with_evidence, session_service, user_and_token, agent
):
    test_app = _make_app(
        agent, hotspot_service, session_service, news_analysis_service_with_evidence
    )
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def client_no_analysis(
    db, hotspot_service, session_service, user_and_token, agent
):
    """NewsAnalysisService 未注入：仅注入锚点。"""
    test_app = _make_app(agent, hotspot_service, session_service, None)
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 默认路径：空证据 NewsAnalysisService
# ---------------------------------------------------------------------------


class TestChatStreamNewsContextInjection:
    @pytest.mark.asyncio
    async def test_news_locked_session_injects_anchor_evidence_leads_user_question(
        self, client_with_analysis, user_and_token, session_service, agent
    ):
        user_id, token = user_and_token
        record = session_service.create(
            user_id=user_id,
            mode="news_analysis_locked",
            locked_agent_id="news",
            news_id="news-1",
        )

        resp = await client_with_analysis.post(
            "/api/v1/chat/stream",
            headers=_bearer(token),
            json={"session_id": record.session_id, "message": "请分析影响"},
        )
        assert resp.status_code == 200

        # 四段都在
        assert "[新闻锚点]" in agent.last_message
        assert "标题：某热点事件" in agent.last_message
        assert "[证据卡片]" in agent.last_message
        assert "[未核实线索]" in agent.last_message
        assert "[用户问题]" in agent.last_message
        assert "请分析影响" in agent.last_message
        # 空证据时显示占位
        assert "暂无证据或线索" in agent.last_message

        # 顺序：锚点 → 证据 → 线索 → 用户问题
        assert agent.last_message.index("[新闻锚点]") < agent.last_message.index("[证据卡片]")
        assert agent.last_message.index("[证据卡片]") < agent.last_message.index("[未核实线索]")
        assert agent.last_message.index("[未核实线索]") < agent.last_message.index("[用户问题]")
        assert agent.last_message.index("[用户问题]") < agent.last_message.index("请分析影响")

    @pytest.mark.asyncio
    async def test_news_locked_with_real_evidence_includes_cards_and_leads(
        self, client_with_evidence, user_and_token, session_service, agent
    ):
        user_id, token = user_and_token
        record = session_service.create(
            user_id=user_id,
            mode="news_analysis_locked",
            locked_agent_id="news",
            news_id="news-1",
        )

        resp = await client_with_evidence.post(
            "/api/v1/chat/stream",
            headers=_bearer(token),
            json={"session_id": record.session_id, "message": "请分析"},
        )
        assert resp.status_code == 200
        # 真实证据段：源名称/URL/claim 都出现
        assert "claim：已核实说法" in agent.last_message
        assert "claim：另一种说法" in agent.last_message
        assert "claim：未核实消息" in agent.last_message
        # conflicted 状态因多个 enabled 来源相互矛盾
        # (此处 evidence_provider 总是返回 enabled，所以会按 enabled 分类为 enabled 证据)
        # 关键是验证：注入包含 evidence/lead 段且不丢失字段
        assert "[证据卡片]" in agent.last_message
        assert "[未核实线索]" in agent.last_message

    @pytest.mark.asyncio
    async def test_yunhe_default_session_does_not_inject_context(
        self, client_with_analysis, user_and_token, session_service, agent
    ):
        user_id, token = user_and_token
        record = session_service.create(user_id=user_id, mode="yunhe_default")

        resp = await client_with_analysis.post(
            "/api/v1/chat/stream",
            headers=_bearer(token),
            json={"session_id": record.session_id, "message": "你好"},
        )
        assert resp.status_code == 200
        assert agent.last_message == "你好"
        assert "[新闻锚点]" not in agent.last_message
        assert "[证据卡片]" not in agent.last_message

    @pytest.mark.asyncio
    async def test_agent_locked_session_does_not_inject_context(
        self, client_with_analysis, user_and_token, session_service, agent
    ):
        user_id, token = user_and_token
        record = session_service.create(
            user_id=user_id, mode="agent_locked", locked_agent_id="travel"
        )

        resp = await client_with_analysis.post(
            "/api/v1/chat/stream",
            headers=_bearer(token),
            json={"session_id": record.session_id, "message": "规划旅行"},
        )
        assert resp.status_code == 200
        assert agent.last_message == "规划旅行"
        assert "[新闻锚点]" not in agent.last_message
        assert agent.last_locked_agent_id == "travel"

    @pytest.mark.asyncio
    async def test_news_locked_anchor_missing_falls_back_to_user_message(
        self, client_with_analysis, user_and_token, session_service, agent
    ):
        user_id, token = user_and_token
        # 会话锚定的 news_id 在热点池中不存在（缓存已失效）
        record = session_service.create(
            user_id=user_id,
            mode="news_analysis_locked",
            locked_agent_id="news",
            news_id="news-missing",
        )

        resp = await client_with_analysis.post(
            "/api/v1/chat/stream",
            headers=_bearer(token),
            json={"session_id": record.session_id, "message": "请分析"},
        )
        assert resp.status_code == 200
        # 锚点不存在：原样转发
        assert agent.last_message == "请分析"
        assert "[新闻锚点]" not in agent.last_message

    @pytest.mark.asyncio
    async def test_no_analysis_service_injects_anchor_with_placeholder_evidence(
        self, client_no_analysis, user_and_token, session_service, agent
    ):
        """NewsAnalysisService 未注入时仍注入锚点，evidence 段降级为占位。"""
        user_id, token = user_and_token
        record = session_service.create(
            user_id=user_id,
            mode="news_analysis_locked",
            locked_agent_id="news",
            news_id="news-1",
        )

        resp = await client_no_analysis.post(
            "/api/v1/chat/stream",
            headers=_bearer(token),
            json={"session_id": record.session_id, "message": "请分析"},
        )
        assert resp.status_code == 200
        assert "[新闻锚点]" in agent.last_message
        assert "[证据卡片]" in agent.last_message
        assert "暂无证据或线索" in agent.last_message
        assert "[用户问题]" in agent.last_message


# ---------------------------------------------------------------------------
# 非流式 /chat 端点
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_stream_emits_evidence_event_with_cards(
    client_with_evidence, user_and_token, session_service
):
    """SSE 流在 news_analysis_locked + 真实证据下，应在 chunk 之前推送 ``evidence`` 事件。

    业务红线：
    - ``evidence`` 事件必须先于 ``chunk``，便于前端先把结构化卡片挂到 assistant
      消息，再让文本增量流入。
    - ``data`` 字段为卡片列表（含 ``source_id``），与后端 ``_evidence_card_to_dict``
      输出一致。
    """
    user_id, token = user_and_token
    record = session_service.create(
        user_id=user_id,
        mode="news_analysis_locked",
        locked_agent_id="news",
        news_id="news-1",
    )

    resp = await client_with_evidence.post(
        "/api/v1/chat/stream",
        headers=_bearer(token),
        json={"session_id": record.session_id, "message": "请分析"},
    )
    assert resp.status_code == 200

    events: list[dict] = []
    async for line in resp.aiter_lines():
        line = line.strip()
        if not line.startswith("data: "):
            continue
        import json as _json

        try:
            events.append(_json.loads(line[len("data: "):]))
        except _json.JSONDecodeError:
            continue

    # 第一条业务事件必须是 evidence
    assert events, "SSE 流不应为空"
    assert events[0]["type"] == "evidence"
    assert isinstance(events[0]["data"], list)
    assert len(events[0]["data"]) == 2  # 2 张 enabled 证据（src-1, src-2）
    # 字段完整且含 source_id
    for card in events[0]["data"]:
        assert "source_id" in card
        assert "source_name" in card
        assert "url" in card
        assert "claim" in card
        assert card["status"] in {"verified", "conflicted"}

    # conflict 标记：因为 src-1 和 src-2 claim 不同
    statuses = {c["status"] for c in events[0]["data"]}
    assert "conflicted" in statuses

    # 后续是 agent 的 chunk/done 事件
    event_types = [e["type"] for e in events]
    assert "chunk" in event_types
    assert "done" in event_types
    # evidence 必须在第一个 chunk 之前
    assert event_types.index("evidence") < event_types.index("chunk")


@pytest.mark.asyncio
async def test_chat_stream_emits_evidence_event_with_empty_cards(
    client_with_analysis, user_and_token, session_service
):
    """空证据时仍推送 ``evidence`` 事件，data 为空数组，让前端明确"无证据"。"""
    user_id, token = user_and_token
    record = session_service.create(
        user_id=user_id,
        mode="news_analysis_locked",
        locked_agent_id="news",
        news_id="news-1",
    )

    resp = await client_with_analysis.post(
        "/api/v1/chat/stream",
        headers=_bearer(token),
        json={"session_id": record.session_id, "message": "请分析"},
    )
    assert resp.status_code == 200

    import json as _json

    events: list[dict] = []
    async for line in resp.aiter_lines():
        line = line.strip()
        if not line.startswith("data: "):
            continue
        try:
            events.append(_json.loads(line[len("data: "):]))
        except _json.JSONDecodeError:
            continue

    assert events and events[0]["type"] == "evidence"
    assert events[0]["data"] == []  # 空数组占位


@pytest.mark.asyncio
async def test_chat_stream_no_evidence_event_for_yunhe_default(
    client_with_evidence, user_and_token, session_service
):
    """yunhe_default 模式下不推送 ``evidence`` 事件。"""
    user_id, token = user_and_token
    record = session_service.create(user_id=user_id, mode="yunhe_default")

    resp = await client_with_evidence.post(
        "/api/v1/chat/stream",
        headers=_bearer(token),
        json={"session_id": record.session_id, "message": "你好"},
    )
    assert resp.status_code == 200

    import json as _json

    has_evidence = False
    async for line in resp.aiter_lines():
        line = line.strip()
        if not line.startswith("data: "):
            continue
        try:
            ev = _json.loads(line[len("data: "):])
        except _json.JSONDecodeError:
            continue
        if ev.get("type") == "evidence":
            has_evidence = True
    assert not has_evidence


class TestChatNonStreamNewsContextInjection:
    @pytest.mark.asyncio
    async def test_news_locked_injects_full_context_in_sync_chat(
        self, client_with_analysis, user_and_token, session_service, agent
    ):
        user_id, token = user_and_token
        record = session_service.create(
            user_id=user_id,
            mode="news_analysis_locked",
            locked_agent_id="news",
            news_id="news-1",
        )

        resp = await client_with_analysis.post(
            "/api/v1/chat",
            headers=_bearer(token),
            json={"session_id": record.session_id, "message": "请分析"},
        )
        assert resp.status_code == 200
        assert "[新闻锚点]" in agent.last_message
        assert "标题：某热点事件" in agent.last_message
        assert "[证据卡片]" in agent.last_message
        assert "[未核实线索]" in agent.last_message
        assert "[用户问题]" in agent.last_message
        assert "请分析" in agent.last_message
