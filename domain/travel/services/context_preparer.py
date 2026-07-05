from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from infrastructure.mcp.runtime import MCPProxyRuntime
from infrastructure.tools.registry import ToolRegistry
from domain.travel.context_manager import ContextManager
from infrastructure.llm.openai import OpenAILLM
from infrastructure.mcp.catalog import MCPCatalog
from domain.memory.manager import DualLayerMemoryManager
from domain.travel.prompt_context import PromptContext
from domain.travel.prompting import PromptBuilder
from domain.reasoning.engine import ReasoningEngine
from domain.shared.runtime.facts import answer_date_or_time_query
from domain.user.session.manager import SessionManager
from domain.user.session.task_state import TaskStateStore
from domain.shared.types import IntentType
from domain.travel.intent.travel_classifier import TravelIntentClassifier, TravelIntentResult
from domain.travel.intent.travel_schema import TravelIntentType
from domain.user.emotion.detector import EmotionDetector
from domain.user.emotion.schema import EmotionResult, EMOTION_STRATEGIES
from domain.user.profile.manager import ProfileManager
from domain.shared.audit.logger import AuditLogger
from domain.travel.services.cache_manager import CacheManager
from domain.travel.services.prompt_helper import PromptHelper
from domain.travel.services.itinerary_generator import ItineraryGenerator

logger = logging.getLogger(__name__)


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


