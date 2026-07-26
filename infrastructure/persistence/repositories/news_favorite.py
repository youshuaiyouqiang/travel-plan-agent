"""``NewsFavoriteRepositoryPort`` 的 SQLite 实现。

P3.3b 将原 ``api/v1/news.py`` 中 favorites 路由的裸 SQL 收敛到此：
- ``list_news_favorites`` — ``SELECT ... FROM news_favorites WHERE user_id = ?``
- ``add_news_favorite`` — ``INSERT INTO news_favorites ...``（UNIQUE 冲突幂等）
- ``delete_news_favorite`` — ``DELETE FROM news_favorites WHERE id = ? AND user_id = ?``

SQL 文本、参数化方式与幂等语义完全保留；不改变表结构或迁移版本。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from infrastructure.persistence.connection import get_connection

logger = logging.getLogger(__name__)


class SqliteNewsFavoriteRepository:
    """``NewsFavoriteRepositoryPort`` 的 SQLite 实现。

    无状态，可单例复用。通过 ``get_connection()`` 获取当前线程连接，
    支持测试隔离的 ``reset_connection()`` 模式。
    """

    def list_by_user(self, user_id: str) -> list[dict[str, Any]]:
        """列出用户全部新闻收藏（仅元数据，不含全文），按 id 倒序。"""
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, title, summary, url, source, tag, created_at "
            "FROM news_favorites WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        ).fetchall()
        return [
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

    def add(
        self,
        *,
        user_id: str,
        title: str,
        summary: str,
        url: str,
        source: str,
        tag: str,
    ) -> bool:
        """插入收藏行；UNIQUE(user_id, title) 冲突返回 False（幂等），新插入返回 True。"""
        now = datetime.utcnow().isoformat()
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO news_favorites (user_id, title, summary, url, source, tag, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, title, summary, url, source, tag, now),
            )
            conn.commit()
            return True
        except Exception as e:
            # UNIQUE 约束冲突 = 已收藏，幂等返回 False
            if "UNIQUE" in str(e) or "unique" in str(e):
                return False
            logger.error("Add news favorite failed: %s", e)
            raise

    def delete(self, *, favorite_id: int, user_id: str) -> bool:
        """删除收藏；只命中属于 ``user_id`` 的行。返回是否实际删除。"""
        conn = get_connection()
        cursor = conn.execute(
            "DELETE FROM news_favorites WHERE id = ? AND user_id = ?",
            (favorite_id, user_id),
        )
        conn.commit()
        return cursor.rowcount > 0


__all__ = ["SqliteNewsFavoriteRepository"]
