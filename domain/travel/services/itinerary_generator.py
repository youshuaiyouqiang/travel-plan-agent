from __future__ import annotations

import json
import logging
from typing import Any

from domain.travel.intent.travel_schema import TravelIntentType

logger = logging.getLogger(__name__)


class ItineraryGenerator:
    def __init__(
        self,
        *,
        llm: Any,
        session_store: Any,
        dual_memory: Any,
    ) -> None:
        self._llm = llm
        self._session_store = session_store
        self._dual_memory = dual_memory

    async def generate_itinerary(
        self,
        session: Any,
        session_id: str,
        user_id: str,
        ops_result: Any,
    ) -> tuple[str, str]:
        """直通生成行程概览，绕过 LLM 推理。

        返回 (reply, itinerary_id)：
          - reply：要追加到 session 的回复文本
          - itinerary_id：结构化的行程 ID（生成失败时为空字符串），
            供上层 TravelAgent 通过 actions 事件结构化下发，避免前端
            从自由文本正则提取（P1-13）。
        """
        from domain.travel.tools.travel_tools import _generate_itinerary_overview

        itinerary_content = ""
        itinerary_markers = ["第1天", "第一天", "Day 1", "day1", "行程安排", "每日行程", "天：", "日游"]
        confirmation_markers = ["您对这个行程满意吗", "满意的话我将为您生成", "不满意可以告诉我", "是否满意"]
        for turn in reversed(session.turns):
            if turn.role == "assistant" and len(turn.content) > 50:
                is_confirmation_only = any(m in turn.content for m in confirmation_markers)
                if is_confirmation_only and not any(m in turn.content for m in itinerary_markers):
                    continue
                if any(marker in turn.content for marker in itinerary_markers):
                    itinerary_content = turn.content
                    break
                if not itinerary_content:
                    itinerary_content = turn.content

        if not itinerary_content:
            logger.warning("itinerary_confirm: no itinerary content found in session history")
            return "抱歉，未能找到行程内容，请重新描述您的行程需求。", ""

        logger.info("itinerary_confirm: found itinerary content, length=%d", len(itinerary_content))

        destination = ""
        if ops_result and hasattr(ops_result, "detected_destination") and ops_result.detected_destination:
            destination = ops_result.detected_destination
        if not destination:
            dest_markers = ["去", "到", "前往", "飞", "游"]
            for turn in reversed(session.turns):
                if turn.role == "user":
                    for marker in dest_markers:
                        idx = turn.content.find(marker)
                        if idx >= 0:
                            fragment = turn.content[idx + len(marker) : idx + len(marker) + 10].strip()
                            for city in [
                                "北京",
                                "上海",
                                "广州",
                                "深圳",
                                "成都",
                                "重庆",
                                "杭州",
                                "西安",
                                "厦门",
                                "青岛",
                                "三亚",
                                "丽江",
                                "大理",
                                "长沙",
                                "武汉",
                                "南京",
                                "苏州",
                                "昆明",
                                "桂林",
                                "黄山",
                            ]:
                                if city in fragment:
                                    destination = city
                                    break
                            if destination:
                                break
                    if destination:
                        break

        title = f"{destination}行程" if destination else "旅行行程"

        arguments = {
            "title": title,
            "content": itinerary_content,
            "session_id": session_id,
            "destination": destination,
            "user_id": user_id,
        }

        logger.info("itinerary_confirm: calling generate_itinerary_overview with args=%s", arguments)

        try:
            result = await _generate_itinerary_overview(arguments)
        except Exception as e:
            logger.error("itinerary_confirm: generate_itinerary_overview failed: %s", e, exc_info=True)
            return "抱歉，行程概览生成失败，请稍后重试。", ""

        if result.get("is_error"):
            logger.error("itinerary_confirm: tool returned error: %s", result.get("content"))
            return "抱歉，行程概览生成失败，请稍后重试。", ""

        try:
            data = json.loads(result.get("content", "{}"))
            itinerary_id = data.get("itinerary_id", "")
        except (json.JSONDecodeError, ValueError):
            itinerary_id = ""

        if itinerary_id:
            return (
                f"正在为您生成专属行程概览卡片，请稍候...\n\n"
                f"行程概览已生成！itinerary_id: {itinerary_id}\n"
                f"点击下方卡片即可查看完整行程",
                itinerary_id,
            )
        else:
            return "行程概览已生成！点击侧边栏「我的行程」即可查看。", ""

    def build_confirm_context(
        self,
        ops_result: Any,
        session: Any,
        user_id: str = "",
        session_id: str = "",
    ) -> str:
        if not ops_result or not hasattr(ops_result, "intent"):
            logger.debug("itinerary_confirm: no ops_result or no intent attr")
            return ""
        if ops_result.intent != TravelIntentType.ITINERARY_CONFIRM:
            logger.debug("itinerary_confirm: intent=%s, not ITINERARY_CONFIRM", ops_result.intent)
            return ""

        logger.info(
            "itinerary_confirm: detected confirm intent, session has %d turns",
            len(session.turns),
        )

        itinerary_content = ""
        itinerary_markers = ["第1天", "第一天", "Day 1", "day1", "行程安排", "每日行程", "天：", "日游"]
        confirmation_markers = ["您对这个行程满意吗", "满意的话我将为您生成", "不满意可以告诉我", "是否满意"]
        for turn in reversed(session.turns):
            if turn.role == "assistant" and len(turn.content) > 50:
                is_confirmation_only = any(m in turn.content for m in confirmation_markers)
                if is_confirmation_only and not any(m in turn.content for m in itinerary_markers):
                    continue
                if any(marker in turn.content for marker in itinerary_markers):
                    itinerary_content = turn.content
                    break
                if not itinerary_content:
                    itinerary_content = turn.content

        if not itinerary_content:
            logger.warning("itinerary_confirm: no itinerary content found in session history")
            return ""

        logger.info("itinerary_confirm: found itinerary content, length=%d", len(itinerary_content))

        user_id_hint = f"\n- user_id: {user_id}" if user_id else ""
        session_id_hint = f"\n- session_id: {session_id}" if session_id else ""

        return (
            "⚠️ 【行程确认指令】用户已确认满意当前行程方案！\n"
            "你必须立即调用 generate_itinerary_overview 工具来生成行程概览卡片。\n"
            "调用参数（注意：不要传content参数，系统会自动获取行程内容）：\n"
            "- title: 行程标题（如：厦门3日游）\n"
            f"- session_id: {session_id or '当前会话ID'}\n"
            f"- destination: 目的地城市{user_id_hint}\n\n"
            "调用后，将返回的 itinerary_id 告知用户，格式为：itinerary_id: xxxxxxxxxx"
        )
