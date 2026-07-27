from __future__ import annotations
import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any
from config import settings
from domain.shared.tools.executor import ToolExecutor
from domain.shared.tools.registry import ToolRegistry
from domain.shared.llm.ports import LLMPort
from domain.shared.audit.context import AuditContext
from domain.shared.types import DecisionType
from domain.reasoning.cost_guard import CostGuard
from domain.reasoning.tool_selector import ToolSelector
from domain.reasoning.json_extract import extract_json_object, strip_code_fences
from domain.reasoning.text_cleaning import clean_final_answer, looks_grounded
from domain.reasoning.decision_parser import DecisionParser, make_signature
from domain.reasoning.prompts import REACT_SYSTEM_SUFFIX
from domain.reasoning.schema_builder import build_func_def, tool_status_text
from domain.reasoning.message_builder import (
    append_tool_result_messages,
    build_working_messages,
)

logger = logging.getLogger(__name__)

# ── 向后兼容别名（P6.1：纯函数已迁移到 json_extract.py） ──────────────────
# 既有测试通过 engine._strip_code_fences / _extract_json_object 导入；
# 拆分后保留别名以避免公开导入路径回归。
_strip_code_fences = strip_code_fences
_extract_json_object = extract_json_object


@dataclass
class TraceStep:
    iteration: int
    decision_type: str
    text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    system_note: str = ""


class AskUserNeeded(Exception):
    def __init__(self, question: str) -> None:
        super().__init__(question)
        self.question = question


class ConfirmationNeeded(Exception):
    def __init__(self, prompt: str) -> None:
        super().__init__(prompt)
        self.prompt = prompt


