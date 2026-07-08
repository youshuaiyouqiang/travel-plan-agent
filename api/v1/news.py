from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Request

from application.dto.request import NewsFavoriteRequest
from application.exceptions import UnauthorizedException, InternalException

logger = logging.getLogger(__name__)

router = APIRouter(tags=["news"])


@router.get("/trending")
async def trending(refresh: bool = False) -> dict:
    from application.trending.manager import get_trending_travel

    items = await get_trending_travel(refresh=refresh)
    return {"items": items}


@router.get("/favorites")
async def list_news_favorites(request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    from infrastructure.persistence.database import get_connection

    conn = get_connection()
    rows = conn.execute(
        "SELECT id, title, summary, content, url, source, tag, created_at "
        "FROM news_favorites WHERE user_id = ? ORDER BY id DESC",
        (user_id,),
    ).fetchall()
    favorites = [
        {
            "id": r["id"],
            "title": r["title"],
            "summary": r["summary"],
            "content": r["content"],
            "url": r["url"],
            "source": r["source"],
            "tag": r["tag"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]
    return {"favorites": favorites}


@router.post("/favorites")
async def add_news_favorite(req: NewsFavoriteRequest, request: Request) -> dict:
    """收藏一条新闻，同时写入 short_term_memories 让智能体能检索到。"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    from infrastructure.persistence.database import get_connection

    now = datetime.utcnow().isoformat()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO news_favorites (user_id, title, summary, content, url, source, tag, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, req.title, req.summary, req.content, req.url, req.source, req.tag, now),
        )
        # 同步写入 short_term_memories，让 agent 在对话中能引用用户关注的新闻
        memory_content = f"用户收藏的新闻：{req.title}。{req.content or req.summary}"
        conn.execute(
            "INSERT INTO short_term_memories (user_id, category, content, experience_tag, created_at) "
            "VALUES (?, 'news', ?, ?, ?)",
            (user_id, memory_content, req.tag or "news"),
        )
        conn.commit()
    except Exception as e:
        # UNIQUE 约束冲突 = 已收藏，幂等返回成功
        if "UNIQUE" in str(e) or "unique" in str(e):
            return {"status": "already_favorited", "title": req.title}
        logger.error("Add news favorite failed: %s", e)
        raise InternalException("收藏失败")
    return {"status": "ok", "title": req.title}


@router.delete("/favorites/{favorite_id}")
async def delete_news_favorite(favorite_id: int, request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    from infrastructure.persistence.database import get_connection

    conn = get_connection()
    conn.execute(
        "DELETE FROM news_favorites WHERE id = ? AND user_id = ?",
        (favorite_id, user_id),
    )
    conn.commit()
    return {"detail": "已取消收藏"}
