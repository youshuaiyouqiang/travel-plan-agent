from __future__ import annotations

import json
import logging

from .base import ToolHandler, ToolSpec, bind_tool

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

    if not user_id and session_id:
        from infra.db import get_connection
        conn = get_connection()
        row = conn.execute(
            "SELECT user_id FROM tasks WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row and row["user_id"]:
            user_id = row["user_id"]
            logger.info("generate_itinerary_overview: user_id resolved from task store: %s", user_id)

    if not content and session_id:
        from infra.db import get_connection
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

    if not content:
        return {"is_error": True, "content": "missing itinerary content: please provide content or session_id"}

    from core.itinerary.parser import ItineraryParser
    from core.itinerary.repository import ItineraryRepository

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
            },
            ensure_ascii=False,
        ),
    }


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
            description="将文字版行程解析为结构化数据并生成行程概览，返回itinerary_id供前端跳转。content参数可选，如果不传则自动从会话历史中获取行程内容。",
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
