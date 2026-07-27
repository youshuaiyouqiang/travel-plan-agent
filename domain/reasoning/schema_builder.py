"""工具 schema 构建与状态文本工具。

P6.1 从 ``engine.py`` 拆出：``build_func_def`` 将 ToolSpec 转为 LLM 函数定义，
``TOOL_STATUS_MAP`` 提供工具执行状态的中文友好提示。
"""

from __future__ import annotations

from typing import Any


def build_func_def(spec: Any) -> dict[str, Any]:
    """构建单个工具的 function definition（OpenAI tools 格式）。"""
    func_def: dict[str, Any] = {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
        },
    }
    if hasattr(spec, "parameters") and spec.parameters:
        func_def["function"]["parameters"] = spec.parameters
    else:
        func_def["function"]["parameters"] = {
            "type": "object",
            "properties": {},
        }
    return func_def


# 工具名称到中文友好提示的映射（流式推理时作为 __status__ 事件发送给前端）
TOOL_STATUS_MAP: dict[str, str] = {
    "fliggy_search_flight": "正在搜索机票...",
    "fliggy_search_train": "正在搜索火车票...",
    "fliggy_search_hotel": "正在搜索酒店...",
    "amap_search_poi": "正在搜索景点...",
    "amap_get_weather": "正在查询天气...",
    "amap_route_plan": "正在规划路线...",
    "save_itinerary": "正在保存行程...",
    "generate_itinerary_overview": "正在生成行程概览...",
    "ask_user": "需要更多信息",
}


def tool_status_text(name: str) -> str:
    """返回工具执行状态的中文提示；未知工具返回通用提示。"""
    return TOOL_STATUS_MAP.get(name, f"正在执行 {name}...")
