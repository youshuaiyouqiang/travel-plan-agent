from __future__ import annotations
import logging
from collections.abc import Callable

from domain.agent.base import BaseAgent
from infrastructure.llm.openai import OpenAILLM
from infrastructure.skills.provider import SkillProvider
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
        llm: OpenAILLM,
        skill_provider: SkillProvider,
        # 内置智能体的特殊构造器（如 TravelAgent 需要完整 Agent 主循环）
        builtin_builders: dict[str, Callable[[AgentConfig], BaseAgent]] | None = None,
    ) -> None:
        self._llm = llm
        self._skill_provider = skill_provider
        self._builtin_builders = builtin_builders or {}

    def create(self, config: AgentConfig) -> BaseAgent:
        """根据配置创建智能体实例。"""
        # 内置智能体可能有特殊的构造逻辑（如 TravelAgent 包装完整 Agent）
        if config.source == "builtin" and config.id in self._builtin_builders:
            builder = self._builtin_builders[config.id]
            return builder(config)

        # 默认：用 DynamicAgent（配置驱动，零代码）
        return DynamicAgent(
            config=config,
            llm=self._llm,
            skill_provider=self._skill_provider,
        )
