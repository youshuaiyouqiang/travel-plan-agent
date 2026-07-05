from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncGenerator
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
from domain.travel.prompting import PromptBuilder
from domain.reasoning.engine import AskUserNeeded, ReasoningEngine, ConfirmationNeeded
from domain.user.session.manager import SessionManager
from domain.user.session.task_state import TaskStatus, TaskStateStore
from domain.shared.runtime.trace import RunTrace, TraceStore
from domain.travel.intent.travel_classifier import TravelIntentClassifier
from domain.user.emotion.detector import EmotionDetector
from domain.user.profile.manager import ProfileManager
from domain.shared.audit.logger import AuditLogger
from domain.travel.services.context_preparer import ChatPreparation, ContextPreparer
from domain.travel.services.itinerary_generator import ItineraryGenerator
from domain.travel.services.cache_manager import CacheManager
from domain.travel.services.prompt_helper import PromptHelper
from domain.travel.services.memory_processor import MemoryProcessor
from domain.travel.services.early_action_handler import EarlyActionHandler

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
            llm=llm, tool_registry=tool_registry,
            tool_executor=tool_executor, audit_logger=audit_logger,
        )
        self._ops_classifier = ops_classifier
        self._emotion_detector = emotion_detector
        self._profile_manager = profile_manager or ProfileManager()
        self._audit_logger = audit_logger

        # Service objects
        self._cache_manager = CacheManager(reasoning=self._reasoning, dual_memory=self._dual_memory)
        self._prompt_helper = PromptHelper(dual_memory=self._dual_memory)
        self._itinerary_generator = ItineraryGenerator(llm=self._llm, session_store=self._session_store, dual_memory=self._dual_memory)
        self._memory_processor = MemoryProcessor(dual_memory=self._dual_memory, memory_extractor=self._memory_extractor, memory_distiller=self._memory_distiller)
        self._early_action_handler = EarlyActionHandler(
            llm=self._llm, memory=self._memory, session_store=self._session_store,
            task_store=self._task_store, trace_store=self._trace_store,
            itinerary_generator=self._itinerary_generator, memory_processor=self._memory_processor,
        )
        self._context_preparer = ContextPreparer(
            llm=self._llm, reasoning=self._reasoning, session_store=self._session_store,
            task_store=self._task_store, ops_classifier=self._ops_classifier,
            emotion_detector=self._emotion_detector, prompt_builder=self._prompt_builder,
            context_manager=self._context_manager, dual_memory=self._dual_memory,
            mcp_catalog=self._mcp_catalog, mcp_runtime=self._mcp_runtime,
            tool_registry=self._tool_registry, profile_manager=self._profile_manager,
            audit_logger=self._audit_logger, cache_manager=self._cache_manager,
            prompt_helper=self._prompt_helper, itinerary_generator=self._itinerary_generator,
            memory=self._memory,
        )

    ChatPreparation = ChatPreparation

    async def _prepare_chat_context(self, *, session_id: str, user_id: str | None, message: str, memory_scope: str, trace_id: str) -> ChatPreparation:
        self._tool_executor.set_audit_context(session_id=session_id, user_id=memory_scope, trace_id=trace_id)
        return await self._context_preparer.prepare(session_id=session_id, user_id=user_id, message=message, memory_scope=memory_scope, trace_id=trace_id)

    async def _finalize_chat(self, *, session_id: str, user_id: str | None, memory_scope: str, trace_id: str, start_time: float, message: str, prep: ChatPreparation, reply: str, status: str, events: list[dict]) -> None:
        session, task, intent, emotion_result = prep.session, prep.task, prep.intent, prep.emotion_result
        session.append("assistant", reply)
        self._memory.refresh_summary(session)
        self._session_store.save(session, user_id=memory_scope)
        if status == "completed":
            task.mark_finished(status=TaskStatus.COMPLETED, reply=reply)
        self._cache_manager.cache_results_from_trace(task)
        task.trace_summary = self._summarize_trace()
        self._task_store.save(task)
        self._trace_store.put(RunTrace(session_id=session_id, user_id=memory_scope, user_message=message, reply=reply, intent=intent.intent.value, goal=intent.goal, tools=prep.tools, memory_context=prep.memory_context, trace_steps=list(self._reasoning.last_trace), events=events))
        logger.info("Agent reasoning complete: session_id=%s user_id=%s", session_id, memory_scope)
        if self._audit_logger:
            self._audit_logger.log_session_complete(session_id=session_id, user_id=memory_scope, trace_id=trace_id, user_message=message, reply=reply, intent=intent.intent.value, emotion=emotion_result.emotion.value if emotion_result else "none", total_duration_ms=int((time.monotonic() - start_time) * 1000), trace_summary=self._summarize_trace())
        await self._memory_processor.process(session, session_id, memory_scope, user_id)

    async def chat(self, *, session_id: str, message: str, user_id: str | None = None, trace_id: str = "") -> dict[str, str]:
        memory_scope = str(user_id or session_id)
        trace_id = trace_id or uuid.uuid4().hex[:16]
        start_time = time.monotonic()
        logger.info("Agent chat start: session_id=%s user_id=%s trace_id=%s message=%s", session_id, user_id or session_id, trace_id, message[:100])

        prep = await self._prepare_chat_context(session_id=session_id, user_id=user_id, message=message, memory_scope=memory_scope, trace_id=trace_id)

        # 处理早退动作
        early_result = await self._early_action_handler.handle(prep=prep, session_id=session_id, user_id=user_id, memory_scope=memory_scope, message=message)
        if early_result is not None:
            return early_result

        # ReAct 推理主路径
        task = prep.task
        status = "completed"
        try:
            reply = await self._reasoning.run(system_prompt=prep.system, user_message=message, force_tool=prep.intent.force_tool, conversation_history=prep.conversation_history)
        except AskUserNeeded as exc:
            reply = exc.question
            status = "needs_user_input"
            task.mark_waiting(status=TaskStatus.NEEDS_USER_INPUT, prompt=exc.question, reply=reply)
        except ConfirmationNeeded as exc:
            reply = exc.prompt
            status = "needs_confirmation"
            task.mark_waiting(status=TaskStatus.NEEDS_CONFIRMATION, prompt=exc.prompt, reply=reply)

        events = [
            {"kind": "context", "message": "Prepared context", "payload": {"trimmed": prep.prompt_context.prepared_context.was_trimmed}},
            {"kind": "memory", "message": "Built memory context", "payload": {"has_memory": bool(prep.memory_context), "scope_id": memory_scope}},
            {"kind": "mcp", "message": "Built MCP context", "payload": {"has_mcp": bool(prep.mcp_context), "selected_tools": [ref.proxy_name for ref in prep.selected_mcp_tools], "connected_tools": [ref.proxy_name for ref in prep.connected_mcp_tools]}},
            {"kind": "result", "message": "Agent run finished", "payload": {"status": status}},
        ]
        await self._finalize_chat(session_id=session_id, user_id=user_id, memory_scope=memory_scope, trace_id=trace_id, start_time=start_time, message=message, prep=prep, reply=reply, status=status, events=events)
        return {"status": status, "reply": reply, "trace_id": trace_id}

    async def chat_stream(self, *, session_id: str, message: str, user_id: str | None = None, trace_id: str = "") -> AsyncGenerator[dict[str, str], None]:
        """流式聊天：工具调用阶段同步执行，最终回复阶段逐 token 流式输出。"""
        memory_scope = str(user_id or session_id)
        trace_id = trace_id or uuid.uuid4().hex[:16]
        start_time = time.monotonic()
        logger.info("Agent chat_stream start: session_id=%s user_id=%s trace_id=%s", session_id, user_id or session_id, trace_id)

        prep = await self._prepare_chat_context(session_id=session_id, user_id=user_id, message=message, memory_scope=memory_scope, trace_id=trace_id)

        # 处理早退动作（流式）
        early_handled = False
        async for event in self._early_action_handler.handle_stream(prep=prep, session_id=session_id, user_id=user_id, memory_scope=memory_scope, message=message):
            yield event
            early_handled = True
        if early_handled:
            return

        # 主推理路径
        yield {"type": "status", "data": "thinking"}
        task = prep.task
        status = "completed"
        full_reply = ""
        try:
            async for chunk in self._reasoning.run_stream(system_prompt=prep.system, user_message=message, force_tool=prep.intent.force_tool, conversation_history=prep.conversation_history):
                if chunk.startswith("__status__:"):
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

        events = [{"kind": "stream_result", "message": "Stream run finished", "payload": {"status": status}}]
        await self._finalize_chat(session_id=session_id, user_id=user_id, memory_scope=memory_scope, trace_id=trace_id, start_time=start_time, message=message, prep=prep, reply=full_reply, status=status, events=events)
        yield {"type": "done", "data": status, "trace_id": trace_id}

    # ===== 查询/快照 =====

    def latest_trace(self, session_id: str) -> dict | None:
        trace = self._trace_store.latest(session_id)
        return trace.to_dict() if trace else None

    def snapshot_session(self, session_id: str) -> dict | None:
        return self._session_store.snapshot(session_id)

    def snapshot_task(self, session_id: str, *, user_id: str | None = None) -> dict:
        effective_user_id = str(user_id or session_id)
        return self._task_store.snapshot(session_id, user_id=effective_user_id)

    # ===== MCP =====

    def list_mcp_servers(self) -> list[dict]:
        return [
            {
                "identifier": server.identifier, "name": server.name,
                "description": server.description, "instructions": server.instructions,
                "tools": [
                    {"name": tool.name, "description": tool.description, "input_schema": tool.input_schema, "proxy_name": tool.proxy_name, "adapter_available": bool(self._mcp_runtime and self._mcp_runtime.adapter_available(tool.proxy_name))}
                    for tool in server.tools
                ],
            }
            for server in self._mcp_catalog.list_servers()
        ]

    def select_mcp_tools(self, query: str, limit: int = 4) -> list[dict]:
        return [
            {"server_identifier": ref.server_identifier, "server_name": ref.server_name, "tool_name": ref.tool_name, "proxy_name": ref.proxy_name, "description": ref.description, "adapter_available": bool(self._mcp_runtime and self._mcp_runtime.adapter_available(ref.proxy_name))}
            for ref in self._mcp_catalog.select_tool_refs(query, limit=limit)
        ]

    # ===== 会话管理 =====

    def list_user_sessions(self, user_id: str) -> list[dict]:
        from infrastructure.persistence.session_repository import SessionRepository
        return SessionRepository.list_by_user(user_id)

    def delete_session(self, session_id: str, *, user_id: str) -> None:
        task = self._task_store.get(session_id, user_id=user_id)
        if task.user_id != user_id:
            return
        from infrastructure.persistence.session_repository import SessionRepository
        SessionRepository.delete(session_id)
        self._session_store._sessions.pop(session_id, None)
        self._task_store._tasks.pop(session_id, None)

    # ===== 向后兼容委托（原私有方法已移至 service 类） =====

    def _build_missing_info_context(self, ops_result: Any, dual_memory_context: str, user_id: str | None) -> str:
        return self._prompt_helper.build_missing_info_context(ops_result, dual_memory_context, user_id)

    def _build_clarification_question(self, ops_result: Any) -> str:
        return self._prompt_helper.build_clarification_question(ops_result)

    def _build_cached_tool_context(self, task: Any) -> str:
        return self._cache_manager.build_cached_context(task)

    def _handle_cache_invalidation(self, task: Any, message: str, ops_result: Any) -> None:
        self._cache_manager.handle_invalidation(task, message, ops_result)

    def _cache_tool_results_from_trace(self, task: Any) -> None:
        self._cache_manager.cache_results_from_trace(task)

    def _check_emergency_keywords(self, message: str) -> str | None:
        return ContextPreparer.check_emergency_keywords(message)

    # ===== 内部工具 =====

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
