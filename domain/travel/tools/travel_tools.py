from __future__ import annotations

import json
import logging

from infrastructure.tools.base import ToolHandler, ToolSpec, bind_tool

logger = logging.getLogger(__name__)


async def _save_itinerary(arguments: dict) -> dict:
    title = str(arguments.get("title", "旅行行程")).strip()
    content = str(arguments.get("content", "")).strip()
    if not content:
        return {"is_error": True, "content": "missing itinerary content"}
    from config import settings
    from pathlib import Path
    path = settings.workspace / "itineraries" / f"{title}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {"content": f"wrote {len(content)} chars to itineraries/{title}.md"}


async def _generate_itinerary_overview(arguments: dict) -> dict:
    title = str(arguments.get("title", "旅行行程")).strip()
    content = str(arguments.get("content", "")).strip()
    destination = str(arguments.get("destination", "")).strip()
    user_id = str(arguments.get("user_id", "")).strip()
    session_id = str(arguments.get("session_id", "")).strip()
    start_date = str(arguments.get("start_date", "")).strip()
    end_date = str(arguments.get("end_date", "")).strip()
    plan_type = str(arguments.get("plan_type", "")).strip()  # sightseeing / budget / ""

    if not user_id and session_id:
        from infrastructure.persistence.database import get_connection
        conn = get_connection()
        row = conn.execute(
            "SELECT user_id FROM tasks WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row and row["user_id"]:
            user_id = row["user_id"]
            logger.info("generate_itinerary_overview: user_id resolved from task store: %s", user_id)

    if not content and session_id:
        from infrastructure.persistence.database import get_connection
        conn = get_connection()
        rows = conn.execute(
            "SELECT role, content FROM session_turns WHERE session_id = ? ORDER BY turn_index DESC",
            (session_id,),
        ).fetchall()
        itinerary_markers = ["第1天", "第一天", "Day 1", "行程安排", "每日行程"]
        for row in rows:
            if row["role"] == "assistant" and len(row["content"]) > 100:
                if any(marker in row["content"] for marker in itinerary_markers):
                    content = row["content"]
                    logger.info("generate_itinerary_overview: content resolved from session history, length=%d", len(content))
                    break
        if not content:
            for row in rows:
                if row["role"] == "assistant" and len(row["content"]) > 200:
                    content = row["content"]
                    logger.info("generate_itinerary_overview: fallback to longest assistant turn, length=%d", len(content))
                    break

    # 如果指定了 plan_type，从 content 中提取对应方案的内容
    if plan_type and content:
        content = _extract_plan_content(content, plan_type)

    if not content:
        return {"is_error": True, "content": "missing itinerary content: please provide content or session_id"}

    from domain.travel.itinerary.parser import ItineraryParser
    from domain.travel.itinerary.repository import ItineraryRepository

    parser = ItineraryParser()
    try:
        itinerary = await parser.parse(
            raw_content=content,
            user_id=user_id,
            session_id=session_id,
        )
    except Exception as e:
        logger.warning("LLM parsing failed, falling back to simple parser: %s", e)
        itinerary = ItineraryParser.parse_simple(content)
        if itinerary:
            itinerary.user_id = user_id
            itinerary.session_id = session_id

    if not itinerary:
        return {"is_error": True, "content": "failed to parse itinerary"}

    if title:
        itinerary.title = title
    if destination:
        itinerary.destination = destination
    if start_date:
        itinerary.start_date = start_date
    if end_date:
        itinerary.end_date = end_date

    repo = ItineraryRepository()
    saved = repo.save_full_itinerary(itinerary)

    # 如果有 plan_type，保存多方案元数据到 itinerary 的 metadata
    if plan_type:
        try:
            from infrastructure.persistence.database import get_connection
            conn = get_connection()
            conn.execute(
                "UPDATE itineraries SET raw_content = ? WHERE id = ?",
                (content[:5000], saved.id),
            )
            conn.commit()
        except Exception:
            logger.warning("Failed to update itinerary with plan metadata")

    return {
        "is_error": False,
        "content": json.dumps(
            {
                "message": "行程概览已生成",
                "itinerary_id": saved.id,
                "title": saved.title,
                "destination": saved.destination,
                "days_count": len(saved.days),
                "activities_count": sum(len(d.activities) for d in saved.days),
                "plan_type": plan_type or "single",
            },
            ensure_ascii=False,
        ),
    }


def _extract_plan_content(content: str, plan_type: str) -> str:
    """从多方案文本中提取指定方案的内容。

    plan_type: sightseeing (方案一/景点打卡型) 或 budget (方案二/经济实惠型)
    如果无法提取，返回原文。
    """
    if not plan_type:
        return content

    import re

    # 定义方案标记模式
    plan_markers = {
        "sightseeing": [
            r"##\s*📋\s*方案一[：:]\s*景点打卡型",
            r"##\s*方案一[：:]\s*景点打卡型",
            r"###\s*方案一[：:]\s*景点打卡型",
            r"📋\s*方案一",
        ],
        "budget": [
            r"##\s*📋\s*方案二[：:]\s*经济实惠型",
            r"##\s*方案二[：:]\s*经济实惠型",
            r"###\s*方案二[：:]\s*经济实惠型",
            r"📋\s*方案二",
        ],
    }

    next_plan_markers = [
        r"##\s*📋\s*方案二",
        r"##\s*方案二",
        r"##\s*🏆\s*推荐方案",
        r"##\s*推荐方案",
        r"<!--MULTI_PLAN:",
    ]

    markers = plan_markers.get(plan_type, [])
    start_idx = -1

    for marker in markers:
        match = re.search(marker, content)
        if match:
            start_idx = match.start()
            break

    if start_idx == -1:
        logger.info("extract_plan_content: no marker found for plan_type=%s, returning full content", plan_type)
        return content

    # 查找下一个方案的起始位置（截取当前方案内容）
    end_idx = len(content)
    for nm in next_plan_markers:
        match = re.search(nm, content[start_idx + 10:])
        if match:
            candidate_end = start_idx + 10 + match.start()
            if candidate_end < end_idx:
                end_idx = candidate_end

    extracted = content[start_idx:end_idx].strip()
    logger.info("extract_plan_content: extracted %d chars for plan_type=%s", len(extracted), plan_type)

    # 如果提取的内容太短（<200字符），可能是提取失败，返回原文
    if len(extracted) < 200:
        return content

    return extracted


def get_travel_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="save_itinerary",
            description="保存旅行行程到文件",
            category="File System",
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "行程标题"},
                    "content": {"type": "string", "description": "行程内容,markdown格式"},
                },
                "required": ["title", "content"],
            },
        ),
        ToolSpec(
            name="generate_itinerary_overview",
            description="将文字版行程解析为结构化数据并生成行程概览，返回itinerary_id供前端跳转。支持多方案：传入plan_type参数（sightseeing/budget）来指定生成哪个方案的概览。content参数可选，如果不传则自动从会话历史中获取行程内容。",
            category="Travel",
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "行程标题，如：成都5日游"},
                    "content": {"type": "string", "description": "行程的完整文字内容，markdown格式。可以不传，系统会自动从会话历史获取"},
                    "destination": {"type": "string", "description": "目的地城市"},
                    "user_id": {"type": "string", "description": "用户ID"},
                    "session_id": {"type": "string", "description": "会话ID（必传，用于获取行程内容和关联用户）"},
                    "start_date": {"type": "string", "description": "出发日期，格式YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "返回日期，格式YYYY-MM-DD"},
                    "plan_type": {
                        "type": "string",
                        "enum": ["sightseeing", "budget"],
                        "description": "方案类型：sightseeing(景点打卡型/方案一) 或 budget(经济实惠型/方案二)。多方案下必传",
                    },
                },
                "required": ["title", "session_id"],
            },
        ),
    ]


def get_travel_handlers() -> dict[str, ToolHandler]:
    return {
        "save_itinerary": _save_itinerary,
        "generate_itinerary_overview": _generate_itinerary_overview,
    }
