"""Task 1 — 新闻来源治理持久化层。

设计要点：
- 所有 SQL 使用 ``?`` 参数绑定；表名来自代码内硬编码白名单。
- ``Source`` / ``SourceAudit`` / ``NewsSourceInit`` 与数据库行之间的双向转换集中在此层。
- 不保存新闻全文；仅保存来源元数据、审核审计与系统初始化事件。
- ``scoring_mode`` 区分内置白名单与 AI 评分候选；``ai_subscores`` 存 6 维度 JSON。
"""

from __future__ import annotations

from typing import Any

from application.news.models import (
    NewsSourceInit,
    ScoringMode,
    Source,
    SourceAudit,
    SourceStatus,
)
from infrastructure.persistence.database import get_connection


def _row_to_source(row: Any) -> Source:
    return Source(
        id=row["id"],
        name=row["name"],
        domain=row["domain"],
        tier=row["tier"],
        status=row["status"],
        scoring_mode=row["scoring_mode"],
        ai_score=row["ai_score"],
        ai_reason=row["ai_reason"],
        ai_subscores=row["ai_subscores"] if "ai_subscores" in row.keys() else "{}",
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


def _row_to_init(row: Any) -> NewsSourceInit:
    return NewsSourceInit(
        id=row["id"],
        source_id=row["source_id"],
        tier=row["tier"],
        scoring_mode=row["scoring_mode"],
        init_at=row["init_at"],
        init_reason=row["init_reason"],
    )


# news_sources 列白名单（用于 SELECT，避免 select * 在测试/旧数据库上漏列）
_SOURCE_COLUMNS = (
    "id, name, domain, tier, status, scoring_mode, "
    "ai_score, ai_reason, ai_subscores, created_at, updated_at"
)


class NewsSourceRepository:
    """新闻来源、审核审计与系统初始化的 SQLite 持久化仓库。"""

    def insert_source(self, source: Source) -> None:
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO news_sources "
                "(id, name, domain, tier, status, scoring_mode, "
                "ai_score, ai_reason, ai_subscores, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    source.id,
                    source.name,
                    source.domain,
                    source.tier,
                    source.status,
                    source.scoring_mode,
                    source.ai_score,
                    source.ai_reason,
                    source.ai_subscores,
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
            f"SELECT {_SOURCE_COLUMNS} FROM news_sources WHERE id = ?",
            (source_id,),
        ).fetchone()
        return _row_to_source(row) if row else None

    def get_source_by_domain(self, domain: str) -> Source | None:
        conn = get_connection()
        row = conn.execute(
            f"SELECT {_SOURCE_COLUMNS} FROM news_sources WHERE domain = ?",
            (domain,),
        ).fetchone()
        return _row_to_source(row) if row else None

    def list_sources_by_status(self, status: SourceStatus) -> list[Source]:
        conn = get_connection()
        rows = conn.execute(
            f"SELECT {_SOURCE_COLUMNS} FROM news_sources "
            "WHERE status = ? ORDER BY created_at ASC",
            (status,),
        ).fetchall()
        return [_row_to_source(r) for r in rows]

    def list_all_sources(self) -> list[Source]:
        conn = get_connection()
        rows = conn.execute(
            f"SELECT {_SOURCE_COLUMNS} FROM news_sources ORDER BY created_at DESC"
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

    def update_source_builtin(
        self, source_id: str, tier: str, updated_at: str
    ) -> None:
        """仅修正内置白名单来源的 tier 与 updated_at；不动其他字段。

        用于 ``register_builtin_whitelist`` 在域名已存在但 ``tier`` 错位时
        的幂等更新。``scoring_mode/ai_score/ai_reason`` 不会被改写。
        """
        conn = get_connection()
        conn.execute(
            "UPDATE news_sources SET tier = ?, updated_at = ? WHERE id = ?",
            (tier, updated_at, source_id),
        )
        conn.commit()

    def update_source_status_builtin_metadata(
        self,
        source_id: str,
        tier: str,
        ai_score: float | None,
        ai_reason: str,
        ai_subscores: str,
        updated_at: str,
    ) -> None:
        """内置白名单元数据全量校正。

        用于 ``register_builtin_whitelist`` 在已有脏数据时把字段拉回
        builtin_whitelist 的正确状态（tier + ai_score=NULL + ai_reason +
        ai_subscores）。``scoring_mode`` 单独由 :meth:`update_source_builtin_scoring_mode` 写。
        """
        conn = get_connection()
        conn.execute(
            "UPDATE news_sources SET tier = ?, ai_score = ?, ai_reason = ?, "
            "ai_subscores = ?, updated_at = ? WHERE id = ?",
            (tier, ai_score, ai_reason, ai_subscores, updated_at, source_id),
        )
        conn.commit()

    def update_source_builtin_scoring_mode(
        self, source_id: str, scoring_mode: str, updated_at: str
    ) -> None:
        """仅修正 ``scoring_mode`` 字段；其他字段不动。

        拆分专用方法是因为 :meth:`update_source_status_builtin_metadata`
        写多列；这里只动 ``scoring_mode`` 以降低误改风险。
        """
        conn = get_connection()
        conn.execute(
            "UPDATE news_sources SET scoring_mode = ?, updated_at = ? WHERE id = ?",
            (scoring_mode, updated_at, source_id),
        )
        conn.commit()

    # ------------------------------------------------------------------
    # 审计
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # 系统初始化事件（替代占位审计行）
    # ------------------------------------------------------------------

    def insert_init(self, init: NewsSourceInit) -> None:
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO news_source_inits "
                "(id, source_id, tier, scoring_mode, init_at, init_reason) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    init.id,
                    init.source_id,
                    init.tier,
                    init.scoring_mode,
                    init.init_at,
                    init.init_reason,
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def list_inits(self) -> list[NewsSourceInit]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, source_id, tier, scoring_mode, init_at, init_reason "
            "FROM news_source_inits ORDER BY init_at DESC"
        ).fetchall()
        return [_row_to_init(r) for r in rows]