class ReasoningEngine:
    def __init__(
        self,
        *,
        llm: LLMPort,
        tool_registry: ToolRegistry,
        tool_executor: ToolExecutor,
        audit_logger: Any | None = None,
    ) -> None:
        self._llm = llm
        self._tool_registry = tool_registry
        self._tool_executor = tool_executor
        self._audit_logger = audit_logger
        self.last_trace: list[TraceStep] = []
        self._tools_schema: list[dict[str, Any]] | None = None
        # ===== P1-2：CostGuard 与 ToolSelector 接入 =====
        self._cost_guard = CostGuard(
            max_iterations=settings.max_iterations,
            max_tool_calls=20,
            token_budget=50000,
        )
        self._tool_selector = ToolSelector()
        # P6.1：决策解析委托给 DecisionParser
        self._decision_parser = DecisionParser(
            tool_registry=tool_registry,
            tool_executor=tool_executor,
        )
        # 已披露工具集：跨多次 run() 累积，实现渐进式披露
        self._disclosed_tools: set[str] = set()

    def set_audit_context(self, *, session_id: str, user_id: str, trace_id: str = "") -> None:
        # P0-5：用共享 ContextVar 替代实例属性，并发安全
        AuditContext.set(session_id=session_id, user_id=user_id, trace_id=trace_id)

    def _auto_disclose(self, user_message: str) -> None:
        """P1-2：根据用户消息自动披露相关工具（渐进式披露的自动推荐）。

        每次调用会向 _disclosed_tools 累加新推荐的工具名。
        若用户消息命中任何工具的关键词，下次构建 schema 时仅包含已披露子集；
        若无任何命中（闲聊/简单问答），_disclosed_tools 保持原状，schema 构建时由调用方决定 fallback。
        """
        if not user_message.strip():
            return
        all_specs = self._tool_registry.get_all_specs()
        # 已披露的不再重复推荐
        recommendations = self._tool_selector.select(
            message=user_message,
            all_specs=all_specs,
            already_disclosed=self._disclosed_tools,
            limit=5,
        )
        for spec in recommendations:
            self._disclosed_tools.add(spec.name)
        if recommendations:
            logger.info(
                "ToolSelector disclosed %d tools: %s",
                len(recommendations),
                [s.name for s in recommendations],
            )

    def _build_active_tools_schema(self) -> list[dict[str, Any]]:
        """P1-2：构建当前激活的工具 schema。

        - 若 _disclosed_tools 非空：仅包含已披露子集（渐进式披露）
        - 若 _disclosed_tools 为空（用户消息未命中任何工具关键词）：fallback 到全量 schema
        """
        if self._disclosed_tools:
            return self._build_tools_schema(disclosed_tools=self._disclosed_tools)
        return self._build_tools_schema()

    def _record_trace(self, trace: TraceStep) -> None:
        self.last_trace.append(trace)
        if self._audit_logger:
            ctx = AuditContext.get()
            self._audit_logger.log_reasoning_step(
                session_id=ctx.session_id,
                user_id=ctx.user_id,
                trace_id=ctx.trace_id,
                iteration=trace.iteration,
                decision_type=trace.decision_type,
                text=trace.text,
                tool_calls=trace.tool_calls,
                tool_results=trace.tool_results,
                system_note=trace.system_note,
            )

    def _build_tools_schema(self, disclosed_tools: set[str] | None = None) -> list[dict[str, Any]]:
        """构建传给 LLM 的 native tools schema。

        当 disclosed_tools 为 None 时：全量构建（向后兼容，缓存全量结果）。
        当 disclosed_tools 非空时：仅包含指定子集工具（不缓存，每次都动态构建）。
        """
        # disclosed 非空时绕过缓存，动态构建子集
        if disclosed_tools is not None:
            schema: list[dict[str, Any]] = []
            for name in disclosed_tools:
                if self._tool_registry.has(name):
                    tool = self._tool_registry.get(name)
                    func_def = build_func_def(tool.spec)
                    schema.append(func_def)
            return schema

        # 全量模式：使用缓存
        if self._tools_schema is not None:
            return self._tools_schema
        schema = []
        for tool in self._tool_registry.iter_tools():
            func_def = build_func_def(tool.spec)
            schema.append(func_def)
        self._tools_schema = schema
        return schema

    async def run(
        self,
        *,
        system_prompt: str,
        user_message: str,
        force_tool: bool,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> str:
        working_messages = build_working_messages(user_message, conversation_history)
        self.last_trace = []
        no_tool_rounds = 0
        ungrounded_rounds = 0
        best_text = ""
        tools_executed = False
        seen_signatures: dict[str, int] = {}
        use_native = getattr(settings, "use_native_tool_calling", True)
        # ===== P1-2：CostGuard 重置 + ToolSelector 自动披露 =====
        self._cost_guard.iterations = 0
        self._cost_guard.tokens_used = 0
        self._cost_guard.tool_calls_used = 0
        self._auto_disclose(user_message)
        tools_schema = self._build_active_tools_schema() if use_native else None

        for iteration in range(1, settings.max_iterations + 1):
            # ===== P1-2：CostGuard 预算检查 =====
            if not self._cost_guard.can_continue():
                logger.warning("CostGuard stopped reasoning: %s", self._cost_guard.exceeded_detail())
                break

            logger.info("===== Reasoning iteration %s/%s =====", iteration, settings.max_iterations)

            near_limit = iteration >= settings.max_iterations - 2

            if use_native and tools_schema:
                llm_resp = await self._llm.complete_with_tools(
                    system=system_prompt,
                    messages=working_messages,
                    tools=tools_schema if not near_limit else None,
                )
                decision = self._decision_parser.llm_response_to_decision(llm_resp)
                if not decision.text and not decision.tool_calls:
                    decision = self._decision_parser.parse_decision(llm_resp.content or "")
            else:
                response = await self._llm.complete(
                    system=system_prompt + "\n\n" + REACT_SYSTEM_SUFFIX,
                    messages=working_messages,
                )
                decision = self._decision_parser.parse_decision(response)
            logger.info(
                "Decision: type=%s tool_calls=%s text_preview=%s",
                decision.decision_type.value,
                [call.name for call in decision.tool_calls],
                decision.text[:100] if decision.text else "",
            )
            trace = TraceStep(
                iteration=iteration,
                decision_type=decision.decision_type.value,
                text=decision.text,
                tool_calls=[
                    {"name": call.name, "arguments": call.arguments, "id": call.call_id} for call in decision.tool_calls
                ],
            )

            if decision.decision_type == DecisionType.FINAL_ANSWER:
                logger.debug("Reasoning final answer: iteration=%s", iteration)
                if len(decision.text) > len(best_text):
                    best_text = decision.text
                if force_tool and not tools_executed and no_tool_rounds < 2:
                    no_tool_rounds += 1
                    trace.system_note = "forced_retry_no_tools"
                    working_messages.append({"role": "assistant", "content": decision.text})
                    working_messages.append(
                        {
                            "role": "user",
                            "content": (
                                "You have not used tools yet. "
                                "If the task requires action, call tools now. "
                                "If the task truly needs no tools, provide a direct complete answer."
                            ),
                        }
                    )
                    self._record_trace(trace)
                    continue
                if tools_executed and not looks_grounded(decision.text):
                    if len(decision.text) > len(best_text):
                        best_text = decision.text
                    ungrounded_rounds += 1
                    if ungrounded_rounds >= 3:
                        logger.warning(
                            "Reasoning: accepting best text after %d ungrounded rounds (len=%d)",
                            ungrounded_rounds,
                            len(best_text),
                        )
                        self._record_trace(trace)
                        if best_text:
                            return clean_final_answer(best_text.strip())
                        return clean_final_answer(decision.text.strip() or "No response generated.")
                    trace.system_note = "final_answer_failed_minimal_verification"
                    self._record_trace(trace)
                    working_messages.append({"role": "assistant", "content": decision.text})
                    working_messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Your final answer is too weak or ungrounded relative to the tool results. "
                                "You must provide the FULL detailed itinerary plan (with daily schedule, transportation, "
                                "hotel recommendations, budget breakdown, etc.) BEFORE asking the user if they are satisfied. "
                                "Do NOT just ask for confirmation without showing the plan first. "
                                "Use the tool results explicitly to build a complete travel plan."
                            ),
                        }
                    )
                    continue
                self._record_trace(trace)
                cleaned = clean_final_answer(decision.text.strip() or "No response generated.")
                return cleaned

            no_tool_rounds = 0
            duplicate_round = False
            for call in decision.tool_calls:
                signature = make_signature(call)
                seen_signatures[signature] = seen_signatures.get(signature, 0) + 1
                if seen_signatures[signature] >= 3:
                    duplicate_round = True

            if duplicate_round:
                logger.warning("Reasoning duplicate tool call pattern detected")
                trace.system_note = "duplicate_tool_calls_detected"
                self._record_trace(trace)
                working_messages.append({"role": "assistant", "content": decision.text})
                working_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "You are repeating the same tool call pattern. "
                            "Use a different tool, ask the user for missing information, "
                            "or provide the best final answer."
                        ),
                    }
                )
                continue

            if near_limit and decision.tool_calls:
                logger.warning(
                    "Reasoning near iteration limit (%s/%s), forcing final answer",
                    iteration,
                    settings.max_iterations,
                )
                trace.system_note = "forced_final_answer_near_limit"
                self._record_trace(trace)
                working_messages.append({"role": "assistant", "content": decision.text or ""})
                working_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "You are approaching the maximum number of reasoning steps. "
                            "You MUST now provide a complete final answer to the user based on the information you have gathered. "
                            "Do NOT call any more tools. Synthesize all the tool results into a clear, helpful response."
                        ),
                    }
                )
                continue

            tool_results = await self._tool_executor.execute(decision.tool_calls)
            for i, (call, result) in enumerate(zip(decision.tool_calls, tool_results)):
                result_preview = str(result.get("content", ""))[:200]
                is_error = result.get("is_error", False)
                log_level = logging.WARNING if is_error else logging.INFO
                logger.log(
                    log_level,
                    "Tool result [%s]: name=%s args=%s error=%s result=%s",
                    i + 1,
                    call.name,
                    json.dumps(call.arguments, ensure_ascii=False)[:200],
                    is_error,
                    result_preview,
                )
            tools_executed = True
            # ===== P1-2：CostGuard 消耗记账 =====
            # sync iterations with loop counter; count each tool call
            self._cost_guard.iterations = iteration
            self._cost_guard.tool_calls_used += len(decision.tool_calls)
            trace.tool_results = tool_results
            self._record_trace(trace)

            confirmation_required = [result for result in tool_results if result.get("requires_confirmation")]
            if confirmation_required:
                first = confirmation_required[0]
                question = str(first.get("content") or "Confirmation required.")
                logger.info("Reasoning paused for confirmation: %s", question)
                raise ConfirmationNeeded(question)

            for result in tool_results:
                if result.get("ask_user"):
                    if iteration == 1 and not tools_executed:
                        logger.info(
                            "ask_user called on first iteration without any search tools - suppressing and redirecting to search tools"
                        )
                        trace.system_note = "ask_user_suppressed_first_iteration"
                        self._record_trace(trace)
                        working_messages.append({"role": "assistant", "content": decision.text})
                        working_messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "The user has already provided sufficient information in their message. "
                                    "Do NOT call ask_user again. Instead, proceed directly with the available search tools "
                                    "(fliggy_search_flight, fliggy_search_train, fliggy_search_hotel, amap_search_poi, amap_get_weather, etc.) "
                                    "to gather real data and generate a travel plan. "
                                    "If some minor details are missing, make reasonable assumptions and proceed."
                                ),
                            }
                        )
                        continue
                    logger.info("Reasoning interrupted for ask_user")
                    raise AskUserNeeded(str(result.get("question") or result.get("content") or ""))

            append_tool_result_messages(
                working_messages,
                decision,
                tool_results,
                trace.tool_calls,
                decision.text,
                use_native,
                include_error_conditional=True,
            )

        logger.warning("Reasoning stopped after max iterations")
        if best_text:
            logger.info("Reasoning: returning best collected text (len=%d)", len(best_text))
            return clean_final_answer(best_text.strip())
        return "Stopped after reaching the maximum iteration limit."

    async def run_stream(
        self,
        *,
        system_prompt: str,
        user_message: str,
        force_tool: bool,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> AsyncGenerator[str, None]:
        """流式推理：工具调用阶段同步执行，最终回复阶段逐 token 流式输出。

        yield 的字符串中，以 ``__status__:`` 开头的是状态通知（非文本内容），
        上层 agent 应将其转为 tool_status SSE 事件，不写入最终回复文本。
        """
        working_messages = build_working_messages(user_message, conversation_history)
        self.last_trace = []
        no_tool_rounds = 0
        best_text = ""
        tools_executed = False
        seen_signatures: dict[str, int] = {}
        use_native = getattr(settings, "use_native_tool_calling", True)
        # ===== P1-2：CostGuard 重置 + ToolSelector 自动披露 =====
        self._cost_guard.iterations = 0
        self._cost_guard.tokens_used = 0
        self._cost_guard.tool_calls_used = 0
        self._auto_disclose(user_message)
        tools_schema = self._build_active_tools_schema() if use_native else None

        for iteration in range(1, settings.max_iterations + 1):
            # ===== P1-2：CostGuard 预算检查 =====
            if not self._cost_guard.can_continue():
                logger.warning(
                    "CostGuard stopped stream reasoning: %s",
                    self._cost_guard.exceeded_detail(),
                )
                break

            logger.info("===== Reasoning stream iteration %s/%s =====", iteration, settings.max_iterations)
            near_limit = iteration >= settings.max_iterations - 2

            yield f"__status__:thinking_round_{iteration}"

            # 非流式阶段：正常调用 complete_with_tools，让模型自己决定是否调用工具
            if use_native and tools_schema:
                llm_resp = await self._llm.complete_with_tools(
                    system=system_prompt,
                    messages=working_messages,
                    tools=tools_schema if not near_limit else None,
                )
                decision = self._decision_parser.llm_response_to_decision(llm_resp)
                if not decision.text and not decision.tool_calls:
                    decision = self._decision_parser.parse_decision(llm_resp.content or "")
            else:
                response = await self._llm.complete(
                    system=system_prompt + "\n\n" + REACT_SYSTEM_SUFFIX,
                    messages=working_messages,
                )
                decision = self._decision_parser.parse_decision(response)

            logger.info(
                "Stream Decision: type=%s tool_calls=%s",
                decision.decision_type.value,
                [call.name for call in decision.tool_calls],
            )
            trace = TraceStep(
                iteration=iteration,
                decision_type=decision.decision_type.value,
                text=decision.text,
                tool_calls=[
                    {"name": call.name, "arguments": call.arguments, "id": call.call_id} for call in decision.tool_calls
                ],
            )

            # ===== FINAL_ANSWER：模型已决定给出最终答案 =====
            if decision.decision_type == DecisionType.FINAL_ANSWER:
                if len(decision.text) > len(best_text):
                    best_text = decision.text

                # 如果还没执行工具但 force_tool，强制重试
                if force_tool and not tools_executed and no_tool_rounds < 2:
                    no_tool_rounds += 1
                    trace.system_note = "forced_retry_no_tools"
                    working_messages.append({"role": "assistant", "content": decision.text})
                    working_messages.append(
                        {
                            "role": "user",
                            "content": "You have not used tools yet. If the task requires action, call tools now. If the task truly needs no tools, provide a direct complete answer.",
                        }
                    )
                    self._record_trace(trace)
                    continue

                self._record_trace(trace)
                answer = clean_final_answer(decision.text.strip() or "No response generated.")

                if tools_executed:
                    yield "__status__:generating_answer"
                    # 工具已执行，decision.text 是经过完整解析的干净文本
                    # 逐块 yield 模拟流式输出，避免 stream_complete 误输出 tool call JSON
                    chunk_size = 3
                    for i in range(0, len(answer), chunk_size):
                        yield answer[i : i + chunk_size]
                        await asyncio.sleep(0.03)
                else:
                    # 无工具调用（闲聊、简单问答），使用真正的流式 API
                    yield "__status__:generating_answer"
                    try:
                        stream_text = ""
                        async for chunk in self._llm.stream_complete(
                            system=system_prompt,
                            messages=working_messages,
                        ):
                            stream_text += chunk
                            yield chunk
                        if not stream_text.strip():
                            yield answer
                    except Exception:
                        yield answer
                return

            # ===== 工具调用处理 =====
            # 发送工具执行状态通知
            for call in decision.tool_calls:
                yield f"__status__:{tool_status_text(call.name)}"

            duplicate_round = False
            for call in decision.tool_calls:
                signature = make_signature(call)
                seen_signatures[signature] = seen_signatures.get(signature, 0) + 1
                if seen_signatures[signature] >= 3:
                    duplicate_round = True

            if duplicate_round:
                trace.system_note = "duplicate_tool_calls_detected"
                self._record_trace(trace)
                working_messages.append({"role": "assistant", "content": decision.text})
                working_messages.append(
                    {
                        "role": "user",
                        "content": "You are repeating the same tool call pattern. Use a different tool, ask the user for missing information, or provide the best final answer.",
                    }
                )
                continue

            if near_limit and decision.tool_calls:
                trace.system_note = "forced_final_answer_near_limit"
                self._record_trace(trace)
                working_messages.append({"role": "assistant", "content": decision.text or ""})
                working_messages.append(
                    {
                        "role": "user",
                        "content": "You are approaching the maximum number of reasoning steps. You MUST now provide a complete final answer. Do NOT call any more tools.",
                    }
                )
                continue

            tool_results = await self._tool_executor.execute(decision.tool_calls)
            tools_executed = True
            # ===== P1-2：CostGuard 消耗记账 =====
            self._cost_guard.iterations = iteration
            self._cost_guard.tool_calls_used += len(decision.tool_calls)
            trace.tool_results = tool_results
            self._record_trace(trace)

            confirmation_required = [r for r in tool_results if r.get("requires_confirmation")]
            if confirmation_required:
                first = confirmation_required[0]
                raise ConfirmationNeeded(str(first.get("content") or "Confirmation required."))

            for result in tool_results:
                if result.get("ask_user"):
                    raise AskUserNeeded(str(result.get("question") or result.get("content") or ""))

            # 将工具结果追加到 working_messages
            append_tool_result_messages(
                working_messages,
                decision,
                tool_results,
                trace.tool_calls,
                decision.text,
                use_native,
                include_error_conditional=False,
            )

        # 超过最大迭代次数
        if best_text:
            yield clean_final_answer(best_text.strip())
        else:
            yield "Stopped after reaching the maximum iteration limit."
