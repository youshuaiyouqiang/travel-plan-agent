from __future__ import annotations

import logging
import traceback as traceback_mod
from tools.policy import ToolPolicy,PolicyMode
from tools.registry import ToolRegistry
from core.types import ToolCall

logger = logging.getLogger(__name__)

class ToolExecutor:
    def __init__(self, *, registry: ToolRegistry, policy: ToolPolicy, audit_logger=None) -> None:
        self._registry = registry
        self._policy = policy
        self._audit_logger = audit_logger
        self._audit_session_id: str = ""
        self._audit_user_id: str = ""
        self._audit_trace_id: str = ""

    def set_audit_context(self, *, session_id: str, user_id: str, trace_id: str = "") -> None:
        self._audit_session_id = session_id
        self._audit_user_id = user_id
        self._audit_trace_id = trace_id

    async def execute(self, calls: list[ToolCall]) -> list[dict]:
        results: list[dict] = []
        for call in calls:
            decision = self._policy.check(call.name, call.arguments)
            logger.debug("Tool check: name=%s decision=%s", call.name, decision.decision.value)
            if decision.decision == PolicyMode.DENY:
                results.append(
                    {
                        "tool_use_id": call.call_id,
                        "name": call.name,
                        "status": "denied",
                        "is_error": True,
                        "content": f"Policy denied: {decision.reason}",
                    }
                )
                logger.warning("Tool denied by policy: name=%s", call.name)
                continue
            if decision.decision == PolicyMode.CONFIRM:
                results.append(
                    {
                        "tool_use_id": call.call_id,
                        "name": call.name,
                        "status": "needs_confirmation",
                        "is_error": False,
                        "requires_confirmation": True,
                        "content": f"Confirmation required: {decision.reason}",
                    }
                )
                logger.info("Tool requires confirmation: name=%s", call.name)
                continue

            if not self._registry.has(call.name):
                results.append(
                    {
                        "tool_use_id": call.call_id,
                        "name": call.name,
                        "status": "unknown_tool",
                        "is_error": True,
                        "content": f"Unknown tool: {call.name}",
                    }
                )
                logger.warning("Tool not found: name=%s", call.name)
                continue

            tool = self._registry.get(call.name)
            logger.info(
                "Tool executing: name=%s args=%s",
                call.name,
                str(call.arguments)[:300],
            )
            tb_text = ""
            try:
                payload = await tool.handler(call.arguments)
            except Exception as exc:
                tb_text = traceback_mod.format_exc()
                logger.exception("Tool execution failed: name=%s error=%s", call.name, exc)
                payload = {
                    "is_error": True,
                    "content": f"Tool execution failed: {type(exc).__name__}: {exc}",
                }
            result = {
                "tool_use_id": call.call_id,
                "name": call.name,
                "status": "error" if bool(payload.get("is_error", False)) else "ok",
                "is_error": bool(payload.get("is_error", False)),
                "content": payload.get("content", ""),
            }
            for key, value in payload.items():
                if key in {"tool_use_id", "name", "is_error", "content"}:
                    continue
                result[key] = value
            results.append(result)
            content_preview = str(result["content"])[:300]
            if result["is_error"]:
                logger.warning("Tool FAILED: name=%s result=%s", call.name, content_preview)
            else:
                logger.info("Tool OK: name=%s result=%s", call.name, content_preview)
            if self._audit_logger:
                self._audit_logger.log_tool_call(
                    session_id=self._audit_session_id,
                    user_id=self._audit_user_id,
                    trace_id=self._audit_trace_id,
                    tool_name=call.name,
                    arguments=call.arguments,
                    result_summary=str(payload.get("content", "")),
                    is_error=result.get("is_error", False),
                    error_traceback=tb_text,
                )
        return results


