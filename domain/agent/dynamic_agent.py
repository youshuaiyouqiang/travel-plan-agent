from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncGenerator

from domain.agent.base import BaseAgent
from domain.agent.schema import AgentConfig
from infrastructure.llm.openai import OpenAILLM
from infrastructure.skills.provider import SkillProvider
from infrastructure.tools.executor import ToolExecutor
from infrastructure.tools.registry import ToolRegistry
from infrastructure.mcp.runtime import MCPProxyRuntime
from domain.user.session.manager import SessionManager
from domain.shared.audit.logger import AuditLogger
from domain.reasoning.engine import ReasoningEngine, AskUserNeeded, ConfirmationNeeded
from domain.safety.prompt_guard import PromptGuard

logger = logging.getLogger(__name__)


class DynamicAgent(BaseAgent):
    """通用动态智能体 — 由 AgentConfig 驱动，具备完整的 ReAct 工具执行能力。

    与旧版（仅 prompt 注入）的关键变化：
    1. 根据 config.skills / config.mcp_servers 筛选工具子集
    2. 通过 ReasoningEngine 执行完整的 ReAct 循环（推理 → 工具调用 → 观察）
    3. 通过 SessionManager 管理多轮对话上下文
    4. 通过 AuditLogger 记录 LLM 与工具调用
    """

    def __init__(
        self,
        *,
        config: AgentConfig,
        llm: OpenAILLM,
        skill_provider: SkillProvider,
        tool_registry: ToolRegistry,
        tool_executor: ToolExecutor,
        session_store: SessionManager,
        mcp_runtime: MCPProxyRuntime,
        audit_logger: AuditLogger,
    ) -> None:
        self._config = config
        self._llm = llm
        self._skill_provider = skill_provider
        self._session_store = session_store
        self._audit_logger = audit_logger
        self._mcp_runtime = mcp_runtime

        # 解析工具名列表
        self._tool_names = self._resolve_tools(config, skill_provider, mcp_runtime)

        # 从全局 registry 中筛选工具子集，构建专属 ToolRegistry
        self._agent_registry = ToolRegistry()
        for name in self._tool_names:
            if tool_registry.has(name):
                tool = tool_registry.get(name)
                self._agent_registry.register(tool)

        # 使用专属 ToolExecutor（绑定子集 registry + 全局 policy/audit）
        self._tool_executor = ToolExecutor(
            registry=self._agent_registry,
            policy=tool_executor.policy,
            audit_logger=audit_logger,
        )

        # 推理引擎（只持有子集工具）
        self._reasoning = ReasoningEngine(
            llm=llm,
            tool_registry=self._agent_registry,
            tool_executor=self._tool_executor,
            audit_logger=audit_logger,
        )

        logger.info(
            "DynamicAgent [%s] initialized: skills=%s mcp=%s resolved_tools=%s",
            config.id,
            config.skills,
            config.mcp_servers,
            self._tool_names,
        )

    @property
    def name(self) -> str:
        return self._config.id

    @property
    def description(self) -> str:
        return self._config.description

    def _resolve_tools(
        self,
        config: AgentConfig,
        skill_provider: SkillProvider,
        mcp_runtime: MCPProxyRuntime,
    ) -> list[str]:
        """根据 config.skills 和 config.mcp_servers 解析需要的工具名。

        1. 从 skill 中提取绑定的工具（openai.yaml 中 interface.tools）
        2. 从 MCP server 中提取工具（通过 catalog.list_tool_refs()）
        返回去重后的工具名列表。
        """
        tool_names: list[str] = []

        # 1. 从 skill 中提取绑定的工具
        for skill_name in config.skills:
            skill = skill_provider.get_skill(skill_name)
            if skill and skill.tools:
                tool_names.extend(skill.tools)
                logger.debug("Skill [%s] provides tools: %s", skill_name, skill.tools)

        # 2. 从 MCP server 中提取工具
        for server_id in config.mcp_servers:
            for ref in mcp_runtime.catalog.list_tool_refs():
                if ref.server_identifier == server_id:
                    tool_names.append(ref.proxy_name)
                    logger.debug("MCP [%s] provides tool: %s", server_id, ref.proxy_name)

        # 去重并保持顺序
        seen: set[str] = set()
        unique: list[str] = []
        for name in tool_names:
            if name not in seen:
                seen.add(name)
                unique.append(name)
        return unique

    def _build_system_prompt(self) -> str:
        """构建 system prompt，注入 skill 说明和 MCP 描述。"""
        prompt = self._config.system_prompt

        if self._config.skills:
            prompt += "\n\n## 可用技能\n"
            for skill_name in self._config.skills:
                skill = self._skill_provider.get_skill(skill_name)
                if skill:
                    prompt += f"\n### {skill.display_name}\n"
                    prompt += f"{skill.description}\n"
                    prompt += f"提示: {skill.default_prompt}\n"
                    if skill.tools:
                        prompt += f"工具: {', '.join(skill.tools)}\n"

        if self._config.mcp_servers:
            prompt += "\n\n## 可用 MCP 服务\n"
            for server_id in self._config.mcp_servers:
                prompt += f"- {server_id}\n"

        return prompt

    async def chat(
        self,
        *,
        session_id: str,
        message: str,
        user_id: str | None = None,
        trace_id: str = "",
        **kwargs,
    ) -> dict:
        # ===== 输入消毒：Prompt 注入防御 =====
        cleaned, warnings = PromptGuard.sanitize(message)
        if warnings:
            logger.warning("Prompt injection detected: %s", warnings)
            if self._audit_logger:
                self._audit_logger.log_api_boundary(
                    session_id=session_id,
                    user_id=user_id or "",
                    trace_id=trace_id,
                    direction="request",
                    endpoint="dynamic_agent.chat",
                    method="INTERNAL",
                    payload=f"prompt_injection_blocked: {warnings}",
                    agent_id=self._config.id,
                )
        message = cleaned

        memory_scope = str(user_id or session_id)
        trace_id = trace_id or uuid.uuid4().hex[:16]

        self._llm.set_audit_context(session_id=session_id, user_id=memory_scope, trace_id=trace_id)
        self._reasoning.set_audit_context(session_id=session_id, user_id=memory_scope, trace_id=trace_id)

        # 加载会话历史
        session = self._session_store.get(session_id)
        # 写入 user_id 到 session（首次创建时绑定，后续保持不变）
        if user_id and not session.user_id:
            session.user_id = memory_scope
        session.append("user", message)

        system_prompt = self._build_system_prompt()

        status = "final_answer"
        try:
            reply = await self._reasoning.run(
                system_prompt=system_prompt,
                user_message=message,
                force_tool=False,
            )
        except AskUserNeeded as exc:
            reply = exc.question
            status = "need_input"
        except ConfirmationNeeded as exc:
            reply = exc.prompt
            status = "need_input"
        except Exception as e:
            logger.error("DynamicAgent chat error: %s", e)
            reply = f"抱歉，处理您的请求时出现了错误：{e}"
            status = "final_answer"

        # 保存会话
        session.append("assistant", reply)
        self._session_store.save(session, user_id=memory_scope)

        return {
            "status": status,
            "reply": reply,
            "active_agent": self._config.id,
            "agent_actions": [],
        }

    async def chat_stream(
        self,
        *,
        session_id: str,
        message: str,
        user_id: str | None = None,
        trace_id: str = "",
        **kwargs,
    ) -> AsyncGenerator[dict, None]:
        # ===== 输入消毒：Prompt 注入防御 =====
        cleaned, warnings = PromptGuard.sanitize(message)
        if warnings:
            logger.warning("Prompt injection detected: %s", warnings)
            if self._audit_logger:
                self._audit_logger.log_api_boundary(
                    session_id=session_id,
                    user_id=user_id or "",
                    trace_id=trace_id,
                    direction="request",
                    endpoint="dynamic_agent.chat_stream",
                    method="INTERNAL",
                    payload=f"prompt_injection_blocked: {warnings}",
                    agent_id=self._config.id,
                )
        message = cleaned

        memory_scope = str(user_id or session_id)
        trace_id = trace_id or uuid.uuid4().hex[:16]

        self._llm.set_audit_context(session_id=session_id, user_id=memory_scope, trace_id=trace_id)
        self._reasoning.set_audit_context(session_id=session_id, user_id=memory_scope, trace_id=trace_id)

        # 加载会话历史
        session = self._session_store.get(session_id)
        # 写入 user_id 到 session（首次创建时绑定，后续保持不变）
        if user_id and not session.user_id:
            session.user_id = memory_scope
        session.append("user", message)

        # 发送路由事件
        yield {"type": "route", "data": self._config.id}
        yield {"type": "status", "data": "thinking"}

        system_prompt = self._build_system_prompt()

        full_reply = ""
        status = "final_answer"
        try:
            async for chunk in self._reasoning.run_stream(
                system_prompt=system_prompt,
                user_message=message,
                force_tool=False,
            ):
                if chunk.startswith("__status__:"):
                    # 状态通知，转为 tool_status 事件
                    yield {"type": "tool_status", "data": chunk[len("__status__:") :]}
                else:
                    full_reply += chunk
                    yield {"type": "chunk", "data": chunk}
        except AskUserNeeded as exc:
            full_reply = exc.question
            status = "need_input"
            yield {"type": "chunk", "data": full_reply}
        except ConfirmationNeeded as exc:
            full_reply = exc.prompt
            status = "need_input"
            yield {"type": "chunk", "data": full_reply}
        except Exception as e:
            logger.error("DynamicAgent chat_stream error: %s", e)
            full_reply = f"抱歉，处理您的请求时出现了错误：{e}"
            yield {"type": "chunk", "data": full_reply}

        # 保存会话（P0-4：session.user_id 已绑定，save 会写入 sessions.user_id 列）
        session.append("assistant", full_reply)
        self._session_store.save(session, user_id=memory_scope)

        yield {"type": "done", "data": status}