class ContextPreparer:
    def __init__(
        self,
        *,
        llm: OpenAILLM,
        reasoning: ReasoningEngine,
        session_store: SessionManager,
        task_store: TaskStateStore,
        ops_classifier: TravelIntentClassifier | None,
        emotion_detector: EmotionDetector | None,
        prompt_builder: PromptBuilder,
        context_manager: ContextManager,
        dual_memory: DualLayerMemoryManager,
        mcp_catalog: MCPCatalog,
        mcp_runtime: MCPProxyRuntime | None,
        tool_registry: ToolRegistry,
        profile_manager: ProfileManager | None,
        audit_logger: AuditLogger | None,
        cache_manager: CacheManager,
        prompt_helper: PromptHelper,
        itinerary_generator: ItineraryGenerator,
        memory: Any,
    ) -> None:
        self._llm = llm
        self._reasoning = reasoning
        self._session_store = session_store
        self._task_store = task_store
        self._ops_classifier = ops_classifier
        self._emotion_detector = emotion_detector
        self._prompt_builder = prompt_builder
        self._context_manager = context_manager
        self._dual_memory = dual_memory
        self._mcp_catalog = mcp_catalog
        self._mcp_runtime = mcp_runtime
        self._tool_registry = tool_registry
        self._profile_manager = profile_manager
        self._audit_logger = audit_logger
        self._cache_manager = cache_manager
        self._prompt_helper = prompt_helper
        self._itinerary_generator = itinerary_generator
        self._memory = memory

    async def prepare(
        self,
        *,
        session_id: str,
        user_id: str | None,
        message: str,
        memory_scope: str,
        trace_id: str,
    ) -> ChatPreparation:
        """chat 与 chat_stream 共用的上下文准备逻辑。

        流程：设置审计上下文 → 加载 session/task → 追加用户消息 → 检查直答/紧急/快速回复/行程确认
        → 构建工具与记忆上下文 → 生成 system prompt → 写入审计日志。
        命中早退路径时设置 early_action 由调用方处理。
        """
        self._llm.set_audit_context(session_id=session_id, user_id=memory_scope, trace_id=trace_id)
        self._reasoning.set_audit_context(session_id=session_id, user_id=memory_scope, trace_id=trace_id)
        from infrastructure.tools.executor import ToolExecutor

        # ToolExecutor audit context is set by the caller (Agent) since it owns the executor
        session = self._session_store.get(session_id)
        task = self._task_store.get(session_id, user_id=memory_scope)
        session.append("user", message)

        # 直答：运行时事实（日期/时间）
        direct_runtime_answer = answer_date_or_time_query(message)
        if direct_runtime_answer:
            return ChatPreparation(
                session=session,
                task=task,
                intent=None,
                ops_result=None,
                emotion_result=None,
                system="",
                tools=[],
                selected_mcp_tools=[],
                connected_mcp_tools=[],
                memory_context="",
                dual_memory_context="",
                mcp_context="",
                profile_context="",
                urgency_context="",
                prompt_context=None,
                early_action=("direct_runtime_answer", direct_runtime_answer),
            )

        # 意图识别
        ops_result: TravelIntentResult | None = None
        if self._ops_classifier:
            # 构建对话历史（不含当前消息），用于 missing_info 上下文检查
            history_turns = session.turns[:-1] if len(session.turns) > 1 else []
            conversation_history = (
                [{"role": t.role, "content": t.content} for t in history_turns] if history_turns else None
            )

            ops_result = await self._ops_classifier.classify(message, conversation_history=conversation_history)
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
                    session_id=session_id,
                    user_id=memory_scope,
                    trace_id=trace_id,
                    message=message,
                    intent=ops_result.intent.value,
                    goal=intent.goal,
                    confidence=ops_result.confidence,
                    classifier="travel_classifier",
                    raw_llm_output=getattr(ops_result, "raw_output", ""),
                )
        else:
            from domain.shared.types import IntentResult

            intent = IntentResult(
                intent=IntentType.TASK,
                goal=message[:100],
                fast_reply=False,
                force_tool=True,
                tool_hints=[],
            )
        logger.info(
            "Intent resolved: intent=%s fast_reply=%s force_tool=%s travel_intent=%s",
            intent.intent.value,
            intent.fast_reply,
            intent.force_tool,
            ops_result.intent.value if ops_result else "none",
        )

        # 情绪检测
        emotion_result: EmotionResult | None = None
        if self._emotion_detector:
            emotion_result = await self._emotion_detector.detect(message)
            if self._audit_logger:
                self._audit_logger.log_emotion_detect(
                    session_id=session_id,
                    user_id=memory_scope,
                    trace_id=trace_id,
                    message=message,
                    emotion=emotion_result.emotion.value,
                    score=emotion_result.score,
                    confidence=emotion_result.confidence,
                    response_style=emotion_result.response_style,
                    raw_llm_output=getattr(emotion_result, "raw_output", ""),
                )

        # 紧急关键词
        emergency_reply = self._check_emergency_keywords(message)
        if emergency_reply:
            return ChatPreparation(
                session=session,
                task=task,
                intent=intent,
                ops_result=ops_result,
                emotion_result=emotion_result,
                system="",
                tools=[],
                selected_mcp_tools=[],
                connected_mcp_tools=[],
                memory_context="",
                dual_memory_context="",
                mcp_context="",
                profile_context="",
                urgency_context="",
                prompt_context=None,
                early_action=("emergency_reply", emergency_reply),
            )

        task.mark_in_progress(goal=intent.goal, latest_user_message=message)
        self._cache_manager.handle_invalidation(task, message, ops_result)
        self._task_store.save(task)
        logger.info(
            "Intent analyzed: session_id=%s user_id=%s intent=%s emotion=%s force_tool=%s",
            session_id,
            memory_scope,
            ops_result.intent.value if ops_result else intent.intent.value,
            emotion_result.emotion.value if emotion_result else "none",
            intent.force_tool,
        )

        # 快速回复路径
        if intent.fast_reply and intent.intent in {IntentType.CHAT, IntentType.QUERY}:
            logger.warning("FAST_REPLY path triggered! intent=%s fast_reply=%s", intent.intent.value, intent.fast_reply)
            system = self._prompt_builder.build_fast_reply_system(intent)
            return ChatPreparation(
                session=session,
                task=task,
                intent=intent,
                ops_result=ops_result,
                emotion_result=emotion_result,
                system=system,
                tools=[],
                selected_mcp_tools=[],
                connected_mcp_tools=[],
                memory_context="",
                dual_memory_context="",
                mcp_context="",
                profile_context="",
                urgency_context="",
                prompt_context=None,
                early_action=("fast_reply", system),
            )

        # 行程确认路径
        if ops_result and ops_result.intent == TravelIntentType.ITINERARY_CONFIRM:
            logger.info("itinerary_confirm: bypassing LLM, directly calling generate_itinerary_overview")
            return ChatPreparation(
                session=session,
                task=task,
                intent=intent,
                ops_result=ops_result,
                emotion_result=emotion_result,
                system="",
                tools=[],
                selected_mcp_tools=[],
                connected_mcp_tools=[],
                memory_context="",
                dual_memory_context="",
                mcp_context="",
                profile_context="",
                urgency_context="",
                prompt_context=None,
                early_action=("itinerary_confirm", ops_result),
            )

        # 缺失信息澄清路径：TRIP_PLANNING 且存在 missing_info 时，先追问再进入 ReAct
        if ops_result and ops_result.intent == TravelIntentType.TRIP_PLANNING and ops_result.missing_info:
            logger.info(
                "trip_planning with missing_info: %s, generating clarification before ReAct",
                ops_result.missing_info,
            )
            clarification_question = self._prompt_helper.build_clarification_question(ops_result)
            return ChatPreparation(
                session=session,
                task=task,
                intent=intent,
                ops_result=ops_result,
                emotion_result=emotion_result,
                system="",
                tools=[],
                selected_mcp_tools=[],
                connected_mcp_tools=[],
                memory_context="",
                dual_memory_context="",
                mcp_context="",
                profile_context="",
                urgency_context="",
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
            session_id,
            memory_scope,
            ",".join(tools),
            bool(memory_context),
            ",".join(ref.proxy_name for ref in connected_mcp_tools),
            emotion_result.emotion.value if emotion_result else "none",
        )
        cached_tool_context = self._cache_manager.build_cached_context(task)
        missing_info_context = self._prompt_helper.build_missing_info_context(ops_result, dual_memory_context, user_id)
        itinerary_confirm_context = self._itinerary_generator.build_confirm_context(
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
                session_id=session_id,
                user_id=memory_scope,
                trace_id=trace_id,
                system_prompt=system,
                tools=tools,
                memory_context=memory_context,
                dual_memory_context=dual_memory_context,
                mcp_context=mcp_context,
                profile_context=profile_context,
                emotion_context=urgency_context,
                selected_mcp_tools=[ref.proxy_name for ref in selected_mcp_tools],
                connected_mcp_tools=[ref.proxy_name for ref in connected_mcp_tools],
            )

        # 构建对话历史供 ReAct 引擎使用
        conversation_history = [
            {"role": t.role, "content": t.content}
            for t in session.turns[:-1]  # 排除当前用户消息
            if t.role in ("user", "assistant") and t.content
        ]

        return ChatPreparation(
            session=session,
            task=task,
            intent=intent,
            ops_result=ops_result,
            emotion_result=emotion_result,
            system=system,
            tools=tools,
            selected_mcp_tools=selected_mcp_tools,
            connected_mcp_tools=connected_mcp_tools,
            memory_context=memory_context,
            dual_memory_context=dual_memory_context,
            mcp_context=mcp_context,
            profile_context=profile_context,
            urgency_context=urgency_context,
            prompt_context=prompt_context,
            early_action=None,
            conversation_history=conversation_history,
        )

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
