from __future__ import annotations
import json
import logging
import time
import uuid
from dataclasses import dataclass
from collections.abc import AsyncGenerator

from application.session.schema import SessionMode
from domain.agent.base import BaseAgent
from infrastructure.llm.openai import OpenAILLM
from domain.agent.schema import AgentConfig
from domain.agent.factory import AgentFactory
from domain.agent.repository import CustomAgentRepository
from domain.safety.prompt_guard import PromptGuard

logger = logging.getLogger(__name__)


# ===== 委派上下文 =====


@dataclass
class DelegationContext:
    """委派上下文 — 跟踪当前会话的活跃委派状态。"""

    agent_id: str
    status: str = "active"  # "active" | "completed" | "released"
    started_at: float = 0.0
    last_interaction: float = 0.0
    delegation_count: int = 0

    def is_active(self) -> bool:
        return self.status == "active"

    def touch(self) -> None:
        self.last_interaction = time.time()


# ===== mode-first 路由决策 =====


@dataclass
class RouteDecision:
    """mode-first 路由决策结果。

    - ``agent_id`` 为 ``None`` 表示云合直接回答（default 模式下的简单通用问题）
    - ``delegated`` 表示是否委派给子 Agent
    - ``reason`` 记录决策路径：``locked_session`` / ``yunhe_direct`` / ``specialist_selected``
    """

    agent_id: str | None
    delegated: bool
    reason: str


# ===== 云合 meta-tools（调度系统能力，不经过 ToolRegistry） =====

