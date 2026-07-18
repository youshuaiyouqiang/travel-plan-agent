"""Task 1 — 旅行草稿与存档持久化层。

设计要点：
- 所有 SQL 使用 ``?`` 参数绑定；表名来自代码内硬编码白名单。
- ``TravelDraft`` / ``TravelArchive`` 与数据库行之间的双向转换集中在此层。
- 存档表只保存行程 JSON 快照，不保存原始外部数据。
"""

from __future__ import annotations

import json
from typing import Any

from application.travel.models import TravelArchive, TravelDraft
from infrastructure.persistence.database import get_connection


def _row_to_draft(row: Any) -> TravelDraft:
    return TravelDraft(
        id=row["id"],
        user_id=row["user_id"],
        session_id=row["session_id"],
        plan=json.loads(row["plan_json"] or "{}"),
        manual_edit_fields=set(json.loads(row["manual_edit_fields"] or "[]")),
        is_read_only=bool(row["is_read_only"]),
        source_archive_id=row["source_archive_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_archive(row: Any) -> TravelArchive:
    return TravelArchive(
        id=row["id"],
        user_id=row["user_id"],
        source_draft_id=row["source_draft_id"],
        confirmed_at=row["confirmed_at"],
        plan_json=row["plan_json"],
    )


class TravelRepository:
    """旅行草稿与存档的 SQLite 持久化仓库。"""

    def insert_draft(self, draft: TravelDraft) -> None:
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO travel_drafts "
                "(id, user_id, session_id, plan_json, manual_edit_fields, "
                "is_read_only, source_archive_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    draft.id,
                    draft.user_id,
                    draft.session_id,
                    json.dumps(draft.plan, ensure_ascii=False),
                    json.dumps(sorted(draft.manual_edit_fields), ensure_ascii=False),
                    1 if draft.is_read_only else 0,
                    draft.source_archive_id,
                    draft.created_at,
                    draft.updated_at,
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def get_draft(self, draft_id: str) -> TravelDraft | None:
        conn = get_connection()
        row = conn.execute(
            "SELECT id, user_id, session_id, plan_json, manual_edit_fields, "
            "is_read_only, source_archive_id, created_at, updated_at "
            "FROM travel_drafts WHERE id = ?",
            (draft_id,),
        ).fetchone()
        return _row_to_draft(row) if row else None

    def mark_draft_read_only(self, draft_id: str, updated_at: str) -> None:
        conn = get_connection()
        conn.execute(
            "UPDATE travel_drafts SET is_read_only = 1, updated_at = ? WHERE id = ?",
            (updated_at, draft_id),
        )
        conn.commit()

    def insert_archive(self, archive: TravelArchive) -> None:
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO travel_archives "
                "(id, user_id, source_draft_id, plan_json, confirmed_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    archive.id,
                    archive.user_id,
                    archive.source_draft_id,
                    archive.plan_json,
                    archive.confirmed_at,
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def get_archive(self, archive_id: str) -> TravelArchive | None:
        conn = get_connection()
        row = conn.execute(
            "SELECT id, user_id, source_draft_id, plan_json, confirmed_at "
            "FROM travel_archives WHERE id = ?",
            (archive_id,),
        ).fetchone()
        return _row_to_archive(row) if row else None
