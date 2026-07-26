from __future__ import annotations
import logging
from collections.abc import Callable

from domain.agent.base import BaseAgent
from domain.shared.llm.ports import LLMPort
from infrastructure.skills.provider import SkillProvider
from infrastructure.tools.registry import ToolRegistry
from infrastructure.tools.executor import ToolExecutor
from infrastructure.mcp.runtime import MCPProxyRuntime
from domain.user.session.manager import SessionManager
from domain.shared.audit.logger import AuditLogger
from domain.agent.schema import AgentConfig
from domain.agent.dynamic_agent import DynamicAgent

logger = logging.getLogger(__name__)


class AgentFactory:
    """智能体工厂 — 根据 AgentConfig 创建 BaseAgent 实例。

    解耦 OrchestratorAgent 与具体 Agent 实现类。
    Orchestrator 只依赖 BaseAgent 接口 + AgentFactory，
    不 import 任何具体的 Agent 类。

    新增智能体类型时：
    - 如果是配置驱动的 → 零改动（DynamicAgent 自动处理）
    - 如果需要特殊逻辑 → 在工厂中加一个分支
    """

    def __init__(
        self,
        *,
        llm: LLMPort,
        skill_provider: SkillProvider,
        tool_registry: ToolRegistry,
        tool_executor: ToolExecutor,
        session_store: SessionManager,
        mcp_runtime: MCPProxyRuntime,
        audit_logger: AuditLogger,
        # 内置智能体的特殊构造器（如 TravelAgent 需要完整 Agent 主循环）
        builtin_builders: dict[str, Callable[[AgentConfig], BaseAgent]] | None = None,
    ) -> None:
        self._llm = llm
        self._skill_provider = skill_provider
        self._tool_registry = tool_registry
        self._tool_executor = tool_executor
        self._session_store = session_store
        self._mcp_runtime = mcp_runtime
        self._audit_logger = audit_logger
        self._builtin_builders = builtin_builders or {}

    def create(self, config: AgentConfig) -> BaseAgent:
        """根据配置创建智能体实例。

        工具白名单在 ``DynamicAgent`` 内通过 ``tool_executor.policy.filter_allowed_tools``
        强制执行：学术 Agent 即使在配置中误加 ``web-search``，也不会获得
        ``web_search`` 工具。``yunhe`` 等未配置白名单的 Agent 保持原行为。
        """
        # 内置智能体可能有特殊的构造逻辑（如 TravelAgent 包装完整 Agent）
        if config.source == "builtin" and config.id in self._builtin_builders:
            builder = self._builtin_builders[config.id]
            return builder(config)

        # 默认：用 DynamicAgent（配置驱动，零代码，具备完整 ReAct 工具执行能力）
        return DynamicAgent(
            config=config,
            llm=self._llm,
            skill_provider=self._skill_provider,
            tool_registry=self._tool_registry,
            tool_executor=self._tool_executor,
            session_store=self._session_store,
            mcp_runtime=self._mcp_runtime,
            audit_logger=self._audit_logger,
        )
