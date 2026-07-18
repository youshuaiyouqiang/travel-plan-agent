"""旅行草稿与存档生命周期应用服务。

设计要点：
- 每个用户和旅行会话只有一份当前草稿；确认后草稿变只读。
- 已确认存档不可修改；``edit_archive`` 永远抛 ``ConflictException``。
- 继续编辑通过 ``start_draft_from_archive`` 创建新草稿，``source_archive_id`` 指向来源存档。
- 所有读取/确认都先经 ``require_owned_draft`` / ``_require_owned_archive`` 校验所有权；
  不属于该用户的资源统一抛 ``NotFoundException``，避免泄漏存在性。
"""

from __future__ import annotations

import json
import os
from datetime import datetime

from application.exceptions import ConflictException, NotFoundException
from application.travel.models import TravelArchive, TravelDraft
from infrastructure.persistence.travel_repository import TravelRepository


class TravelService:
    """旅行草稿与存档应用服务。"""

    def __init__(self, repository: TravelRepository | None = None) -> None:
        self._repo = repository or TravelRepository()

    # ------------------------------------------------------------------
    # 草稿
    # ------------------------------------------------------------------

    def save_draft(self, user_id: str, session_id: str, plan: dict) -> TravelDraft:
        """保存一份新的当前草稿。"""
        now = datetime.utcnow().isoformat()
        draft = TravelDraft(
            id=os.urandom(8).hex(),
            user_id=user_id,
            session_id=session_id,
            plan=plan,
            manual_edit_fields=set(),
            is_read_only=False,
            source_archive_id=None,
            created_at=now,
            updated_at=now,
        )
        self._repo.insert_draft(draft)
        return draft

    def require_owned_draft(self, user_id: str, draft_id: str) -> TravelDraft:
        """读取草稿；未找到或不属于该用户均抛 ``NotFoundException``。"""
        draft = self._repo.get_draft(draft_id)
        if draft is None or draft.user_id != user_id:
            raise NotFoundException("travel_draft", draft_id)
        return draft

    # ------------------------------------------------------------------
    # 确认存档
    # ------------------------------------------------------------------

    def confirm(self, user_id: str, draft_id: str) -> TravelArchive:
        """将草稿确认存档：复制草稿快照到存档表，并将草稿标记只读。

        已确认（只读）的草稿再次确认抛 ``ConflictException``。
        """
        draft = self.require_owned_draft(user_id, draft_id)
        if draft.is_read_only:
            raise ConflictException("草稿已确认，无法再次确认")
        archive = TravelArchive(
            id=os.urandom(8).hex(),
            user_id=user_id,
            source_draft_id=draft.id,
            confirmed_at=datetime.utcnow().isoformat(),
            plan_json=json.dumps(draft.plan, ensure_ascii=False),
        )
        self._repo.insert_archive(archive)
        self._repo.mark_draft_read_only(draft.id, datetime.utcnow().isoformat())
        return archive

    def edit_archive(self, user_id: str, archive_id: str, changes: dict) -> None:
        """存档不可变：永远抛 ``ConflictException``。

        若存档不属于该用户，则抛 ``NotFoundException`` 以避免泄漏存在性。
        """
        archive = self._require_owned_archive(user_id, archive_id)
        raise ConflictException(f"存档不可修改: {archive.id}")

    def start_draft_from_archive(self, user_id: str, archive_id: str) -> TravelDraft:
        """基于已确认存档创建新草稿，``source_archive_id`` 指向来源存档。

        新草稿沿用来源草稿的会话 id；若来源草稿已被清理，回退到原草稿 id 作为会话标识。
        """
        archive = self._require_owned_archive(user_id, archive_id)
        source_draft = self._repo.get_draft(archive.source_draft_id)
        session_id = source_draft.session_id if source_draft else archive.source_draft_id
        now = datetime.utcnow().isoformat()
        draft = TravelDraft(
            id=os.urandom(8).hex(),
            user_id=user_id,
            session_id=session_id,
            plan=json.loads(archive.plan_json or "{}"),
            manual_edit_fields=set(),
            is_read_only=False,
            source_archive_id=archive.id,
            created_at=now,
            updated_at=now,
        )
        self._repo.insert_draft(draft)
        return draft

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _require_owned_archive(self, user_id: str, archive_id: str) -> TravelArchive:
        archive = self._repo.get_archive(archive_id)
        if archive is None or archive.user_id != user_id:
            raise NotFoundException("travel_archive", archive_id)
        return archive
