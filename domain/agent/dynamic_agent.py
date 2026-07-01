from __future__ import annotations
import logging
from collections.abc import AsyncGenerator

from domain.agent.base import BaseAgent
from infrastructure.llm.openai import OpenAILLM
from infrastructure.skills.provider import SkillProvider
from domain.agent.schema import AgentConfig

logger = logging.getLogger(__name__)


class DynamicAgent(BaseAgent):
    """通用动态智能体 — 由 AgentConfig 驱动，不硬编码任何字段。

    用于用户自定义智能体。
    构造函数只接收 AgentConfig + 依赖（LLM、SkillProvider），
    不再接收 10 个独立字段。

    【商用限制 — 当前实现的不足】
    1. 无会话记忆：每次调用都是独立的 system+user，不保留对话历史。
       商用产品应注入 SessionManager，维护多轮对话上下文。
    2. 无工具执行：_build_prompt 只把 skill 描述注入 prompt，
       但不实际调用 skill 对应的工具。用户配置了 amap-maps 也无法真正查地图。
       后续应接入 ToolExecutor，根据 skills 列表加载对应工具。
    3. 无审计：不记录 LLM 调用日志。

    这些是 MVP 阶段的已知限制，商用前必须补齐。
    """

    def __init__(
        self,
        *,
        config: AgentConfig,
        llm: OpenAILLM,
        skill_provider: SkillProvider,
    ) -> None:
        self._config = config
        self._llm = llm
        self._skill_provider = skill_provider

    @property
    def name(self) -> str:
        return self._config.id

    @property
    def description(self) -> str:
        return self._config.description

    async def chat(self, *, session_id: str, message: str, user_id: str | None = None, **kwargs) -> dict:
        prompt = self._build_prompt()
        # 注意：OpenAILLM 的方法是 complete / stream_complete，不是 chat / chat_stream
        reply = await self._llm.complete(
            system=prompt,
            messages=[{"role": "user", "content": message}],
        )
        return {
            "status": "completed",
            "reply": reply,
            "active_agent": self._config.id,
            "agent_actions": [],
        }

    async def chat_stream(self, *, session_id: str, message: str, user_id: str | None = None, **kwargs) -> AsyncGenerator[dict, None]:
        yield {"type": "route", "data": self._config.id}
        yield {"type": "status", "data": "thinking"}

        prompt = self._build_prompt()
        async for chunk in self._llm.stream_complete(
            system=prompt,
            messages=[{"role": "user", "content": message}],
        ):
            yield {"type": "chunk", "data": chunk}

        yield {"type": "done", "data": "completed"}

    def _build_prompt(self) -> str:
        """构建 system prompt，注入 skill 说明。"""
        prompt = self._config.system_prompt

        if self._config.skills:
            prompt += "\n\n## 可用技能\n"
            for skill_name in self._config.skills:
                skill = self._skill_provider.get_skill(skill_name)
                if skill:
                    prompt += f"\n### {skill.display_name}\n"
                    prompt += f"{skill.description}\n"
                    prompt += f"提示: {skill.default_prompt}\n"

        return prompt
