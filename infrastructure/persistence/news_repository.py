"""Task 1 — 新闻来源治理持久化层。

设计要点：
- 所有 SQL 使用 ``?`` 参数绑定；表名来自代码内硬编码白名单。
- ``Source`` / ``SourceAudit`` 与数据库行之间的双向转换集中在此层。
- 不保存新闻全文；仅保存来源元数据与审核审计记录。
"""

from __future__ import annotations

from typing import Any

from application.news.models import Source, SourceAudit, SourceStatus
from infrastructure.persistence.database import get_connection


def _row_to_source(row: Any) -> Source:
    return Source(
        id=row["id"],
        name=row["name"],
        domain=row["domain"],
        tier=row["tier"],
        status=row["status"],
        ai_score=row["ai_score"],
        ai_reason=row["ai_reason"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_audit(row: Any) -> SourceAudit:
    return SourceAudit(
        id=row["id"],
        source_id=row["source_id"],
        admin_id=row["admin_id"],
        previous_status=row["previous_status"],
        decision=row["decision"],
        reason=row["reason"],
        created_at=row["created_at"],
    )


class NewsSourceRepository:
    """新闻来源与审核审计的 SQLite 持久化仓库。"""

    def insert_source(self, source: Source) -> None:
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO news_sources "
                "(id, name, domain, tier, status, ai_score, ai_reason, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    source.id,
                    source.name,
                    source.domain,
                    source.tier,
                    source.status,
                    source.ai_score,
                    source.ai_reason,
                    source.created_at,
                    source.updated_at,
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def get_source_by_id(self, source_id: str) -> Source | None:
        conn = get_connection()
        row = conn.execute(
            "SELECT id, name, domain, tier, status, ai_score, ai_reason, created_at, updated_at "
            "FROM news_sources WHERE id = ?",
            (source_id,),
        ).fetchone()
        return _row_to_source(row) if row else None

    def get_source_by_domain(self, domain: str) -> Source | None:
        conn = get_connection()
        row = conn.execute(
            "SELECT id, name, domain, tier, status, ai_score, ai_reason, created_at, updated_at "
            "FROM news_sources WHERE domain = ?",
            (domain,),
        ).fetchone()
        return _row_to_source(row) if row else None

    def list_sources_by_status(self, status: SourceStatus) -> list[Source]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, name, domain, tier, status, ai_score, ai_reason, created_at, updated_at "
            "FROM news_sources WHERE status = ? ORDER BY created_at ASC",
            (status,),
        ).fetchall()
        return [_row_to_source(r) for r in rows]

    def list_all_sources(self) -> list[Source]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, name, domain, tier, status, ai_score, ai_reason, created_at, updated_at "
            "FROM news_sources ORDER BY created_at DESC"
        ).fetchall()
        return [_row_to_source(r) for r in rows]

    def update_source_status(
        self, source_id: str, status: SourceStatus, updated_at: str
    ) -> None:
        conn = get_connection()
        conn.execute(
            "UPDATE news_sources SET status = ?, updated_at = ? WHERE id = ?",
            (status, updated_at, source_id),
        )
        conn.commit()

    def insert_audit(self, audit: SourceAudit) -> None:
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO news_source_audits "
                "(id, source_id, admin_id, previous_status, decision, reason, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    audit.id,
                    audit.source_id,
                    audit.admin_id,
                    audit.previous_status,
                    audit.decision,
                    audit.reason,
                    audit.created_at,
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def list_audits(self) -> list[SourceAudit]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, source_id, admin_id, previous_status, decision, reason, created_at "
            "FROM news_source_audits ORDER BY created_at DESC"
        ).fetchall()
        return [_row_to_audit(r) for r in rows]
