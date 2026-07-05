from __future__ import annotations

import logging
from typing import Any

from domain.memory.manager import DualLayerMemoryManager
from domain.reasoning.engine import ReasoningEngine
from domain.travel.intent.travel_classifier import TravelIntentResult
from domain.travel.intent.travel_schema import TravelIntentType

logger = logging.getLogger(__name__)


class CacheManager:
    _CATEGORY_LABELS = {
        "flight": "机票",
        "train": "高铁/火车",
        "hotel": "酒店",
        "poi": "景点",
        "weather": "天气",
        "route": "路线",
        "keyword_search": "关键词搜索",
    }

    _FIELD_LABELS = {
        "destination": "目的地",
        "origin": "出发地",
        "duration": "旅行天数",
        "dates": "出发日期",
        "budget": "预算",
    }

    _CORE_CHANGE_KEYWORDS = [
        "出发地",
        "从哪",
        "从哪出发",
        "从哪里",
        "换个出发",
        "目的地",
        "去哪",
        "去哪里",
        "换个目的",
        "改去",
        "出发日期",
        "出发时间",
        "改日期",
        "换个日期",
        "改时间",
        "返程",
        "回程",
        "返回时间",
        "改返程",
    ]

    _LOCAL_CHANGE_KEYWORDS = [
        "换个酒店",
        "换酒店",
        "不住",
        "酒店不好",
        "换个景点",
        "换景点",
        "不要这个景点",
        "景点不好",
        "行程太紧",
        "太赶",
        "太累",
        "轻松一点",
        "换个餐厅",
        "换餐厅",
        "不想吃",
    ]

    def __init__(
        self,
        *,
        reasoning: ReasoningEngine,
        dual_memory: DualLayerMemoryManager,
    ) -> None:
        self._reasoning = reasoning
        self._dual_memory = dual_memory

    def build_cached_context(self, task: Any) -> str:
        cached = task.get_cached_results()
        if not cached:
            return ""
        parts: list[str] = []
        for category, info in cached.items():
            label = self._CATEGORY_LABELS.get(category, category)
            tool_name = info.get("tool_name", "")
            result = info.get("result", "")
            if not result:
                continue
            truncated = result[:2000] if len(result) > 2000 else result
            parts.append(f"### {label}（来自 {tool_name}）\n{truncated}")
        if not parts:
            return ""
        header = (
            "以下数据是之前搜索获取的，仍然有效。"
            "如果用户只是修改景点、酒店、行程安排等局部内容，请直接使用这些数据，不要重复调用相同的搜索工具。"
            "只有当用户改变了出发地、目的地、出发日期、返程日期等核心参数时，才需要重新搜索对应类别的数据。"
        )
        return header + "\n\n" + "\n\n".join(parts)

    def handle_invalidation(
        self,
        task: Any,
        message: str,
        ops_result: TravelIntentResult | None,
    ) -> None:
        """基于 LLM 意图分类结果决定缓存策略，关键词匹配作为兜底。"""
        cached = task.get_cached_results()
        if not cached:
            return

        # ★ 优先使用 LLM 分类结果中的 modification_scope
        if ops_result and ops_result.intent == TravelIntentType.ITINERARY_ADJUST and ops_result.modification_scope:
            scope = ops_result.modification_scope
            categories = ops_result.affected_categories

            if scope == "full_research":
                task.invalidate_cache()
                logger.info("Cache fully invalidated (LLM classified: full_research) for session %s", task.session_id)
                return
            elif scope == "partial_research" and categories:
                for cat in categories:
                    task.invalidate_cache(cat)
                logger.info(
                    "Cache partial invalidated: %s (LLM classified) for session %s", categories, task.session_id
                )
                return
            elif scope == "local_reorder":
                # 缓存不动，LLM 纯重排
                logger.info("Cache kept (LLM classified: local_reorder) for session %s", task.session_id)
                return

        # ★ 兜底：LLM 分类没有 modification_scope 时，走关键词匹配
        is_core_change = any(kw in message for kw in self._CORE_CHANGE_KEYWORDS)
        if is_core_change:
            task.invalidate_cache()
            logger.info("Cache fully invalidated: core params changed for session %s", task.session_id)
            return
        is_hotel_change = any(kw in message for kw in ["换酒店", "换个酒店", "不住", "酒店不好", "酒店不行"])
        is_poi_change = any(kw in message for kw in ["换景点", "换个景点", "不要这个景点", "景点不好", "景点不行"])
        if is_hotel_change:
            task.invalidate_cache("hotel")
            logger.info("Cache partial invalidation: hotel cache cleared for session %s", task.session_id)
        if is_poi_change:
            task.invalidate_cache("poi")
            logger.info("Cache partial invalidation: poi cache cleared for session %s", task.session_id)

    def cache_results_from_trace(self, task: Any) -> None:
        if not self._reasoning.last_trace:
            return
        for step in self._reasoning.last_trace:
            if not step.tool_results:
                continue
            for call_info, result_info in zip(step.tool_calls, step.tool_results):
                name = call_info.get("name", "")
                args = call_info.get("arguments", {})
                content = str(result_info.get("content", ""))
                is_error = result_info.get("is_error", False)
                if name and content and not is_error:
                    task.cache_tool_result(name, args, content[:4000])
