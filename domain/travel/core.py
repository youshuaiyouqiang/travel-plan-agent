from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

from config import settings
from infrastructure.mcp.runtime import MCPProxyRuntime
from infrastructure.tools.executor import ToolExecutor
from infrastructure.tools.registry import ToolRegistry
from domain.travel.context_manager import ContextManager
from infrastructure.llm.openai import OpenAILLM
from infrastructure.mcp.catalog import MCPCatalog
from domain.memory.manager import SessionMemory, DualLayerMemoryManager
from domain.memory.memory_extractor import MemoryExtractor
from domain.memory.memory_distiller import MemoryDistiller
from domain.travel.prompt_context import PromptContext
from domain.travel.prompting import PromptBuilder
from domain.reasoning.engine import AskUserNeeded, ReasoningEngine, ConfirmationNeeded
from domain.shared.runtime.facts import answer_date_or_time_query, current_datetime_text
from domain.user.session.manager import SessionManager
from domain.user.session.task_state import TaskStatus, TaskStateStore
from domain.shared.runtime.trace import RunTrace, TraceStore
from domain.shared.types import IntentType
from domain.travel.intent.travel_classifier import TravelIntentClassifier, TravelIntentResult
from domain.travel.intent.travel_schema import TravelIntentType
from domain.user.emotion.detector import EmotionDetector
from domain.user.emotion.schema import EmotionResult, EMOTION_STRATEGIES
from domain.user.profile.manager import ProfileManager
from domain.shared.audit.logger import AuditLogger
from domain.shared.metrics.collector import track_request

logger = logging.getLogger(__name__)


def _human_readable_reason(reason: str) -> str:
    mapping = {
        "user_requested": "需要人工旅行顾问协助",
        "emotion:angry": "检测到您不满意，为您转接专属顾问",
        "max_retries": "多次尝试未能满足您的需求",
        "sensitive_topic": "涉及签证等敏感问题，需要专业顾问处理",
    }
    return mapping.get(reason, reason)


