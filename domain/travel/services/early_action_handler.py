from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any

from infrastructure.llm.openai import OpenAILLM
from domain.memory.manager import SessionMemory
from domain.user.session.manager import SessionManager
from domain.user.session.task_state import TaskStatus, TaskStateStore
from domain.shared.runtime.trace import RunTrace, TraceStore
from domain.travel.services.context_preparer import ChatPreparation
from domain.travel.services.itinerary_generator import ItineraryGenerator
from domain.travel.services.memory_processor import MemoryProcessor

logger = logging.getLogger(__name__)


class EarlyActionHandler:
    def __init__(
        self,
        *,
        llm: OpenAILLM,
        memory: SessionMemory,
        session_store: SessionManager,
        task_store: TaskStateStore,
        trace_store: TraceStore,
        itinerary_generator: ItineraryGenerator,
        memory_processor: MemoryProcessor,
    ) -> None:
        self._llm = llm
        self._memory = memory
        self._session_store = session_store
        self._task_store = task_store
        self._trace_store = trace_store
        self._itinerary_generator = itinerary_generator
        self._memory_processor = memory_processor

    async def handle(
        self,
        *,
        prep: ChatPreparation,
        session_id: str,
        user_id: str | None,
        memory_scope: str,
        message: str,
    ) -> dict[str, str] | None:
        """处理 chat() 的早退动作。返回结果 dict 或 None（无早退）。"""
        if not prep.early_action:
            return None

        kind, payload = prep.early_action
        session = prep.session
        task = prep.task

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
            reply, itinerary_id = await self._itinerary_generator.generate_itinerary(
                session=session, session_id=session_id,
                user_id=memory_scope, ops_result=ops_result,
            )
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
            await self._memory_processor.process(session, session_id, memory_scope, user_id)
            result: dict[str, str] = {"status": "completed", "reply": reply}
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

        return None

    async def handle_stream(
        self,
        *,
        prep: ChatPreparation,
        session_id: str,
        user_id: str | None,
        memory_scope: str,
        message: str,
    ) -> AsyncGenerator[dict[str, str], None]:
        """处理 chat_stream() 的早退动作。yield 事件流。"""
        if not prep.early_action:
            return

        kind, payload = prep.early_action
        session = prep.session
        task = prep.task

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

        # fast_reply / itinerary_confirm / need_input 都需要先发 thinking 状态
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
            reply, itinerary_id = await self._itinerary_generator.generate_itinerary(
                session=session, session_id=session_id, user_id=memory_scope, ops_result=ops_result,
            )
            if itinerary_id:
                task.metadata["last_itinerary_id"] = itinerary_id
            session.append("assistant", reply)
            self._memory.refresh_summary(session)
            self._session_store.save(session, user_id=memory_scope)
            task.mark_finished(status=TaskStatus.COMPLETED, reply=reply)
            self._task_store.save(task)
            await self._memory_processor.process(session, session_id, memory_scope, user_id)
            yield {"type": "chunk", "data": reply}
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