YUNHE_META_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "delegate_to",
            "description": "将任务委派给专业智能体处理。当你无法直接回答、需要专业工具时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "目标智能体 ID（从可用智能体列表中选择）",
                    },
                    "message": {
                        "type": "string",
                        "description": "要委派给智能体的消息（通常是用户的原始请求）",
                    },
                },
                "required": ["agent_id", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_available_agents",
            "description": "列出所有可用的专业智能体及其能力描述。不确定该委派给谁时使用。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


class OrchestratorAgent(BaseAgent):
    """云合 — 通用智能体 + 调度者。

    核心变化（Phase 3）：
    1. 不再靠 prompt 路由（选一个 agent 就完事）
    2. 改为 LLM function calling，云合自主决定直接回复 or 委派
    3. 云合自身直答（三层决策：Tier 0 快路径 / Tier 1 function calling / Tier 2 委派执行）
    4. 支持多次委派（多智能体协作），上限 3 次
    5. 委派上下文状态机：IDLE ↔ DELEGATED
    6. 保留原有 prompt 路由（_route()）作为兜底

    兼容设计：
    - default_agent="travel"：传统模式，route → delegate（完全向后兼容）
    - default_agent="yunhe"：新模式，三层决策 + function calling 委派
    - __getattr__ 始终委托到 travel agent 的底层实现（会话/调试/记忆）
    """

    _DESC_CACHE_TTL = 60
    _MAX_DELEGATIONS = 3
    _DELEGATION_TIMEOUT = 1800  # 30 分钟

    # Tier 0：规则快路径
    _FAST_CHAT: set[str] = {
        "你好",
        "hello",
        "hi",
        "谢谢",
        "thanks",
        "收到",
        "嗯",
        "哦",
        "哈",
        "嘿",
        "好的",
        "ok",
        "okay",
        "bye",
        "再见",
        "拜拜",
        "晚安",
        "早安",
    }

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

        # 云合配置（从 YAML 加载，运行时注入可用智能体列表）
        self._yunhe_config = self._builtin_configs.get("yunhe")
        self._yunhe_mode = default_agent == "yunhe" and self._yunhe_config is not None

        # Agent 实例缓存
        # P2-7：缓存 key 改为 (agent_id, user_id or "")，避免跨用户复用 agent 实例
        self._agent_cache: dict[tuple[str, str], BaseAgent] = {}
        self._MAX_CACHE_SIZE = 100

        # 智能体描述缓存
        self._desc_cache: dict[str, tuple[str, float]] = {}

        # 委派上下文状态机：session_id → DelegationContext
        self._delegation_contexts: dict[str, DelegationContext] = {}

        # 用于 __getattr__ 委托的工具代理（travel agent 底层实现）
        self._utility_agent_id: str = "travel"

        logger.info(
            "OrchestratorAgent: default=%s yunhe_mode=%s",
            self._default,
            self._yunhe_mode,
        )

    # ===== 接口 =====

    @property
    def name(self) -> str:
        return "yunhe" if self._yunhe_mode else "orchestrator"

    @property
    def description(self) -> str:
        if self._yunhe_config:
            return self._yunhe_config.description
        return "总调度智能体，负责将用户需求路由给专业智能体。"

    def __getattr__(self, name: str):
        """委托未定义的公共方法到 travel agent（会话/调试/记忆等），保持向后兼容。

        即使 default_agent="yunhe"，list_user_sessions/list_mcp_servers 等
        工具方法仍委托给 travel agent 的底层实现（domain/travel/core.py:Agent）。
        """
        if name.startswith("_"):
            raise AttributeError(name)
        agent = self._get_or_create_agent(self._utility_agent_id, None)
        return getattr(agent, name)

    # ===== 智能体描述（供 LLM 路由 / 委派） =====

    def _get_all_descriptions(self, user_id: str | None) -> str:
        cache_key = user_id or "anonymous"
        now = time.time()
        if cache_key in self._desc_cache:
            desc, ts = self._desc_cache[cache_key]
            if now - ts < self._DESC_CACHE_TTL:
                return desc

        configs: list[AgentConfig] = []
        # 云合模式下，云合自身不列入可委派列表
        for c in self._builtin_configs.values():
            if c.id != "yunhe":
                configs.append(c)
        if user_id:
            configs += self._custom_repo.list_by_user(user_id)
        configs += self._custom_repo.list_public()
        desc = "\n".join(f"- {c.id}: {c.description}" for c in configs)
        self._desc_cache[cache_key] = (desc, now)
        return desc

    # ===== 兼容模式：prompt 路由（兜底） =====

    async def _route(self, message: str, user_id: str | None) -> str:
        """LLM 路由 — 保留作为 function calling 委派失败时的兜底。"""
        if len(message.strip()) < 2:
            return self._utility_agent_id

        agents_desc = self._get_all_descriptions(user_id)
        try:
            resp = await self._llm.complete(
                system="你是 Claw 系统的智能路由器。判断用户消息应该交给哪个专业智能体处理。只返回智能体 ID，不要解释。无法判断返回默认值。",
                messages=[
                    {
                        "role": "user",
                        "content": f"可用智能体：\n{agents_desc}\n\n默认：{self._utility_agent_id}\n\n用户消息：{message}",
                    }
                ],
            )
            agent_id = resp.strip().lower()
            if not self._agent_exists(agent_id, user_id):
                agent_id = self._utility_agent_id
        except Exception as e:
            logger.error("Router failed: %s", e)
            agent_id = self._utility_agent_id
        return agent_id

    def _agent_exists(self, agent_id: str, user_id: str | None) -> bool:
        if agent_id in self._builtin_configs and agent_id != "yunhe":
            return True
        if user_id:
            config = self._custom_repo.get(agent_id)
            if config and (config.user_id == user_id or config.is_public):
                return True
        return False

    def _get_or_create_agent(self, agent_id: str, user_id: str | None) -> BaseAgent:
        # P2-7：缓存 key 含 user_id，避免跨用户复用 agent 实例
        cache_key = (agent_id, user_id or "")
        if cache_key in self._agent_cache:
            return self._agent_cache[cache_key]
        config: AgentConfig | None
        if agent_id in self._builtin_configs:
            config = self._builtin_configs[agent_id]
        else:
            config = self._custom_repo.get(agent_id)
        if not config:
            config = self._builtin_configs[self._utility_agent_id]

        agent = self._factory.create(config)

        if len(self._agent_cache) >= self._MAX_CACHE_SIZE:
            # 清理：保留 builtin agent（其 key 的 agent_id 在 _builtin_configs）
            self._agent_cache = {k: v for k, v in self._agent_cache.items() if k[0] in self._builtin_configs}
        self._agent_cache[cache_key] = agent
        return agent

    # ===== 云合模式：prompt 构建 =====

    def _build_yunhe_prompt(self, user_id: str | None) -> str:
        """构建云合的 system_prompt，动态注入可用智能体列表。"""
        if not self._yunhe_config:
            return ""
        agents_desc = self._get_all_descriptions(user_id)
        return self._yunhe_config.system_prompt.replace("{agent_list}", agents_desc)

    # ===== 云合模式：Tier 0 快路径 =====

    def _is_fast_chat(self, message: str) -> bool:
        """Tier 0：判断是否为极短闲聊，可跳过 function calling。"""
        stripped = message.strip().lower()
        return stripped in self._FAST_CHAT or len(stripped) <= 1

    def _is_simple_general_question(self, message: str) -> bool:
        """mode-first 路由：判断是否为简单通用问题，云合可直接回答。

        复用既有 ``_is_fast_chat`` 规则；后续可在此扩展更细致的意图判定。
        """
        return self._is_fast_chat(message)

    # ===== mode-first 路由决策 =====

    async def _select_handler(
        self,
        mode: SessionMode,
        locked_agent_id: str | None,
        message: str,
        user_id: str | None,
    ) -> RouteDecision:
        """根据会话模式、锁定 Agent 与消息内容做路由决策。

        - ``agent_locked`` / ``news_analysis_locked``：始终路由到锁定 Agent
        - ``yunhe_default`` + 简单通用问题：云合直答
        - ``yunhe_default`` + 专家问题：单跳委派给专业 Agent
        """
        if mode in {"agent_locked", "news_analysis_locked"}:
            if not locked_agent_id:
                # 防御性：锁定模式缺失 locked_agent_id 时退回云合直答
                return RouteDecision(None, False, "yunhe_direct")
            return RouteDecision(locked_agent_id, True, "locked_session")
        if self._is_simple_general_question(message):
            return RouteDecision(None, False, "yunhe_direct")
        return await self._select_one_specialist(message, user_id)

    async def _select_one_specialist(
        self,
        message: str,
        user_id: str | None,
    ) -> RouteDecision:
        """默认模式下单跳委派：选一个专业 Agent 处理。"""
        agent_id = await self._route(message, user_id)
        return RouteDecision(agent_id=agent_id, delegated=True, reason="specialist_selected")

    async def _yunhe_direct_reply(self, message: str, user_id: str | None) -> str:
        """云合直接回答（收集流式 chunk 为单字符串，供同步 ``chat`` 使用）。"""
        parts: list[str] = []
        async for event in self._direct_reply(session_id="", message=message, user_id=user_id):
            if event.get("type") == "chunk":
                parts.append(str(event.get("data", "")))
        return "".join(parts)

    # ===== 云合模式：直接回复（不注入 tools） =====

    async def _direct_reply(self, session_id: str, message: str, user_id: str | None) -> AsyncGenerator[dict, None]:
        """直接 LLM 回复（不注入 tools，省 token）。"""
        system_prompt = self._build_yunhe_prompt(user_id)
        try:
            yield {"type": "status", "data": "thinking"}
            async for chunk in self._llm.stream_complete(
                system=system_prompt,
                messages=[{"role": "user", "content": message}],
            ):
                yield {"type": "chunk", "data": chunk}
        except Exception as e:
            logger.error("Yunhe direct_reply failed: %s", e)
            yield {"type": "chunk", "data": f"抱歉，出了点问题：{e}"}
        yield {"type": "done", "data": "final_answer"}

    # ===== 云合模式：function calling 委派主循环（Tier 1 + Tier 2） =====

    async def _yunhe_chat_stream(
        self,
        session_id: str,
        message: str,
        user_id: str | None,
    ) -> AsyncGenerator[dict, None]:
        """云合三层决策流程（Tier 0 → Tier 1 → Tier 2）。

        仅在 self._yunhe_mode 时使用此流程。
        """
        # ===== 输入消毒：Prompt 注入防御 =====
        cleaned, warnings = PromptGuard.sanitize(message)
        if warnings:
            logger.warning("Prompt injection detected: %s", warnings)
        message = cleaned

        # ===== Tier 0：规则快路径 =====
        if self._is_fast_chat(message):
            logger.info("Yunhe Tier 0: fast chat for '%s'", message[:30])
            async for event in self._direct_reply(session_id, message, user_id):
                yield event
            return

        # ===== Tier 1 + Tier 2：function calling 委派循环 =====
        yield {"type": "route", "data": "yunhe"}
        yield {"type": "status", "data": "thinking"}

        system_prompt = self._build_yunhe_prompt(user_id)
        working_messages: list[dict] = [{"role": "user", "content": message}]
        delegation_count = 0
        # P2-8：独立迭代上限，防止 LLM 反复调用非委派 tool（如 list_available_agents）导致死循环
        yunhe_iteration = 0
        _MAX_YUNHE_ITERATIONS = 10

        while delegation_count < self._MAX_DELEGATIONS:
            yunhe_iteration += 1
            if yunhe_iteration > _MAX_YUNHE_ITERATIONS:
                logger.warning(
                    "Yunhe loop hit max_yunhe_iterations=%d, breaking",
                    _MAX_YUNHE_ITERATIONS,
                )
                yield {"type": "chunk", "data": "\n\n（已达到推理上限）"}
                break
            try:
                llm_resp = await self._llm.complete_with_tools(
                    system=system_prompt,
                    messages=working_messages,
                    tools=YUNHE_META_TOOLS,
                )
            except Exception as e:
                logger.error("Yunhe function calling failed: %s, falling back to prompt route", e)
                # 兜底：prompt 路由
                routed_id = await self._route(message, user_id)
                agent = self._get_or_create_agent(routed_id, user_id)
                yield {"type": "route", "data": routed_id}
                async for event in agent.chat_stream(
                    session_id=session_id,
                    message=message,
                    user_id=user_id,
                ):
                    yield event
                return

            # LLM 没有调用 tool → 直接回复（通用问答）
            if not llm_resp.has_tool_calls or not llm_resp.tool_calls:
                content = llm_resp.content or ""
                if content.strip():
                    yield {"type": "chunk", "data": content}
                yield {"type": "done", "data": "final_answer"}
                return

            # 处理 tool calls
            for tool_call in llm_resp.tool_calls:
                if tool_call.name == "delegate_to":
                    agent_id = tool_call.arguments.get("agent_id", "")
                    delegated_message = tool_call.arguments.get("message", message)

                    if not self._agent_exists(agent_id, user_id):
                        working_messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id or str(uuid.uuid4()),
                                "content": json.dumps({"error": f"智能体 {agent_id} 不存在"}),
                            }
                        )
                        continue

                    # 流式输出委派事件
                    yield {"type": "route", "data": agent_id}
                    yield {"type": "status", "data": f"正在转接 {agent_id}..."}

                    # 执行委派
                    agent = self._get_or_create_agent(agent_id, user_id)
                    try:
                        result = await agent.chat(
                            session_id=session_id,
                            message=delegated_message,
                            user_id=user_id,
                        )
                    except Exception as e:
                        logger.error("Delegation to %s failed: %s", agent_id, e)
                        working_messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id or str(uuid.uuid4()),
                                "content": json.dumps({"error": f"委派失败: {e}"}),
                            }
                        )
                        continue

                    delegation_count += 1

                    status = result.get("status", "final_answer")
                    # 兼容 TravelAgent 返回 "completed"
                    if status == "completed":
                        status = "final_answer"
                    reply = result.get("reply", "")

                    if status == "need_input":
                        # 子智能体需要追问 → 设置委派上下文
                        self._delegation_contexts[session_id] = DelegationContext(
                            agent_id=agent_id,
                            status="active",
                            started_at=time.time(),
                            last_interaction=time.time(),
                            delegation_count=delegation_count,
                        )
                        yield {"type": "chunk", "data": reply}
                        missing_info = result.get("missing_info", [])
                        if missing_info:
                            yield {"type": "need_input", "data": missing_info}
                        yield {"type": "done", "data": "need_input"}
                        return

                    # final_answer: 将结果回传云合 LLM
                    working_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id or str(uuid.uuid4()),
                            "content": json.dumps({"agent": agent_id, "reply": reply[:4000]}, ensure_ascii=False),
                        }
                    )

                    # 流式输出子智能体回复
                    yield {"type": "chunk", "data": reply}

                elif tool_call.name == "list_available_agents":
                    agents_desc = self._get_all_descriptions(user_id)
                    working_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id or str(uuid.uuid4()),
                            "content": json.dumps({"agents": agents_desc}, ensure_ascii=False),
                        }
                    )

            # 继续循环，让云合 LLM 看到委派结果后做下一步决策
            if delegation_count >= self._MAX_DELEGATIONS:
                yield {"type": "chunk", "data": "\n\n（已达委派上限）"}
                break

        yield {"type": "done", "data": "final_answer"}

    # ===== 委派上下文：用户消息转发给当前委派智能体 =====

    async def _forward_to_delegated_agent(
        self,
        ctx: DelegationContext,
        session_id: str,
        message: str,
        user_id: str | None,
    ) -> AsyncGenerator[dict, None]:
        """将用户消息直接转发给当前委派的智能体（跳过 Tier 0/1）。"""
        agent = self._get_or_create_agent(ctx.agent_id, user_id)
        yield {"type": "route", "data": ctx.agent_id}

        try:
            result = await agent.chat(
                session_id=session_id,
                message=message,
                user_id=user_id,
            )
        except Exception as e:
            logger.error("Delegation forward to %s failed: %s", ctx.agent_id, e)
            del self._delegation_contexts[session_id]
            yield {"type": "chunk", "data": f"委派出错：{e}"}
            yield {"type": "done", "data": "final_answer"}
            return

        ctx.touch()
        status = result.get("status", "final_answer")
        if status == "completed":
            status = "final_answer"
        reply = result.get("reply", "")

        if status == "final_answer":
            # 任务完成 → 清除委派上下文
            ctx.status = "completed"
            del self._delegation_contexts[session_id]
            yield {"type": "chunk", "data": reply}
            yield {"type": "done", "data": "final_answer"}

        elif status == "need_input":
            # 需要用户补充信息 → 保持委派上下文
            yield {"type": "chunk", "data": reply}
            missing_info = result.get("missing_info", [])
            if missing_info:
                yield {"type": "need_input", "data": missing_info}
            yield {"type": "done", "data": "need_input"}

        elif status == "cannot_handle":
            # 智能体无法处理 → 释放委派，云合重新接手（回退到 Tier 1）
            del self._delegation_contexts[session_id]
            yield {"type": "chunk", "data": reply}
            async for event in self._yunhe_chat_stream(session_id, message, user_id):
                yield event

    def _is_delegation_expired(self, ctx: DelegationContext) -> bool:
        return time.time() - ctx.last_interaction > self._DELEGATION_TIMEOUT

    # ===== 主入口 =====

    async def chat(  # type: ignore[override]
        self,
        session_id: str,
        user_id: str | None,
        message: str,
        mode: SessionMode = "yunhe_default",
        locked_agent_id: str | None = None,
        *,
        agent_id: str | None = None,
        trace_id: str = "",
    ) -> dict:
        """mode-first 同步对话。

        返回值在既有 ``status`` / ``reply`` / ``active_agent`` / ``agent_actions``
        字段基础上，新增：

        - ``handled_by``：本轮实际处理消息的 Agent ID（云合直答时为 ``"yunhe"``）
        - ``next_controller``：下一轮控制权归属（默认模式委派后回到 ``"yunhe"``，
          锁定模式留在锁定 Agent）

        ``agent_id`` 仅作为管理员/调试显式覆盖；传入时绕过 mode 路由。

        注意：签名与 BaseAgent.chat 不一致（额外接受 mode/locked_agent_id 位置参数），
        因为 OrchestratorAgent 是顶层调度器，由 API 路由按 mode-first 语义直接调用，
        不参与 BaseAgent 的多态替换场景。
        """
        # admin/debug 显式覆盖
        if agent_id:
            agent = self._get_or_create_agent(agent_id, user_id)
            result = await agent.chat(
                session_id=session_id, message=message, user_id=user_id, trace_id=trace_id
            )
            return {
                **result,
                "handled_by": agent_id,
                "next_controller": agent_id,
            }

        # 非 yunhe 模式（legacy 兼容）：按消息路由到专业 Agent，控制权不回云合
        if not self._yunhe_mode:
            routed_id = await self._route(message, user_id)
            agent = self._get_or_create_agent(routed_id, user_id)
            result = await agent.chat(
                session_id=session_id, message=message, user_id=user_id, trace_id=trace_id
            )
            return {
                **result,
                "handled_by": routed_id,
                "next_controller": routed_id,
            }

        # yunhe 模式：mode-first 路由
        decision = await self._select_handler(mode, locked_agent_id, message, user_id)

        if decision.agent_id is None:
            # 云合直答
            reply = await self._yunhe_direct_reply(message, user_id)
            return {
                "status": "final_answer",
                "reply": reply,
                "active_agent": "yunhe",
                "agent_actions": [],
                "handled_by": "yunhe",
                "next_controller": "yunhe",
            }

        # 委派给专业 Agent
        agent = self._get_or_create_agent(decision.agent_id, user_id)
        result = await agent.chat(
            session_id=session_id, message=message, user_id=user_id, trace_id=trace_id
        )
        # 默认模式：单轮委派后控制权回到云合；锁定模式：控制权留在锁定 Agent
        next_controller = "yunhe" if mode == "yunhe_default" else decision.agent_id
        return {
            **result,
            "handled_by": decision.agent_id,
            "next_controller": next_controller,
        }

    async def chat_stream(  # type: ignore[override]
        self,
        session_id: str,
        user_id: str | None,
        message: str,
        mode: SessionMode = "yunhe_default",
        locked_agent_id: str | None = None,
        *,
        agent_id: str | None = None,
        trace_id: str = "",
    ) -> AsyncGenerator[dict, None]:
        """mode-first 流式对话；与 :py:meth:`chat` 保持一致的路由语义。"""
        # admin/debug 显式覆盖
        if agent_id:
            agent = self._get_or_create_agent(agent_id, user_id)
            async for event in agent.chat_stream(
                session_id=session_id, message=message, user_id=user_id, trace_id=trace_id
            ):
                yield event
            return

        # 非 yunhe 模式（legacy 兼容）
        if not self._yunhe_mode:
            routed_id = await self._route(message, user_id)
            agent = self._get_or_create_agent(routed_id, user_id)
            async for event in agent.chat_stream(
                session_id=session_id, message=message, user_id=user_id, trace_id=trace_id
            ):
                yield event
            return

        # yunhe 模式：活跃委派上下文优先转发（保持 need_input 追问体验）
        ctx = self._delegation_contexts.get(session_id)
        if ctx and ctx.is_active() and not self._is_delegation_expired(ctx):
            logger.info("Yunhe: forwarding to delegated agent %s", ctx.agent_id)
            async for event in self._forward_to_delegated_agent(
                ctx,
                session_id,
                message,
                user_id,
            ):
                yield event
            return

        if ctx:
            del self._delegation_contexts[session_id]

        # mode-first 路由决策
        decision = await self._select_handler(mode, locked_agent_id, message, user_id)

        if decision.agent_id is None:
            # 云合直答
            yield {"type": "route", "data": "yunhe"}
            async for event in self._direct_reply(
                session_id=session_id, message=message, user_id=user_id
            ):
                yield event
            return

        # 委派给专业 Agent
        yield {"type": "route", "data": decision.agent_id}
        agent = self._get_or_create_agent(decision.agent_id, user_id)
        async for event in agent.chat_stream(
            session_id=session_id, message=message, user_id=user_id, trace_id=trace_id
        ):
            yield event
        # 默认模式：单轮委派完成后控制权回到云合（通知前端可清空 activeAgent 锁定态）
        if mode == "yunhe_default":
            yield {"type": "control_returned", "data": "yunhe"}
