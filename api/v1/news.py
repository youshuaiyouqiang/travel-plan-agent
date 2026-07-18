from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Request

from application.dto.request import NewsFavoriteRequest
from application.exceptions import InternalException, NotFoundException, UnauthorizedException
from application.news.models import NewsItem

logger = logging.getLogger(__name__)

router = APIRouter(tags=["news"])


@router.get("/trending")
async def trending(refresh: bool = False) -> dict:
    from application.trending.manager import get_trending_travel

    items = await get_trending_travel(refresh=refresh)
    return {"items": items}


@router.get("/hotspots")
async def list_hotspots(request: Request) -> dict:
    """列出当前热点池（只读缓存，严禁发起外部抓取）。

    业务红线：
    - ``GET /hotspots`` 只读缓存；外部抓取由定时器与
      ``HotspotService.refresh`` 负责。
    - 未认证返回 401；缓存未配置时返回空列表。
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    service = getattr(request.app.state, "hotspot_service", None)
    if service is None:
        return {"items": []}
    items = await service.list_current()
    return {"items": [_news_item_to_dict(item) for item in items]}


@router.post("/hotspots/{news_id}/analysis-sessions")
async def create_analysis_session(news_id: str, request: Request) -> dict:
    """为指定热点创建 ``news_analysis_locked`` 会话。

    业务红线：
    - 锁定 Agent 固定为 ``news``；不接受客户端传入的 ``locked_agent_id``。
    - 锚点 ``news_id`` 必须存在于热点池缓存中；不存在统一返回 404。
    - 会话由 ``SessionService.create`` 在内部创建，不经过用户 API 校验。
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    hotspot_service = getattr(request.app.state, "hotspot_service", None)
    session_service = getattr(request.app.state, "session_service", None)
    if hotspot_service is None or session_service is None:
        raise InternalException("新闻研判服务未配置")

    news_item = hotspot_service.repository.get_by_id(news_id)
    if news_item is None:
        raise NotFoundException("news", news_id)

    record = session_service.create(
        user_id=user_id,
        mode="news_analysis_locked",
        locked_agent_id="news",
        news_id=news_id,
    )
    return {
        "session_id": record.session_id,
        "mode": record.mode,
        "locked_agent_id": record.locked_agent_id,
        "news_id": record.news_id,
        "anchor": _news_item_to_dict(news_item),
    }


def _news_item_to_dict(item: NewsItem) -> dict:
    """将 ``NewsItem`` 序列化为响应字典；不包含新闻全文。"""
    return {
        "id": item.id,
        "title": item.title,
        "source": item.source,
        "url": item.url,
        "summary": item.summary,
        "published_at": item.published_at,
    }


@router.get("/favorites")
async def list_news_favorites(request: Request) -> dict:
    """列出当前用户的新闻收藏（仅元数据，不含全文）。"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    from infrastructure.persistence.database import get_connection

    conn = get_connection()
    rows = conn.execute(
        "SELECT id, title, summary, url, source, tag, created_at "
        "FROM news_favorites WHERE user_id = ? ORDER BY id DESC",
        (user_id,),
    ).fetchall()
    favorites = [
        {
            "id": r["id"],
            "title": r["title"],
            "summary": r["summary"],
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
    """收藏一条新闻（仅元数据；不写入新闻全文，不注入短期记忆）。"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    from infrastructure.persistence.database import get_connection

    now = datetime.utcnow().isoformat()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO news_favorites (user_id, title, summary, url, source, tag, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, req.title, req.summary, req.url, req.source, req.tag, now),
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
