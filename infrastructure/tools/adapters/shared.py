"""Layer 3 共享 function calls — 云合和子智能体都需要的通用基础能力。

这些工具不绑定任何 skill/MCP，属于全局共享的基础设施层。
"""

import datetime
from infrastructure.tools.base import ToolSpec


def get_shared_specs() -> list[ToolSpec]:
    """返回共享工具规格列表。"""
    return [
        ToolSpec(
            name="get_current_time",
            description="获取当前日期和时间。用于时间推理、日期计算等场景。",
            category="system",
            parameters={
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "时区，如 'Asia/Shanghai'，不传则使用系统默认时区",
                    },
                },
            },
            tier="core",
            short_description="获取当前时间",
            disclosure_keywords=["时间", "现在几点", "今天", "日期", "星期", "几号"],
        ),
        ToolSpec(
            name="request_confirmation",
            description="在执行高风险操作前，请求用户确认。",
            category="system",
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "待确认的操作描述",
                    },
                    "risk_level": {
                        "type": "string",
                        "description": "风险级别：low/medium/high",
                        "enum": ["low", "medium", "high"],
                    },
                    "details": {
                        "type": "string",
                        "description": "操作详细说明",
                    },
                },
                "required": ["action"],
            },
            tier="core",
            short_description="请求用户确认操作",
            confirm_required=False,
        ),
    ]


async def get_current_time_handler(arguments: dict) -> dict:
    """获取当前时间。"""
    now = datetime.datetime.now()
    time_str = now.strftime("%Y-%m-%d %H:%M:%S")
    weekday_map = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    weekday = weekday_map[now.weekday()]
    return {
        "content": json_dumps(
            {
                "datetime": time_str,
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H:%M:%S"),
                "weekday": weekday,
                "timestamp": now.timestamp(),
            },
            ensure_ascii=False,
        ),
    }


async def request_confirmation_handler(arguments: dict) -> dict:
    """请求用户确认 — 返回需要确认的信号。"""
    action = arguments.get("action", "操作")
    risk_level = arguments.get("risk_level", "medium")
    details = arguments.get("details", "")
    return {
        "requires_confirmation": True,
        "content": f"⚠️ 请求确认：{action}\n风险级别：{risk_level}\n{details}" if details else f"⚠️ 请求确认：{action}",
    }


def get_shared_handlers() -> dict:
    """返回共享工具处理器映射。"""
    return {
        "get_current_time": get_current_time_handler,
        "request_confirmation": request_confirmation_handler,
    }


import json as _json


def json_dumps(obj, **kwargs):
    return _json.dumps(obj, **kwargs)
