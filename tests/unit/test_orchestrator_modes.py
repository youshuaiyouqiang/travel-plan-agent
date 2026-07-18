"""Task 3 mode-first 调度的单元测试。

覆盖范围：
- ``yunhe_default`` 模式下专家问题委派给专业 Agent，回复后控制权回到云合
- ``agent_locked`` 模式下所有消息路由到锁定 Agent，控制权不回云合
- ``yunhe_default`` 模式下简单通用问题由云合直接回答
- ``news_analysis_locked`` 模式下路由到新闻 Agent

设计要点：使用 stub LLM/Factory/CustomRepo，避免真实 LLM 调用。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass

import pytest

from domain.agent.base import BaseAgent
from domain.agent.orchestrator import OrchestratorAgent
from domain.agent.schema import AgentConfig


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


@dataclass
class _StubToolCall:
    name: str = ""
    arguments: dict | None = None
    id: str = ""


@dataclass
class _StubLLMResponse:
    content: str = ""
    tool_calls: list = None

    def __post_init__(self):
        if self.tool_calls is None:
            self.tool_calls = []

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


class _StubLLM:
    """LLM stub：根据消息内容返回固定的路由结果。

    - 含 ``论文`` / ``RAG`` → ``academic``
    - 其他 → ``travel``
    """

    async def complete(self, *, system: str, messages: list[dict]) -> str:
        user_msg = messages[-1]["content"] if messages else ""
        if "论文" in user_msg or "RAG" in user_msg:
            return "academic"
        return "travel"

    async def complete_with_tools(self, *, system: str, messages: list[dict], tools: list):
        # 重构后的 chat() 不再走 complete_with_tools；保留以防回退路径调用
        return _StubLLMResponse(content="stub reply")

    async def stream_complete(self, *, system: str, messages: list[dict]) -> AsyncGenerator[str, None]:
        yield "云合直接回复"


class _StubAgent(BaseAgent):
    """记录最后一次被调用的消息，便于断言。"""

    def __init__(self, agent_id: str) -> None:
        self._id = agent_id
        self.last_message: str | None = None

    @property
    def name(self) -> str:
        return self._id

    @property
    def description(self) -> str:
        return f"stub {self._id}"

    async def chat(self, *, session_id: str, message: str, user_id: str | None = None, **kwargs) -> dict:
        self.last_message = message
        return {
            "status": "final_answer",
            "reply": f"[{self._id}] {message}",
            "active_agent": self._id,
            "agent_actions": [],
        }

    async def chat_stream(self, *, session_id: str, message: str, user_id: str | None = None, **kwargs) -> AsyncGenerator[dict, None]:
        self.last_message = message
        yield {"type": "chunk", "data": f"[{self._id}] {message}"}
        yield {"type": "done", "data": "final_answer"}


class _StubFactory:
    """按 AgentConfig.id 创建 _StubAgent，并暴露已创建实例供测试断言。"""

    def __init__(self) -> None:
        self.created: dict[str, _StubAgent] = {}

    def create(self, config: AgentConfig) -> BaseAgent:
        agent = _StubAgent(config.id)
        self.created[config.id] = agent
        return agent


class _StubCustomRepo:
    def list_by_user(self, user_id: str | None):
        return []

    def list_public(self):
        return []

    def get(self, agent_id: str):
        return None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_configs() -> list[AgentConfig]:
    return [
        AgentConfig(id="yunhe", name="云合", description="调度员"),
        AgentConfig(id="academic", name="学术", description="论文检索"),
        AgentConfig(id="travel", name="旅行", description="行程规划"),
        AgentConfig(id="news", name="新闻", description="新闻深度研判"),
    ]


@pytest.fixture
def factory() -> _StubFactory:
    return _StubFactory()


@pytest.fixture
def orchestrator(factory) -> OrchestratorAgent:
    return OrchestratorAgent(
        llm=_StubLLM(),
        factory=factory,
        builtin_configs=_make_configs(),
        custom_repo=_StubCustomRepo(),
        default_agent="yunhe",
    )


# ---------------------------------------------------------------------------
# mode-first 路由测试
# ---------------------------------------------------------------------------


class TestModeFirstRouting:
    """验证 orchestrator.chat 按 session mode 决策路由。"""

    @pytest.mark.asyncio
    async def test_default_mode_returns_to_yunhe_after_single_delegation(self, orchestrator):
        result = await orchestrator.chat("s1", "u1", "检索 RAG 论文", "yunhe_default", None)
        assert result["handled_by"] == "academic"
        assert result["next_controller"] == "yunhe"
        # 既有字段保留，便于 chat.py 适配
        assert result["status"] == "final_answer"
        assert "reply" in result

    @pytest.mark.asyncio
    async def test_agent_locked_mode_stays_with_locked_agent(self, orchestrator, factory):
        result = await orchestrator.chat("s1", "u1", "随便聊点什么", "agent_locked", "academic")
        assert result["handled_by"] == "academic"
        # 锁定会话：控制权不回到云合
        assert result["next_controller"] == "academic"
        # 路由到 academic，不应触发 yunhe 直答
        assert "academic" in factory.created
        assert factory.created["academic"].last_message == "随便聊点什么"

    @pytest.mark.asyncio
    async def test_default_mode_simple_question_handled_by_yunhe(self, orchestrator, factory):
        result = await orchestrator.chat("s1", "u1", "你好", "yunhe_default", None)
        assert result["handled_by"] == "yunhe"
        assert result["next_controller"] == "yunhe"
        # 简单闲聊不应委派给专业 Agent
        assert "academic" not in factory.created
        assert "travel" not in factory.created

    @pytest.mark.asyncio
    async def test_news_analysis_locked_routes_to_news_agent(self, orchestrator, factory):
        result = await orchestrator.chat(
            "s1", "u1", "继续研判这条新闻", "news_analysis_locked", "news"
        )
        assert result["handled_by"] == "news"
        assert result["next_controller"] == "news"

    @pytest.mark.asyncio
    async def test_default_mode_specialist_question_does_not_lock(self, orchestrator):
        """默认模式下单轮委派回复后，下一轮简单问题仍由云合直答。"""
        first = await orchestrator.chat("s1", "u1", "检索 RAG 论文", "yunhe_default", None)
        assert first["handled_by"] == "academic"
        assert first["next_controller"] == "yunhe"

        second = await orchestrator.chat("s1", "u1", "谢谢", "yunhe_default", None)
        assert second["handled_by"] == "yunhe"
        assert second["next_controller"] == "yunhe"
