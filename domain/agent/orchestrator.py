from __future__ import annotations
import logging
import time
from collections.abc import AsyncGenerator, Callable

from domain.agent.base import BaseAgent
from infrastructure.llm.openai import OpenAILLM
from domain.agent.schema import AgentConfig
from domain.agent.factory import AgentFactory
from domain.agent.repository import CustomAgentRepository

logger = logging.getLogger(__name__)


class OrchestratorAgent(BaseAgent):
    """总调度智能体 — LLM 路由 + 工厂创建。

    依赖关系（全部是抽象/接口，不依赖具体类）：
    - AgentFactory：创建 Agent 实例
    - CustomAgentRepository：读取用户自定义智能体配置
    - BaseAgent：统一接口

    不 import DynamicAgent、TravelAgent 等具体类。
    """

    # 智能体描述缓存时间（秒），避免每次路由都查数据库
    _DESC_CACHE_TTL = 60

    def __init__(
        self,
        *,
        llm: OpenAILLM,
        factory: AgentFactory,
        builtin_configs: list[AgentConfig],
        custom_repo: CustomAgentRepository,
        default_agent: str = "travel",
    ) -> None:
        self._llm = llm
        self._factory = factory
        self._builtin_configs = {c.id: c for c in builtin_configs}
        self._custom_repo = custom_repo
        self._default = default_agent
        # 缓存已创建的 Agent 实例（内置智能体常驻，自定义按需创建）
        # 【商用注意】无界缓存会导致内存泄漏。生产环境应使用 LRU 或 TTL 淘汰策略。
        # 简单方案：限制缓存大小，超过时淘汰最久未访问的。
        self._agent_cache: dict[str, BaseAgent] = {}
        self._MAX_CACHE_SIZE = 100  # 最多缓存 100 个 Agent 实例
        # 智能体描述缓存（避免每次路由都查 DB）
        self._desc_cache: dict[str, tuple[str, float]] = {}  # user_id -> (desc, timestamp)

    @property
    def name(self) -> str:
        return "orchestrator"

    @property
    def description(self) -> str:
        return "总调度智能体，负责将用户需求路由给专业智能体。"

    def __getattr__(self, name: str):
        """委托未定义的公共方法到默认智能体（会话/调试/记忆等），保持向后兼容。

        现有 /api/sessions、/debug/* 等端点调用 list_user_sessions、
        snapshot_session 等方法，这些方法在默认 travel 智能体的底层 Agent 上实现。
        通过委托转发，避免改动现有端点代码。
        """
        if name.startswith('_'):
            raise AttributeError(name)
        default_agent = self._get_or_create_agent(self._default, None)
        return getattr(default_agent, name)

    def _get_all_descriptions(self, user_id: str | None) -> str:
        """获取所有可用智能体的描述（供 LLM 路由），带缓存。"""
        cache_key = user_id or "anonymous"
        now = time.time()

        # 缓存命中
        if cache_key in self._desc_cache:
            desc, ts = self._desc_cache[cache_key]
            if now - ts < self._DESC_CACHE_TTL:
                return desc

        # 重新构建
        configs = list(self._builtin_configs.values())
        if user_id:
            configs += self._custom_repo.list_by_user(user_id)
        configs += self._custom_repo.list_public()
        desc = "\n".join(f"- {c.id}: {c.description}" for c in configs)

        self._desc_cache[cache_key] = (desc, now)
        return desc

    async def _route(self, message: str, user_id: str | None) -> str:
        """LLM 路由。"""
        if len(message.strip()) < 2:
            return self._default

        agents_desc = self._get_all_descriptions(user_id)
        prompt = (
            f"你是 Claw 系统的智能路由器。判断用户消息应该交给哪个专业智能体处理。\n\n"
            f"可用智能体：\n{agents_desc}\n\n"
            f"规则：只返回智能体 ID，不要解释。无法判断返回 {self._default}。\n\n"
            f"用户消息：{message}\n\n智能体 ID："
        )

        try:
            # OpenAILLM.complete(system=, messages=) — 没有 chat() 方法
            resp = await self._llm.complete(
                system="你是 Claw 系统的智能路由器。判断用户消息应该交给哪个专业智能体处理。只返回智能体 ID，不要解释。无法判断返回默认值。",
                messages=[{"role": "user", "content": f"可用智能体：\n{agents_desc}\n\n默认：{self._default}\n\n用户消息：{message}"}],
            )
            agent_id = resp.strip().lower()
            # 验证 ID 是否存在
            if not self._agent_exists(agent_id, user_id):
                agent_id = self._default
        except Exception as e:
            logger.error("Router failed: %s", e)
            agent_id = self._default

        return agent_id

    def _agent_exists(self, agent_id: str, user_id: str | None) -> bool:
        if agent_id in self._builtin_configs:
            return True
        if user_id:
            config = self._custom_repo.get(agent_id)
            if config and (config.user_id == user_id or config.is_public):
                return True
        return False

    def _get_or_create_agent(self, agent_id: str, user_id: str | None) -> BaseAgent:
        """获取或创建 Agent 实例（通过工厂，不直接 import 具体类）。"""
        if agent_id in self._agent_cache:
            return self._agent_cache[agent_id]

        # 获取配置
        if agent_id in self._builtin_configs:
            config = self._builtin_configs[agent_id]
        else:
            config = self._custom_repo.get(agent_id)

        if not config:
            # fallback
            config = self._builtin_configs[self._default]

        # 通过工厂创建（解耦关键点）
        agent = self._factory.create(config)

        # 缓存淘汰：超过上限时清空（简单 LRU 策略）
        if len(self._agent_cache) >= self._MAX_CACHE_SIZE:
            # 保留内置智能体，淘汰自定义智能体
            self._agent_cache = {
                k: v for k, v in self._agent_cache.items()
                if k in self._builtin_configs
            }
        self._agent_cache[agent_id] = agent
        return agent

    async def chat(self, *, session_id: str, message: str,
                   user_id: str | None = None, agent_id: str | None = None,
                   trace_id: str = "") -> dict:
        # 指定 agent_id 时直接使用
        if agent_id:
            agent = self._get_or_create_agent(agent_id, user_id)
        else:
            # LLM 自动路由
            routed_id = await self._route(message, user_id)
            agent = self._get_or_create_agent(routed_id, user_id)

        return await agent.chat(session_id=session_id, message=message, user_id=user_id, trace_id=trace_id)

    async def chat_stream(self, *, session_id: str, message: str,
                          user_id: str | None = None, agent_id: str | None = None,
                          trace_id: str = "") -> AsyncGenerator[dict, None]:
        if agent_id:
            agent = self._get_or_create_agent(agent_id, user_id)
        else:
            routed_id = await self._route(message, user_id)
            agent = self._get_or_create_agent(routed_id, user_id)

        async for event in agent.chat_stream(session_id=session_id, message=message, user_id=user_id, trace_id=trace_id):
            yield event
