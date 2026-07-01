from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import settings
from domain.shared.audit.schema import AuditEvent
from domain.shared.audit.sanitizer import sanitize, sanitize_dict

logger = logging.getLogger(__name__)


class AuditLogger:
    def __init__(self, log_dir: Path | None = None) -> None:
        self._log_dir = Path(log_dir) if log_dir else settings.audit_log_dir
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._enabled = settings.audit_enabled
        self._lock = threading.Lock()
        self._current_date: str = ""
        self._log_file: Path | None = None
        self._rotate_if_needed()

    def _rotate_if_needed(self) -> None:
        """按日期轮转：每天一个 audit-YYYY-MM-DD.jsonl 文件。"""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self._current_date:
            self._current_date = today
            self._log_file = self._log_dir / f"audit-{today}.jsonl"

    def log(
        self,
        *,
        event_type: str,
        session_id: str,
        user_id: str,
        trace_id: str = "",
        tool_name: str = "",
        action: str = "",
        input_summary: str = "",
        output_summary: str = "",
        risk_level: str = "low",
        metadata: dict[str, Any] | None = None,
        llm_input: str = "",
        llm_output: str = "",
        duration_ms: int = 0,
    ) -> None:
        if not self._enabled:
            return

        event = AuditEvent(
            event_id=uuid.uuid4().hex[:16],
            event_type=event_type,
            session_id=session_id,
            user_id=user_id,
            trace_id=trace_id,
            tool_name=tool_name,
            action=sanitize(action),
            input_summary=sanitize(input_summary),
            output_summary=sanitize(output_summary),
            risk_level=risk_level,
            metadata=sanitize_dict(metadata or {}),
            llm_input=sanitize(llm_input),
            llm_output=sanitize(llm_output),
            duration_ms=duration_ms,
        )

        self._write(event)
        logger.debug("Audit event: type=%s session=%s trace=%s risk=%s", event_type, session_id, trace_id, risk_level)

    def log_tool_call(
        self,
        *,
        session_id: str,
        user_id: str,
        tool_name: str,
        arguments: dict,
        result_summary: str,
        is_error: bool = False,
        duration_ms: int = 0,
        trace_id: str = "",
        error_traceback: str = "",
    ) -> None:
        risk_level = "high" if tool_name == "run_shell" else ("medium" if is_error else "low")
        metadata: dict[str, Any] = {}
        if error_traceback:
            metadata["error_traceback"] = error_traceback
        self.log(
            event_type="tool_call",
            session_id=session_id,
            user_id=user_id,
            trace_id=trace_id,
            tool_name=tool_name,
            action=f"Called tool: {tool_name}",
            input_summary=str(arguments),
            output_summary=result_summary,
            risk_level=risk_level,
            duration_ms=duration_ms,
            metadata=metadata,
        )

    def log_llm_call(
        self,
        *,
        session_id: str,
        user_id: str,
        model: str,
        system_prompt: str,
        messages: list[dict[str, Any]],
        response: str,
        duration_ms: int,
        tool_calls_mode: bool = False,
        trace_id: str = "",
    ) -> None:
        input_text = json.dumps(
            [{"role": "system", "content": system_prompt}] + messages,
            ensure_ascii=False,
        )
        self.log(
            event_type="llm_call",
            session_id=session_id,
            user_id=user_id,
            trace_id=trace_id,
            tool_name=model,
            action=f"LLM call ({'tool_mode' if tool_calls_mode else 'text_mode'})",
            input_summary=system_prompt,
            output_summary=response,
            risk_level="low",
            llm_input=input_text,
            llm_output=response,
            duration_ms=duration_ms,
            metadata={"model": model, "tool_calls_mode": tool_calls_mode},
        )

    def log_intent_classify(
        self,
        *,
        session_id: str,
        user_id: str,
        message: str,
        intent: str,
        goal: str,
        confidence: float,
        classifier: str,
        raw_llm_output: str = "",
        duration_ms: int = 0,
        trace_id: str = "",
    ) -> None:
        self.log(
            event_type="intent_classify",
            session_id=session_id,
            user_id=user_id,
            trace_id=trace_id,
            action=f"Intent classified: {intent}",
            input_summary=message,
            output_summary=f"intent={intent} goal={goal} confidence={confidence:.2f}",
            risk_level="low",
            llm_output=raw_llm_output,
            duration_ms=duration_ms,
            metadata={
                "classifier": classifier,
                "intent": intent,
                "goal": goal,
                "confidence": confidence,
            },
        )

    def log_emotion_detect(
        self,
        *,
        session_id: str,
        user_id: str,
        message: str,
        emotion: str,
        score: float,
        confidence: float,
        response_style: str,
        raw_llm_output: str = "",
        duration_ms: int = 0,
        trace_id: str = "",
    ) -> None:
        self.log(
            event_type="emotion_detect",
            session_id=session_id,
            user_id=user_id,
            trace_id=trace_id,
            action=f"Emotion detected: {emotion}",
            input_summary=message,
            output_summary=f"emotion={emotion} score={score:.2f} confidence={confidence:.2f} style={response_style}",
            risk_level="low",
            llm_output=raw_llm_output,
            duration_ms=duration_ms,
            metadata={
                "emotion": emotion,
                "score": score,
                "confidence": confidence,
                "response_style": response_style,
            },
        )

    def log_reasoning_step(
        self,
        *,
        session_id: str,
        user_id: str,
        iteration: int,
        decision_type: str,
        text: str,
        tool_calls: list[dict[str, Any]],
        tool_results: list[dict[str, Any]],
        system_note: str = "",
        duration_ms: int = 0,
        trace_id: str = "",
    ) -> None:
        self.log(
            event_type="reasoning_step",
            session_id=session_id,
            user_id=user_id,
            trace_id=trace_id,
            action=f"Reasoning iteration {iteration}: {decision_type}",
            input_summary=f"iteration={iteration} decision_type={decision_type}",
            output_summary=text if text else "",
            risk_level="medium" if decision_type == "tool_calls" else "low",
            duration_ms=duration_ms,
            metadata={
                "iteration": iteration,
                "decision_type": decision_type,
                "system_note": system_note,
                "tool_calls": tool_calls,
                "tool_results": [
                    {
                        "name": r.get("name", ""),
                        "status": r.get("status", ""),
                        "is_error": r.get("is_error", False),
                        "content_preview": str(r.get("content", "")),
                    }
                    for r in tool_results
                ],
            },
        )

    def log_context_built(
        self,
        *,
        session_id: str,
        user_id: str,
        trace_id: str,
        system_prompt: str,
        tools: list[str],
        memory_context: str,
        dual_memory_context: str,
        mcp_context: str,
        profile_context: str,
        emotion_context: str,
        selected_mcp_tools: list[str] | None = None,
        connected_mcp_tools: list[str] | None = None,
    ) -> None:
        """记录注入给 LLM 的完整上下文，便于排查"大模型为何这么决策"。"""
        self.log(
            event_type="context_built",
            session_id=session_id,
            user_id=user_id,
            trace_id=trace_id,
            action="Built prompt context for reasoning",
            input_summary=f"tools={len(tools)} memory={bool(memory_context)} mcp={bool(mcp_context)}",
            output_summary=system_prompt,
            risk_level="low",
            metadata={
                "tools": tools,
                "selected_mcp_tools": selected_mcp_tools or [],
                "connected_mcp_tools": connected_mcp_tools or [],
                "has_memory": bool(memory_context),
                "has_dual_memory": bool(dual_memory_context),
                "has_mcp": bool(mcp_context),
                "has_profile": bool(profile_context),
                "has_emotion": bool(emotion_context),
                "memory_context": memory_context,
                "dual_memory_context": dual_memory_context,
                "mcp_context": mcp_context,
                "profile_context": profile_context,
                "emotion_context": emotion_context,
            },
        )

    def log_session_complete(
        self,
        *,
        session_id: str,
        user_id: str,
        user_message: str,
        reply: str,
        intent: str,
        emotion: str,
        total_duration_ms: int,
        trace_summary: str = "",
        trace_id: str = "",
    ) -> None:
        self.log(
            event_type="session_complete",
            session_id=session_id,
            user_id=user_id,
            trace_id=trace_id,
            action="Session completed",
            input_summary=user_message,
            output_summary=reply,
            risk_level="low",
            duration_ms=total_duration_ms,
            metadata={
                "intent": intent,
                "emotion": emotion,
                "trace_summary": trace_summary,
            },
        )

    def log_api_boundary(
        self,
        *,
        session_id: str,
        user_id: str,
        trace_id: str,
        direction: str,
        endpoint: str,
        method: str,
        payload: str,
        status_code: int = 0,
        duration_ms: int = 0,
        agent_id: str = "",
    ) -> None:
        """记录 API 边界的原始请求/响应全文。direction: request | response。"""
        self.log(
            event_type=f"api_{direction}",
            session_id=session_id,
            user_id=user_id,
            trace_id=trace_id,
            action=f"API {direction}: {method} {endpoint}",
            input_summary=payload if direction == "request" else "",
            output_summary=payload if direction == "response" else "",
            risk_level="low",
            duration_ms=duration_ms,
            metadata={
                "endpoint": endpoint,
                "method": method,
                "status_code": status_code,
                "agent_id": agent_id,
            },
        )

    def _write(self, event: AuditEvent) -> None:
        line = json.dumps(asdict(event), ensure_ascii=False)
        try:
            with self._lock:
                self._rotate_if_needed()
                with open(self._log_file, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
        except Exception:
            logger.warning("Failed to write audit event", exc_info=True)
