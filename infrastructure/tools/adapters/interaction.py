from __future__ import annotations

from .base import ToolHandler, ToolSpec, bind_tool

async def _ask_user(arguments: dict) -> dict:
    question = str(arguments.get("question","")).strip()
    if not question:
        return {"is_error":True,"content":"missing question"}
    return {
        "content": question,
        "ask_user": True,
        "question":question,
    }

def get_interaction_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="ask_user",
            description="向用户提问以获取缺失的关键信息。仅在用户消息完全缺少目的地、日期等关键信息时使用，如果用户已提供则不要调用",
            category="Ask User",
            parameters={
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "要问用户的问题"},
                },
                "required": ["question"],
            },
        )
    ]


def get_interaction_handlers() -> dict[str, ToolHandler]:
    return {"ask_user": _ask_user}


def build_interaction_tools() -> list:
    specs = {spec.name: spec for spec in get_interaction_specs()}
    return [bind_tool(specs[name], handler) for name, handler in get_interaction_handlers().items()]