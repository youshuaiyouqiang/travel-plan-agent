"""working_messages 构建与工具结果消息追加（P6.2 提取自 engine.py）。

纯函数模块，不依赖 ``ReasoningEngine`` 实例状态。``run`` 和 ``run_stream``
共用这些函数构建对话上下文，避免双份实现产生行为漂移。
"""

from __future__ import annotations

import json
from typing import Any

from domain.shared.types import Decision

# 最近 3 轮对话（user+assistant 各一条）作为上下文，防止 LLM 遗忘关键信息。
MAX_HISTORY_TURNS: int = 6


def build_working_messages(
    user_message: str,
    conversation_history: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """截取最近对话历史 + 当前用户消息，构建 working_messages。

    保留最近 3 轮对话（6 条消息）作为上下文，防止 LLM 遗忘关键信息。
    仅接受 ``user`` / ``assistant`` 角色且内容非空的轮次。
    """
    messages: list[dict[str, str]] = []
    if conversation_history:
        recent = conversation_history[-MAX_HISTORY_TURNS:]
        for turn in recent:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})
    return messages


def append_tool_result_messages(
    working_messages: list[dict[str, Any]],
    decision: Decision,
    tool_results: list[dict],
    trace_tool_calls: list[dict[str, Any]],
    decision_text: str,
    use_native: bool,
    *,
    include_error_conditional: bool = True,
) -> None:
    """将工具执行结果追加到 working_messages（run / run_stream 共用）。

    native 模式：追加 assistant tool_calls + tool 结果 + user 提示。
    非 native 模式：追加 assistant JSON payload + 结果摘要；
    若 ``include_error_conditional`` 为 True（run 路径），额外根据结果
    是否含错误追加不同的 user 提示。

    ``trace_tool_calls`` 与 ``decision_text`` 是 ``TraceStep.tool_calls`` 和
    ``decision.text`` 的快照，作为参数显式传入，避免本模块反向依赖
    ``TraceStep`` 类型。
    """
    if use_native:
        assistant_msg: dict[str, Any] = {"role": "assistant", "content": decision_text or None}
        assistant_msg["tool_calls"] = [
            {
                "id": call.call_id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(call.arguments, ensure_ascii=False),
                },
            }
            for call in decision.tool_calls
        ]
        working_messages.append(assistant_msg)
        for call, result in zip(decision.tool_calls, tool_results):
            tool_content = result.get("content", "")
            if isinstance(tool_content, dict):
                tool_content = json.dumps(tool_content, ensure_ascii=False)
            working_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.call_id,
                    "content": str(tool_content)[:4000],
                }
            )
        working_messages.append(
            {
                "role": "user",
                "content": (
                    "Use the tool results above to continue. "
                    "If they are sufficient, reply with a plain-text final answer for the user. "
                    "Only call new tools if you still need different information. "
                    "Do not repeat the same tool calls."
                ),
            }
        )
    else:
        assistant_payload = {
            "tool_calls": trace_tool_calls,
            "text": decision_text,
        }
        working_messages.append(
            {"role": "assistant", "content": json.dumps(assistant_payload, ensure_ascii=False)}
        )
        result_summaries = []
        for r in tool_results:
            name = r.get("name", "unknown")
            content = r.get("content", "")
            is_error = r.get("is_error", False)
            tag = "ERROR" if is_error else "OK"
            result_summaries.append(f"[{name}] {tag}: {content[:2000]}")
        working_messages.append(
            {
                "role": "user",
                "content": "Tool results:\n" + "\n---\n".join(result_summaries),
            }
        )
        if include_error_conditional:
            if all(
                not result.get("is_error", False) and not result.get("requires_confirmation")
                for result in tool_results
            ):
                working_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Use the tool results above to continue. "
                            "If they are sufficient, reply with a plain-text final answer for the user. "
                            "Only return new tool_calls JSON if you still need different information or a different action. "
                            "Do not repeat the same tool_calls JSON."
                        ),
                    }
                )
            else:
                working_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "The tool results contain errors, missing data, or confirmation requests. "
                            "If you can recover, call a different tool or ask the user for the missing information. "
                            "If the results are already sufficient, answer plainly. "
                            "Do not repeat the same tool_calls JSON."
                        ),
                    }
                )