class Agent:
    def __init__(
        self,
        *,
        llm: OpenAILLM,
        prompt_builder: PromptBuilder,
        session_store: SessionManager,
        tool_registry: ToolRegistry,
        tool_executor: ToolExecutor,
        mcp_catalog: MCPCatalog | None = None,
        mcp_runtime: MCPProxyRuntime | None = None,
        ops_classifier: TravelIntentClassifier | None = None,
        emotion_detector: EmotionDetector | None = None,
        profile_manager: ProfileManager | None = None,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        self._llm = llm
        self._prompt_builder = prompt_builder
        self._session_store = session_store
        self._tool_registry = tool_registry
        self._tool_executor = tool_executor
        self._memory = SessionMemory()
        self._dual_memory = DualLayerMemoryManager()
        self._memory_extractor = MemoryExtractor(llm)
        self._memory_distiller = MemoryDistiller(llm)
        self._context_manager = ContextManager()
        self._trace_store = TraceStore()
        self._task_store = TaskStateStore()
        self._mcp_catalog = mcp_catalog or MCPCatalog(settings.mcp_servers_dir)
        self._mcp_runtime = mcp_runtime
        self._reasoning = ReasoningEngine(
            llm=llm,
            tool_registry=tool_registry,
            tool_executor=tool_executor,
            audit_logger=audit_logger,
        )
        self._ops_classifier = ops_classifier
        self._emotion_detector = emotion_detector
        self._profile_manager = profile_manager or ProfileManager()
        self._audit_logger = audit_logger

    # ===== P1-6：chat 与 chat_stream 共用的上下文准备与收尾逻辑 =====

    @dataclass
    class ChatPreparation:
        """chat / chat_stream 共用的上下文准备结果。

        early_action 为 None 时表示进入 ReAct 推理主路径；
        否则调用方需根据 kind 自行处理（保存/trace/yield/return）后提前结束。
        """
        session: Any
        task: Any
        intent: Any
        ops_result: Any
        emotion_result: Any
        system: str
        tools: list[str]
        selected_mcp_tools: list
        connected_mcp_tools: list
        memory_context: str
        dual_memory_context: str
        mcp_context: str
        profile_context: str
        urgency_context: str
        prompt_context: Any
        early_action: tuple[str, Any] | None = field(default=None)
        conversation_history: list[dict[str, str]] = field(default_factory=list)

    async def _prepare_chat_context(
        self,
        *,
        session_id: str,
        user_id: str | None,
        message: str,
        memory_scope: str,
        trace_id: str,
    ) -> "Agent.ChatPreparation":
        """chat 与 chat_stream 共用的上下文准备逻辑。

        流程：设置审计上下文 → 加载 session/task → 追加用户消息 → 检查直答/紧急/快速回复/行程确认
        → 构建工具与记忆上下文 → 生成 system prompt → 写入审计日志。
        命中早退路径时设置 early_action 由调用方处理。
        """
        self._llm.set_audit_context(session_id=session_id, user_id=memory_scope, trace_id=trace_id)
        self._reasoning.set_audit_context(session_id=session_id, user_id=memory_scope, trace_id=trace_id)
        self._tool_executor.set_audit_context(session_id=session_id, user_id=memory_scope, trace_id=trace_id)
        session = self._session_store.get(session_id)
        task = self._task_store.get(session_id, user_id=memory_scope)
        session.append("user", message)

        # 直答：运行时事实（日期/时间）
        direct_runtime_answer = answer_date_or_time_query(message)
        if direct_runtime_answer:
            return self.ChatPreparation(
                session=session, task=task, intent=None, ops_result=None,
                emotion_result=None, system="", tools=[], selected_mcp_tools=[],
                connected_mcp_tools=[], memory_context="", dual_memory_context="",
                mcp_context="", profile_context="", urgency_context="",
                prompt_context=None,
                early_action=("direct_runtime_answer", direct_runtime_answer),
            )

        # 意图识别
        ops_result: TravelIntentResult | None = None
        if self._ops_classifier:
            # 构建对话历史（不含当前消息），用于 missing_info 上下文检查
            history_turns = session.turns[:-1] if len(session.turns) > 1 else []
            conversation_history = [{"role": t.role, "content": t.content} for t in history_turns] if history_turns else None

            ops_result = await self._ops_classifier.classify(
                message, conversation_history=conversation_history
            )
            # ★ TRIP_PLANNING 等需要信息完整性的意图：优先用 LLM 检查 missing_info，
            # regex 仅作 LLM 不可用时的 fallback。
            if ops_result and conversation_history:
                _LLM_FIRST_INTENTS = {
                    TravelIntentType.TRIP_PLANNING,
                    TravelIntentType.FLIGHT_SEARCH,
                    TravelIntentType.HOTEL_SEARCH,
                }
                if ops_result.intent in _LLM_FIRST_INTENTS:
                    try:
                        context_missing = await self._ops_classifier.check_missing_info_with_context(
                            message=message,
                            intent=ops_result.intent,
                            conversation_history=conversation_history,
                        )
                        ops_result.missing_info = context_missing
                    except Exception as e:
                        logger.warning("LLM missing_info check failed, using regex result: %s", e)
                elif ops_result.missing_info:
                    # 非关键意图：regex 有缺失时才用 LLM 纠正
                    try:
                        context_missing = await self._ops_classifier.check_missing_info_with_context(
                            message=message,
                            intent=ops_result.intent,
                            conversation_history=conversation_history,
                        )
                        ops_result.missing_info = context_missing
                    except Exception as e:
                        logger.warning("Failed to re-check missing_info with context: %s", e)
            intent = self._ops_classifier.to_intent_result(ops_result)
            if self._audit_logger:
                self._audit_logger.log_intent_classify(
                    session_id=session_id, user_id=memory_scope, trace_id=trace_id,
                    message=message, intent=ops_result.intent.value, goal=intent.goal,
                    confidence=ops_result.confidence, classifier="travel_classifier",
                    raw_llm_output=getattr(ops_result, "raw_output", ""),
                )
        else:
            from domain.shared.types import IntentResult
            intent = IntentResult(
                intent=IntentType.TASK, goal=message[:100],
                fast_reply=False, force_tool=True, tool_hints=[],
            )
        logger.info(
            "Intent resolved: intent=%s fast_reply=%s force_tool=%s travel_intent=%s",
            intent.intent.value, intent.fast_reply, intent.force_tool,
            ops_result.intent.value if ops_result else "none",
        )

        # 情绪检测
        emotion_result: EmotionResult | None = None
        if self._emotion_detector:
            emotion_result = await self._emotion_detector.detect(message)
            if self._audit_logger:
                self._audit_logger.log_emotion_detect(
                    session_id=session_id, user_id=memory_scope, trace_id=trace_id,
                    message=message, emotion=emotion_result.emotion.value,
                    score=emotion_result.score, confidence=emotion_result.confidence,
                    response_style=emotion_result.response_style,
                    raw_llm_output=getattr(emotion_result, "raw_output", ""),
                )

        # 紧急关键词
        emergency_reply = self._check_emergency_keywords(message)
        if emergency_reply:
            return self.ChatPreparation(
                session=session, task=task, intent=intent, ops_result=ops_result,
                emotion_result=emotion_result, system="", tools=[], selected_mcp_tools=[],
                connected_mcp_tools=[], memory_context="", dual_memory_context="",
                mcp_context="", profile_context="", urgency_context="",
                prompt_context=None,
                early_action=("emergency_reply", emergency_reply),
            )

        task.mark_in_progress(goal=intent.goal, latest_user_message=message)
        self._handle_cache_invalidation(task, message, ops_result)
        self._task_store.save(task)
        logger.info(
            "Intent analyzed: session_id=%s user_id=%s intent=%s emotion=%s force_tool=%s",
            session_id, memory_scope,
            ops_result.intent.value if ops_result else intent.intent.value,
            emotion_result.emotion.value if emotion_result else "none",
            intent.force_tool,
        )

        # 快速回复路径
        if intent.fast_reply and intent.intent in {IntentType.CHAT, IntentType.QUERY}:
            logger.warning("FAST_REPLY path triggered! intent=%s fast_reply=%s", intent.intent.value, intent.fast_reply)
            system = self._prompt_builder.build_fast_reply_system(intent)
            return self.ChatPreparation(
                session=session, task=task, intent=intent, ops_result=ops_result,
                emotion_result=emotion_result, system=system, tools=[], selected_mcp_tools=[],
                connected_mcp_tools=[], memory_context="", dual_memory_context="",
                mcp_context="", profile_context="", urgency_context="",
                prompt_context=None,
                early_action=("fast_reply", system),
            )

        # 行程确认路径
        from domain.travel.intent.travel_schema import TravelIntentType
        if ops_result and ops_result.intent == TravelIntentType.ITINERARY_CONFIRM:
            logger.info("itinerary_confirm: bypassing LLM, directly calling generate_itinerary_overview")
            return self.ChatPreparation(
                session=session, task=task, intent=intent, ops_result=ops_result,
                emotion_result=emotion_result, system="", tools=[], selected_mcp_tools=[],
                connected_mcp_tools=[], memory_context="", dual_memory_context="",
                mcp_context="", profile_context="", urgency_context="",
                prompt_context=None,
                early_action=("itinerary_confirm", ops_result),
            )

        # 缺失信息澄清路径：TRIP_PLANNING 且存在 missing_info 时，先追问再进入 ReAct
        if ops_result and ops_result.intent == TravelIntentType.TRIP_PLANNING and ops_result.missing_info:
            logger.info(
                "trip_planning with missing_info: %s, generating clarification before ReAct",
                ops_result.missing_info,
            )
            clarification_question = self._build_clarification_question(ops_result)
            return self.ChatPreparation(
                session=session, task=task, intent=intent, ops_result=ops_result,
                emotion_result=emotion_result, system="", tools=[], selected_mcp_tools=[],
                connected_mcp_tools=[], memory_context="", dual_memory_context="",
                mcp_context="", profile_context="", urgency_context="",
                prompt_context=None,
                early_action=("need_input", clarification_question),
            )

        # 构建 ReAct 上下文
        base_tools = self._tool_registry.list_names(intent.tool_hints, exclude_categories=["MCP"])
        context = self._context_manager.prepare(session, current_message=message)
        memory_context = ""
        dual_memory_context = ""
        if user_id:
            dual_memory_context = self._dual_memory.build_full_context(user_id, query=message)
        selected_mcp_tools = self._mcp_catalog.select_tool_refs(message, limit=4)
        connected_mcp_tools = [
            ref
            for ref in selected_mcp_tools
            if self._mcp_runtime and self._mcp_runtime.adapter_available(ref.proxy_name)
        ]
        tools = list(dict.fromkeys(base_tools + [ref.proxy_name for ref in connected_mcp_tools]))
        mcp_context = self._mcp_catalog.build_prompt_block(tool_refs=connected_mcp_tools)

        urgency_context = ""
        if emotion_result and emotion_result.response_style != "neutral":
            strategy = EMOTION_STRATEGIES.get(emotion_result.emotion, {})
            urgency_context = strategy.get("system_prompt_suffix", "")

        if self._profile_manager and user_id:
            self._profile_manager.update(
                memory_scope,
                intent=intent.intent.value,
                emotion=emotion_result.emotion.value if emotion_result else None,
                category=ops_result.rag_keywords[0] if ops_result and ops_result.rag_keywords else None,
            )
        profile_context = self._profile_manager.build_context(memory_scope) if self._profile_manager else ""

        logger.info(
            "Agent reasoning path: session_id=%s user_id=%s tools=%s memory=%s mcp=%s emotion=%s",
            session_id, memory_scope, ",".join(tools), bool(memory_context),
            ",".join(ref.proxy_name for ref in connected_mcp_tools),
            emotion_result.emotion.value if emotion_result else "none",
        )
        cached_tool_context = self._build_cached_tool_context(task)
        missing_info_context = self._build_missing_info_context(ops_result, dual_memory_context, user_id)
        itinerary_confirm_context = self._build_itinerary_confirm_context(
            ops_result, session, user_id=memory_scope, session_id=session_id
        )
        prompt_context = PromptContext(
            prepared_context=context,
            intent=intent,
            tools=tools,
            travel_intent=ops_result.intent.value if ops_result else "",
            memory_context=memory_context,
            mcp_context=mcp_context,
            emotion_context=urgency_context,
            profile_context=profile_context,
            cached_tool_context=cached_tool_context,
            dual_memory_context=dual_memory_context,
            missing_info_context=missing_info_context,
            itinerary_confirm_context=itinerary_confirm_context,
        )
        system = self._prompt_builder.build_react_system(prompt_context)
        if ops_result and ops_result.intent == TravelIntentType.ITINERARY_CONFIRM and not itinerary_confirm_context:
            logger.warning("itinerary_confirm: confirm context is EMPTY despite ITINERARY_CONFIRM intent")
        if self._audit_logger:
            self._audit_logger.log_context_built(
                session_id=session_id, user_id=memory_scope, trace_id=trace_id,
                system_prompt=system, tools=tools, memory_context=memory_context,
                dual_memory_context=dual_memory_context, mcp_context=mcp_context,
                profile_context=profile_context, emotion_context=urgency_context,
                selected_mcp_tools=[ref.proxy_name for ref in selected_mcp_tools],
                connected_mcp_tools=[ref.proxy_name for ref in connected_mcp_tools],
            )

        # 构建对话历史供 ReAct 引擎使用
        conversation_history = [
            {"role": t.role, "content": t.content}
            for t in session.turns[:-1]  # 排除当前用户消息
            if t.role in ("user", "assistant") and t.content
        ]

        return self.ChatPreparation(
            session=session, task=task, intent=intent, ops_result=ops_result,
            emotion_result=emotion_result, system=system, tools=tools,
            selected_mcp_tools=selected_mcp_tools, connected_mcp_tools=connected_mcp_tools,
            memory_context=memory_context, dual_memory_context=dual_memory_context,
            mcp_context=mcp_context, profile_context=profile_context,
            urgency_context=urgency_context, prompt_context=prompt_context,
            early_action=None, conversation_history=conversation_history,
        )

    async def _finalize_chat(
        self,
        *,
        session_id: str,
        user_id: str | None,
        memory_scope: str,
        trace_id: str,
        start_time: float,
        message: str,
        prep: "Agent.ChatPreparation",
        reply: str,
        status: str,
        events: list[dict],
    ) -> None:
        """chat 与 chat_stream 共用的收尾逻辑：保存 session/task/trace/audit/memory。

        reasoning 调用（run / run_stream）与 chunk 流式输出由调用方自行处理，
        本方法仅负责后置的持久化、trace、审计与记忆蒸馏。
        """
        session = prep.session
        task = prep.task
        intent = prep.intent
        emotion_result = prep.emotion_result
        session.append("assistant", reply)
        self._memory.refresh_summary(session)
        self._session_store.save(session, user_id=memory_scope)
        if status == "completed":
            task.mark_finished(status=TaskStatus.COMPLETED, reply=reply)
        self._cache_tool_results_from_trace(task)
        task.trace_summary = self._summarize_trace()
        self._task_store.save(task)
        self._trace_store.put(
            RunTrace(
                session_id=session_id,
                user_id=memory_scope,
                user_message=message,
                reply=reply,
                intent=intent.intent.value,
                goal=intent.goal,
                tools=prep.tools,
                memory_context=prep.memory_context,
                trace_steps=list(self._reasoning.last_trace),
                events=events,
            )
        )
        logger.info("Agent reasoning complete: session_id=%s user_id=%s", session_id, memory_scope)
        if self._audit_logger:
            self._audit_logger.log_session_complete(
                session_id=session_id,
                user_id=memory_scope,
                trace_id=trace_id,
                user_message=message,
                reply=reply,
                intent=intent.intent.value,
                emotion=emotion_result.emotion.value if emotion_result else "none",
                total_duration_ms=int((time.monotonic() - start_time) * 1000),
                trace_summary=self._summarize_trace(),
            )
        await self._post_chat_memory_processing(session, session_id, memory_scope, user_id)

    async def chat(
        self,
        *,
        session_id: str,
        message: str,
        user_id: str | None = None,
        trace_id: str = "",
    ) -> dict[str, str]:
        memory_scope = str(user_id or session_id)
        trace_id = trace_id or uuid.uuid4().hex[:16]
        start_time = time.monotonic()
        logger.info("Agent chat start: session_id=%s user_id=%s trace_id=%s message=%s", session_id, user_id or session_id, trace_id, message[:100])

        prep = await self._prepare_chat_context(
            session_id=session_id, user_id=user_id, message=message,
            memory_scope=memory_scope, trace_id=trace_id,
        )
        session = prep.session
        task = prep.task

        # 处理早退动作（直答/紧急/快速回复/行程确认）
        if prep.early_action:
            kind, payload = prep.early_action
            if kind == "direct_runtime_answer":
                reply = payload
                session.append("assistant", reply)
                self._memory.refresh_summary(session)
                self._session_store.save(session, user_id=memory_scope)
                task.mark_finished(status=TaskStatus.COMPLETED, reply=reply)
                task.trace_summary = "Answered directly from runtime facts."
                self._task_store.save(task)
                self._trace_store.put(
                    RunTrace(
                        session_id=session_id, user_id=memory_scope,
                        user_message=message, reply=reply,
                        intent="runtime_fact", goal="answer date/time from runtime facts",
                        tools=[], trace_steps=[],
                        events=[{"kind": "runtime_fact", "message": "Answered from runtime clock"}],
                    )
                )
                return {"status": "completed", "reply": reply}

            if kind == "emergency_reply":
                reply = payload
                session.append("assistant", reply)
                self._memory.refresh_summary(session)
                self._session_store.save(session, user_id=memory_scope)
                return {"status": "completed", "reply": reply}

            if kind == "fast_reply":
                system = payload
                reply = await self._llm.complete(
                    system=system,
                    messages=[{"role": "user", "content": message}],
                )
                session.append("assistant", reply)
                self._memory.refresh_summary(session)
                task.mark_finished(status=TaskStatus.COMPLETED, reply=reply)
                task.trace_summary = "Fast reply path without tools."
                self._task_store.save(task)
                self._trace_store.put(
                    RunTrace(
                        session_id=session_id, user_id=memory_scope,
                        user_message=message, reply=reply,
                        intent=prep.intent.intent.value, goal=prep.intent.goal,
                        tools=[], memory_context="", trace_steps=[],
                        events=[{"kind": "fast_reply", "message": "Handled without tools"}],
                    )
                )
                logger.info("Agent fast reply complete: session_id=%s", session_id)
                self._session_store.save(session, user_id=memory_scope)
                return {"status": "completed", "reply": reply}

            if kind == "itinerary_confirm":
                ops_result = payload
                logger.info("itinerary_confirm: bypassing LLM, directly calling generate_itinerary_overview")
                reply, itinerary_id = await self._direct_generate_itinerary(
                    session=session, session_id=session_id,
                    user_id=memory_scope, ops_result=ops_result,
                )
                # P1-13：结构化保存 itinerary_id，供 TravelAgent 通过 actions 事件下发
                if itinerary_id:
                    task.metadata["last_itinerary_id"] = itinerary_id
                session.append("assistant", reply)
                self._memory.refresh_summary(session)
                self._session_store.save(session, user_id=memory_scope)
                task.mark_finished(status=TaskStatus.COMPLETED, reply=reply)
                task.trace_summary = "Direct itinerary generation (bypassed LLM reasoning)."
                self._task_store.save(task)
                self._trace_store.put(
                    RunTrace(
                        session_id=session_id, user_id=memory_scope,
                        user_message=message, reply=reply,
                        intent=prep.intent.intent.value, goal=prep.intent.goal,
                        tools=["generate_itinerary_overview"], memory_context="",
                        trace_steps=[],
                        events=[{"kind": "direct_tool_call", "message": "generate_itinerary_overview called directly"}],
                    )
                )
                logger.info("Agent itinerary confirm complete: session_id=%s", session_id)
                await self._post_chat_memory_processing(session, session_id, memory_scope, user_id)
                result = {"status": "completed", "reply": reply}
                if itinerary_id:
                    result["itinerary_id"] = itinerary_id
                return result

            if kind == "need_input":
                reply = payload
                session.append("assistant", reply)
                self._memory.refresh_summary(session)
                self._session_store.save(session, user_id=memory_scope)
                task.mark_waiting(
                    status=TaskStatus.NEEDS_USER_INPUT,
                    prompt=reply,
                    reply=reply,
                )
                logger.info("Agent need_input (early): session_id=%s question=%s", session_id, reply[:100])
                return {"status": "needs_user_input", "reply": reply}

        # ReAct 推理主路径
        status = "completed"
        try:
            reply = await self._reasoning.run(
                system_prompt=prep.system,
                user_message=message,
                force_tool=prep.intent.force_tool,
                conversation_history=prep.conversation_history,
            )
        except AskUserNeeded as exc:
            reply = exc.question
            status = "needs_user_input"
            task.mark_waiting(
                status=TaskStatus.NEEDS_USER_INPUT,
                prompt=exc.question,
                reply=reply,
            )
        except ConfirmationNeeded as exc:
            reply = exc.prompt
            status = "needs_confirmation"
            task.mark_waiting(
                status=TaskStatus.NEEDS_CONFIRMATION,
                prompt=exc.prompt,
                reply=reply,
            )

        events = [
            {"kind": "context", "message": "Prepared context", "payload": {"trimmed": prep.prompt_context.prepared_context.was_trimmed}},
            {
                "kind": "memory",
                "message": "Built memory context",
                "payload": {"has_memory": bool(prep.memory_context), "scope_id": memory_scope},
            },
            {
                "kind": "mcp",
                "message": "Built MCP context",
                "payload": {
                    "has_mcp": bool(prep.mcp_context),
                    "selected_tools": [ref.proxy_name for ref in prep.selected_mcp_tools],
                    "connected_tools": [ref.proxy_name for ref in prep.connected_mcp_tools],
                },
            },
            {"kind": "result", "message": "Agent run finished", "payload": {"status": status}},
        ]
        await self._finalize_chat(
            session_id=session_id, user_id=user_id, memory_scope=memory_scope,
            trace_id=trace_id, start_time=start_time, message=message,
            prep=prep, reply=reply, status=status, events=events,
        )
        return {"status": status, "reply": reply, "trace_id": trace_id}

    async def chat_stream(
        self,
        *,
        session_id: str,
        message: str,
        user_id: str | None = None,
        trace_id: str = "",
    ) -> AsyncGenerator[dict[str, str], None]:
        """流式聊天：工具调用阶段同步执行，最终回复阶段逐 token 流式输出。

        yield 的 dict 格式：
          {"type": "status", "data": "thinking"}       — 正在思考/工具调用中
          {"type": "tool_status", "data": "状态文本"}   — 工具执行状态（搜索机票、搜索酒店等）
          {"type": "chunk", "data": "文本片段"}          — 流式文本片段
          {"type": "done", "data": "completed"}         — 流式结束
          {"type": "error", "data": "错误信息"}          — 出错
        """
        memory_scope = str(user_id or session_id)
        trace_id = trace_id or uuid.uuid4().hex[:16]
        start_time = time.monotonic()
        logger.info("Agent chat_stream start: session_id=%s user_id=%s trace_id=%s", session_id, user_id or session_id, trace_id)

        prep = await self._prepare_chat_context(
            session_id=session_id, user_id=user_id, message=message,
            memory_scope=memory_scope, trace_id=trace_id,
        )
        session = prep.session
        task = prep.task

        # 处理早退动作（直答/紧急/快速回复/行程确认）
        if prep.early_action:
            kind, payload = prep.early_action
            if kind == "direct_runtime_answer":
                reply = payload
                session.append("assistant", reply)
                self._memory.refresh_summary(session)
                self._session_store.save(session, user_id=memory_scope)
                task.mark_finished(status=TaskStatus.COMPLETED, reply=reply)
                self._task_store.save(task)
                yield {"type": "chunk", "data": reply}
                yield {"type": "done", "data": "completed"}
                return

            if kind == "emergency_reply":
                reply = payload
                session.append("assistant", reply)
                self._memory.refresh_summary(session)
                self._session_store.save(session, user_id=memory_scope)
                yield {"type": "chunk", "data": reply}
                yield {"type": "done", "data": "completed"}
                return

            # fast_reply / itinerary_confirm / 主推理路径都需要先发 thinking 状态
            yield {"type": "status", "data": "thinking"}

            if kind == "fast_reply":
                system = payload
                reply = ""
                async for chunk in self._llm.stream_complete(system=system, messages=[{"role": "user", "content": message}]):
                    reply += chunk
                    yield {"type": "chunk", "data": chunk}
                session.append("assistant", reply)
                self._memory.refresh_summary(session)
                task.mark_finished(status=TaskStatus.COMPLETED, reply=reply)
                self._task_store.save(task)
                self._session_store.save(session, user_id=memory_scope)
                yield {"type": "done", "data": "completed"}
                return

            if kind == "itinerary_confirm":
                ops_result = payload
                reply, itinerary_id = await self._direct_generate_itinerary(
                    session=session, session_id=session_id, user_id=memory_scope, ops_result=ops_result,
                )
                # P1-13：结构化保存 itinerary_id，供 TravelAgent 通过 actions 事件下发
                if itinerary_id:
                    task.metadata["last_itinerary_id"] = itinerary_id
                session.append("assistant", reply)
                self._memory.refresh_summary(session)
                self._session_store.save(session, user_id=memory_scope)
                task.mark_finished(status=TaskStatus.COMPLETED, reply=reply)
                self._task_store.save(task)
                await self._post_chat_memory_processing(session, session_id, memory_scope, user_id)
                yield {"type": "chunk", "data": reply}
                # done event 携带结构化 itinerary_id（如果有），供 TravelAgent 读取
                done_data = {"status": "completed", "itinerary_id": itinerary_id} if itinerary_id else "completed"
                yield {"type": "done", "data": done_data}
                return

            if kind == "need_input":
                reply = payload
                session.append("assistant", reply)
                self._memory.refresh_summary(session)
                self._session_store.save(session, user_id=memory_scope)
                task.mark_waiting(
                    status=TaskStatus.NEEDS_USER_INPUT,
                    prompt=reply,
                    reply=reply,
                )
                logger.info("Agent need_input (early stream): session_id=%s question=%s", session_id, reply[:100])
                yield {"type": "chunk", "data": reply}
                yield {"type": "done", "data": "needs_user_input"}
                return

        else:
            # 主推理路径也需要 thinking 状态
            yield {"type": "status", "data": "thinking"}

        # ReAct 推理主路径（流式）
        status = "completed"
        full_reply = ""
        try:
            async for chunk in self._reasoning.run_stream(
                system_prompt=prep.system,
                user_message=message,
                force_tool=prep.intent.force_tool,
                conversation_history=prep.conversation_history,
            ):
                if chunk.startswith("__status__:"):
                    # 状态通知，转为 tool_status 事件，不写入回复文本
                    yield {"type": "tool_status", "data": chunk[len("__status__:"):]}
                else:
                    full_reply += chunk
                    yield {"type": "chunk", "data": chunk}
        except AskUserNeeded as exc:
            full_reply = exc.question
            status = "needs_user_input"
            task.mark_waiting(status=TaskStatus.NEEDS_USER_INPUT, prompt=exc.question, reply=full_reply)
            yield {"type": "chunk", "data": full_reply}
        except ConfirmationNeeded as exc:
            full_reply = exc.prompt
            status = "needs_confirmation"
            task.mark_waiting(status=TaskStatus.NEEDS_CONFIRMATION, prompt=exc.prompt, reply=full_reply)
            yield {"type": "chunk", "data": full_reply}

        events = [
            {"kind": "stream_result", "message": "Stream run finished", "payload": {"status": status}},
        ]
        await self._finalize_chat(
            session_id=session_id, user_id=user_id, memory_scope=memory_scope,
            trace_id=trace_id, start_time=start_time, message=message,
            prep=prep, reply=full_reply, status=status, events=events,
        )
        yield {"type": "done", "data": status, "trace_id": trace_id}

    def latest_trace(self, session_id: str) -> dict | None:
        trace = self._trace_store.latest(session_id)
        return trace.to_dict() if trace else None

    def snapshot_session(self, session_id: str) -> dict | None:
        return self._session_store.snapshot(session_id)

    def snapshot_task(self, session_id: str, *, user_id: str | None = None) -> dict:
        effective_user_id = str(user_id or session_id)
        return self._task_store.snapshot(session_id, user_id=effective_user_id)

    def _summarize_trace(self) -> str:
        if not self._reasoning.last_trace:
            return ""
        parts: list[str] = []
        for step in self._reasoning.last_trace[-3:]:
            summary = f"iter={step.iteration} type={step.decision_type}"
            if step.tool_calls:
                summary += " tools=" + ",".join(call["name"] for call in step.tool_calls)
            if step.system_note:
                summary += f" note={step.system_note}"
            parts.append(summary)
        return " | ".join(parts)

    @staticmethod
    def _check_emergency_keywords(message: str) -> str | None:
        lowered = message.lower()
        emergency_keywords = ["丢失", "被盗", "护照", "受伤", "事故", "报警", "急救", "大使馆", "领事馆"]
        if not any(kw in lowered for kw in emergency_keywords):
            return None
        return (
            "⚠️ 紧急情况！以下信息可能对您有帮助：\n\n"
            "📞 紧急电话：\n"
            "• 中国领事保护热线：+86-10-12308\n"
            "• 国际急救：112（欧盟）/ 911（美国）/ 110（日本）\n"
            "• 报警：当地报警电话\n\n"
            "🏛️ 如果护照丢失：\n"
            "1. 立即向当地警方报案，获取报案证明\n"
            "2. 联系中国驻当地使领馆办理旅行证\n"
            "3. 使领馆信息可通过外交部官网查询\n\n"
            "请保护好自身安全，如需更多帮助请继续告诉我。"
        )

    async def _post_chat_memory_processing(
        self,
        session: Any,
        session_id: str,
        memory_scope: str,
        user_id: str | None,
    ) -> None:
        from config import settings as cfg
        if not cfg.memory_extraction_enabled:
            return
        if not user_id:
            return

        try:
            conv_id = self._dual_memory.save_conversation(
                session_id=session_id,
                user_id=user_id,
                summary=session.summary[:200] if session.summary else "",
            )

            turns_data = [{"role": t.role, "content": t.content} for t in session.turns]
            extracted = await self._memory_extractor.extract(
                turns_data,
                user_id=user_id,
                session_id=session_id,
            )

            if extracted:
                saved_ids = self._memory_extractor.save_extracted(
                    extracted,
                    user_id=user_id,
                    conversation_id=conv_id,
                )
                for mid in saved_ids:
                    self._dual_memory.record_extraction(
                        conversation_id=conv_id,
                        memory_type="short_term",
                        memory_id=mid,
                    )

            ltm_list = self._dual_memory.get_long_term_memories(user_id)
            for ltm in ltm_list:
                self._dual_memory.record_extraction(
                    conversation_id=conv_id,
                    memory_type="long_term",
                    memory_id=ltm.id,
                    relevance=0.5,
                )

            # P1-3：在独立线程中调用 sync distiller 方法，避免阻塞事件循环，
            # 同时让 _compress_content 内部的 asyncio.run() 能正常工作（线程内无运行中的 loop）
            distilled = await asyncio.to_thread(
                self._memory_distiller.run_distillation, user_id
            )
            if distilled > 0:
                logger.info("Memory distilled: user=%s count=%d", user_id, distilled)

            await asyncio.to_thread(self._memory_distiller.run_decay, user_id)

        except Exception:
            logger.warning("Post-chat memory processing failed", exc_info=True)

    def list_mcp_servers(self) -> list[dict]:
        return [
            {
                "identifier": server.identifier,
                "name": server.name,
                "description": server.description,
                "instructions": server.instructions,
                "tools": [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "input_schema": tool.input_schema,
                        "proxy_name": tool.proxy_name,
                        "adapter_available": bool(
                            self._mcp_runtime and self._mcp_runtime.adapter_available(tool.proxy_name)
                        ),
                    }
                    for tool in server.tools
                ],
            }
            for server in self._mcp_catalog.list_servers()
        ]

    def select_mcp_tools(self, query: str, limit: int = 4) -> list[dict]:
        return [
            {
                "server_identifier": ref.server_identifier,
                "server_name": ref.server_name,
                "tool_name": ref.tool_name,
                "proxy_name": ref.proxy_name,
                "description": ref.description,
                "adapter_available": bool(
                    self._mcp_runtime and self._mcp_runtime.adapter_available(ref.proxy_name)
                ),
            }
            for ref in self._mcp_catalog.select_tool_refs(query, limit=limit)
        ]

    _CATEGORY_LABELS = {
        "flight": "机票",
        "train": "高铁/火车",
        "hotel": "酒店",
        "poi": "景点",
        "weather": "天气",
        "route": "路线",
        "keyword_search": "关键词搜索",
    }

    _FIELD_LABELS = {
        "destination": "目的地",
        "origin": "出发地",
        "duration": "旅行天数",
        "dates": "出发日期",
        "budget": "预算",
    }

    async def _direct_generate_itinerary(
        self,
        session: Any,
        session_id: str,
        user_id: str,
        ops_result: Any,
    ) -> tuple[str, str]:
        """直通生成行程概览，绕过 LLM 推理。

        返回 (reply, itinerary_id)：
          - reply：要追加到 session 的回复文本
          - itinerary_id：结构化的行程 ID（生成失败时为空字符串），
            供上层 TravelAgent 通过 actions 事件结构化下发，避免前端
            从自由文本正则提取（P1-13）。
        """
        from domain.travel.tools.travel_tools import _generate_itinerary_overview

        itinerary_content = ""
        itinerary_markers = ["第1天", "第一天", "Day 1", "day1", "行程安排", "每日行程", "天：", "日游"]
        confirmation_markers = ["您对这个行程满意吗", "满意的话我将为您生成", "不满意可以告诉我", "是否满意"]
        for turn in reversed(session.turns):
            if turn.role == "assistant" and len(turn.content) > 50:
                is_confirmation_only = any(m in turn.content for m in confirmation_markers)
                if is_confirmation_only and not any(m in turn.content for m in itinerary_markers):
                    continue
                if any(marker in turn.content for marker in itinerary_markers):
                    itinerary_content = turn.content
                    break
                if not itinerary_content:
                    itinerary_content = turn.content

        if not itinerary_content:
            logger.warning("itinerary_confirm: no itinerary content found in session history")
            return "抱歉，未能找到行程内容，请重新描述您的行程需求。"

        logger.info("itinerary_confirm: found itinerary content, length=%d", len(itinerary_content))

        destination = ""
        if ops_result and hasattr(ops_result, "detected_destination") and ops_result.detected_destination:
            destination = ops_result.detected_destination
        if not destination:
            dest_markers = ["去", "到", "前往", "飞", "游"]
            for turn in reversed(session.turns):
                if turn.role == "user":
                    for marker in dest_markers:
                        idx = turn.content.find(marker)
                        if idx >= 0:
                            fragment = turn.content[idx + len(marker):idx + len(marker) + 10].strip()
                            for city in ["北京", "上海", "广州", "深圳", "成都", "重庆", "杭州", "西安", "厦门", "青岛", "三亚", "丽江", "大理", "长沙", "武汉", "南京", "苏州", "昆明", "桂林", "黄山"]:
                                if city in fragment:
                                    destination = city
                                    break
                            if destination:
                                break
                    if destination:
                        break

        title = f"{destination}行程" if destination else "旅行行程"

        arguments = {
            "title": title,
            "content": itinerary_content,
            "session_id": session_id,
            "destination": destination,
            "user_id": user_id,
        }

        logger.info("itinerary_confirm: calling generate_itinerary_overview with args=%s", arguments)

        try:
            result = await _generate_itinerary_overview(arguments)
        except Exception as e:
            logger.error("itinerary_confirm: generate_itinerary_overview failed: %s", e, exc_info=True)
            return "抱歉，行程概览生成失败，请稍后重试。", ""

        if result.get("is_error"):
            logger.error("itinerary_confirm: tool returned error: %s", result.get("content"))
            return "抱歉，行程概览生成失败，请稍后重试。", ""

        try:
            data = json.loads(result.get("content", "{}"))
            itinerary_id = data.get("itinerary_id", "")
        except (json.JSONDecodeError, ValueError):
            itinerary_id = ""

        if itinerary_id:
            return (
                f"正在为您生成专属行程概览卡片，请稍候...\n\n"
                f"行程概览已生成！itinerary_id: {itinerary_id}\n"
                f"点击下方卡片即可查看完整行程",
                itinerary_id,
            )
        else:
            return "行程概览已生成！点击侧边栏「我的行程」即可查看。", ""

    def _build_itinerary_confirm_context(
        self,
        ops_result: Any,
        session: Any,
        user_id: str = "",
        session_id: str = "",

    ) -> str:
        if not ops_result or not hasattr(ops_result, "intent"):
            logger.debug("itinerary_confirm: no ops_result or no intent attr")
            return ""
        from domain.travel.intent.travel_schema import TravelIntentType
        if ops_result.intent != TravelIntentType.ITINERARY_CONFIRM:
            logger.debug("itinerary_confirm: intent=%s, not ITINERARY_CONFIRM", ops_result.intent)
            return ""

        logger.info(
            "itinerary_confirm: detected confirm intent, session has %d turns",
            len(session.turns),
        )

        itinerary_content = ""
        itinerary_markers = ["第1天", "第一天", "Day 1", "day1", "行程安排", "每日行程", "天：", "日游"]
        confirmation_markers = ["您对这个行程满意吗", "满意的话我将为您生成", "不满意可以告诉我", "是否满意"]
        for turn in reversed(session.turns):
            if turn.role == "assistant" and len(turn.content) > 50:
                is_confirmation_only = any(m in turn.content for m in confirmation_markers)
                if is_confirmation_only and not any(m in turn.content for m in itinerary_markers):
                    continue
                if any(marker in turn.content for marker in itinerary_markers):
                    itinerary_content = turn.content
                    break
                if not itinerary_content:
                    itinerary_content = turn.content

        if not itinerary_content:
            logger.warning("itinerary_confirm: no itinerary content found in session history")
            return ""

        logger.info("itinerary_confirm: found itinerary content, length=%d", len(itinerary_content))

        user_id_hint = f"\n- user_id: {user_id}" if user_id else ""
        session_id_hint = f"\n- session_id: {session_id}" if session_id else ""

        return (
            "⚠️ 【行程确认指令】用户已确认满意当前行程方案！\n"
            "你必须立即调用 generate_itinerary_overview 工具来生成行程概览卡片。\n"
            "调用参数（注意：不要传content参数，系统会自动获取行程内容）：\n"
            "- title: 行程标题（如：厦门3日游）\n"
            f"- session_id: {session_id or '当前会话ID'}\n"
            f"- destination: 目的地城市{user_id_hint}\n\n"
            "调用后，将返回的 itinerary_id 告知用户，格式为：itinerary_id: xxxxxxxxxx"
        )

    def _build_missing_info_context(
        self,
        ops_result: Any,
        dual_memory_context: str,
        user_id: str | None,
    ) -> str:
        if not ops_result or not hasattr(ops_result, "missing_info"):
            return ""
        missing = ops_result.missing_info
        if not missing:
            return ""

        parts: list[str] = []

        missing_labels = [self._FIELD_LABELS.get(f, f) for f in missing]
        parts.append(f"用户缺少以下关键信息：{'、'.join(missing_labels)}")
        parts.append("请友好地提醒用户补充这些信息，同时可以提供一些目的地相关的推荐来增加互动性。")

        destination = getattr(ops_result, "detected_destination", "")
        if destination:
            parts.append(f"用户已提供目的地：{destination}")
            parts.append(
                f"请利用你对{destination}的了解，主动推荐该地的特色景点、美食、文化活动等，"
                f"让用户在补充信息的同时对旅行产生期待。"
            )

        if dual_memory_context and user_id:
            preference_memories = self._dual_memory.get_long_term_memories(user_id)
            preference_items = [m for m in preference_memories if m.category == "preference"]
            if preference_items:
                prefs = "、".join(m.content for m in preference_items[:5])
                parts.append(
                    f"用户偏好（请据此推荐）：{prefs}"
                )
                parts.append(
                    "当你基于用户偏好做出推荐时，请在推荐后面用【基于记忆：偏好内容】标注依据，"
                    "例如：推荐青岛啤酒博物馆【基于记忆：喜欢文化类景点】"
                )

            stm_list = self._dual_memory.get_short_term_memories(user_id)
            stm_prefs = [m for m in stm_list if m.category == "preference"]
            if stm_prefs:
                prefs = "、".join(m.content for m in stm_prefs[:3])
                if not preference_items:
                    parts.append(f"用户近期偏好（请据此推荐）：{prefs}")
                    parts.append(
                        "当你基于用户偏好做出推荐时，请在推荐后面用【基于记忆：偏好内容】标注依据"
                    )

            experience_items = [m for m in preference_memories if m.category == "experience"]
            stm_exp = [m for m in stm_list if m.category == "experience"]
            all_exp = experience_items + stm_exp
            if all_exp:
                exp_texts = []
                for e in all_exp[:3]:
                    tag = "✓" if e.experience_tag == "success" else "✗"
                    exp_texts.append(f"{tag} {e.content}")
                parts.append(f"用户旅行经验：{'、'.join(exp_texts)}")
                parts.append(
                    "当你基于用户经验调整推荐时，请用【基于记忆：经验内容】标注依据"
                )

        return "\n".join(parts)

    def _build_clarification_question(self, ops_result: Any) -> str:
        """根据 missing_info 构建友好的追问问题，在进入 ReAct 前调用。

        一次性问完所有缺失信息，避免多轮追问。
        """
        destination = getattr(ops_result, "detected_destination", "")
        missing = ops_result.missing_info

        # 如果目的地也缺失，优先问目的地（最关键信息）
        if "destination" in missing:
            return "请问您想去哪个城市旅行？"

        # 目的地已知，一次性问完所有缺失信息
        destination = destination or "目的地"
        question_parts: list[str] = []

        for field in missing:
            label = self._FIELD_LABELS.get(field, field)
            if field == "origin":
                question_parts.append(f"从哪个城市出发")
            elif field == "duration":
                question_parts.append(f"计划旅行几天")
            elif field == "dates":
                question_parts.append(f"大概什么时候出发")
            elif field == "budget":
                question_parts.append(f"预算大概是多少")
            else:
                question_parts.append(f"补充一下{label}")

        if len(question_parts) == 1:
            return f"好的，您想去{destination}旅行。请问{question_parts[0]}？"
        else:
            items = "、".join(question_parts)
            return f"好的，您想去{destination}旅行。请问{items}？"

    def _build_cached_tool_context(self, task: Any) -> str:
        cached = task.get_cached_results()
        if not cached:
            return ""
        parts: list[str] = []
        for category, info in cached.items():
            label = self._CATEGORY_LABELS.get(category, category)
            tool_name = info.get("tool_name", "")
            result = info.get("result", "")
            if not result:
                continue
            truncated = result[:2000] if len(result) > 2000 else result
            parts.append(f"### {label}（来自 {tool_name}）\n{truncated}")
        if not parts:
            return ""
        header = (
            "以下数据是之前搜索获取的，仍然有效。"
            "如果用户只是修改景点、酒店、行程安排等局部内容，请直接使用这些数据，不要重复调用相同的搜索工具。"
            "只有当用户改变了出发地、目的地、出发日期、返程日期等核心参数时，才需要重新搜索对应类别的数据。"
        )
        return header + "\n\n" + "\n\n".join(parts)

    _CORE_CHANGE_KEYWORDS = [
        "出发地", "从哪", "从哪出发", "从哪里", "换个出发",
        "目的地", "去哪", "去哪里", "换个目的", "改去",
        "出发日期", "出发时间", "改日期", "换个日期", "改时间",
        "返程", "回程", "返回时间", "改返程",
    ]

    _LOCAL_CHANGE_KEYWORDS = [
        "换个酒店", "换酒店", "不住", "酒店不好",
        "换个景点", "换景点", "不要这个景点", "景点不好",
        "行程太紧", "太赶", "太累", "轻松一点",
        "换个餐厅", "换餐厅", "不想吃",
    ]

    def _handle_cache_invalidation(
        self,
        task: Any,
        message: str,
        ops_result: TravelIntentResult | None,
    ) -> None:
        """基于 LLM 意图分类结果决定缓存策略，关键词匹配作为兜底。"""
        cached = task.get_cached_results()
        if not cached:
            return

        # ★ 优先使用 LLM 分类结果中的 modification_scope
        if (
            ops_result
            and ops_result.intent == TravelIntentType.ITINERARY_ADJUST
            and ops_result.modification_scope
        ):
            scope = ops_result.modification_scope
            categories = ops_result.affected_categories

            if scope == "full_research":
                task.invalidate_cache()
                logger.info("Cache fully invalidated (LLM classified: full_research) for session %s", task.session_id)
                return
            elif scope == "partial_research" and categories:
                for cat in categories:
                    task.invalidate_cache(cat)
                logger.info("Cache partial invalidated: %s (LLM classified) for session %s", categories, task.session_id)
                return
            elif scope == "local_reorder":
                # 缓存不动，LLM 纯重排
                logger.info("Cache kept (LLM classified: local_reorder) for session %s", task.session_id)
                return

        # ★ 兜底：LLM 分类没有 modification_scope 时，走关键词匹配
        is_core_change = any(kw in message for kw in self._CORE_CHANGE_KEYWORDS)
        if is_core_change:
            task.invalidate_cache()
            logger.info("Cache fully invalidated: core params changed for session %s", task.session_id)
            return
        is_hotel_change = any(kw in message for kw in ["换酒店", "换个酒店", "不住", "酒店不好", "酒店不行"])
        is_poi_change = any(kw in message for kw in ["换景点", "换个景点", "不要这个景点", "景点不好", "景点不行"])
        if is_hotel_change:
            task.invalidate_cache("hotel")
            logger.info("Cache partial invalidation: hotel cache cleared for session %s", task.session_id)
        if is_poi_change:
            task.invalidate_cache("poi")
            logger.info("Cache partial invalidation: poi cache cleared for session %s", task.session_id)

    def _cache_tool_results_from_trace(self, task: Any) -> None:
        if not self._reasoning.last_trace:
            return
        for step in self._reasoning.last_trace:
            if not step.tool_results:
                continue
            for call_info, result_info in zip(step.tool_calls, step.tool_results):
                name = call_info.get("name", "")
                args = call_info.get("arguments", {})
                content = str(result_info.get("content", ""))
                is_error = result_info.get("is_error", False)
                if name and content and not is_error:
                    task.cache_tool_result(name, args, content[:4000])

    def list_user_sessions(self, user_id: str) -> list[dict]:
        # P1-10：委派给 SessionRepository
        from infrastructure.persistence.session_repository import SessionRepository
        return SessionRepository.list_by_user(user_id)

    def delete_session(self, session_id: str, *, user_id: str) -> None:
        task = self._task_store.get(session_id, user_id=user_id)
        if task.user_id != user_id:
            return
        # P1-10：委派给 SessionRepository 级联删除
        from infrastructure.persistence.session_repository import SessionRepository
        SessionRepository.delete(session_id)
        self._session_store._sessions.pop(session_id, None)
        self._task_store._tasks.pop(session_id, None)
