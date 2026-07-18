"""Task 1 草稿与存档生命周期的集成测试。

覆盖范围：
- ``application.travel.service.TravelService`` 的草稿保存、确认存档与存档续编
- 已确认存档不可修改；继续编辑创建新草稿
- 对象级所有权校验：不属于该用户的草稿/存档统一抛 ``NotFoundException``

业务红线：已确认存档不可修改；继续编辑创建新草稿。
"""

from __future__ import annotations

import pytest

from application.exceptions import ConflictException, NotFoundException
from application.travel.service import TravelService
from infrastructure.persistence.database import init_db, reset_connection


# ---------------------------------------------------------------------------
# 共享 fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_travel_draft_archive.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()


@pytest.fixture
def service(db) -> TravelService:
    return TravelService()


def sample_plan() -> dict:
    """最小可用的行程草稿内容。"""
    return {
        "title": "京都三日游",
        "destination": "京都",
        "days": [
            {
                "day_index": 1,
                "date": "2026-08-01",
                "activities": [
                    {"id": "a1", "title": "清水寺", "time_slot": "上午", "location": "清水道"},
                ],
            },
        ],
    }


# ---------------------------------------------------------------------------
# 生命周期测试
# ---------------------------------------------------------------------------


class TestTravelDraftArchiveLifecycle:
    def test_save_draft_returns_draft_with_id_and_plan(self, service):
        draft = service.save_draft("u1", "s1", sample_plan())
        assert draft.id
        assert draft.user_id == "u1"
        assert draft.session_id == "s1"
        assert draft.plan["title"] == "京都三日游"
        assert draft.is_read_only is False
        assert draft.source_archive_id is None
        assert draft.manual_edit_fields == set()

    def test_confirmed_archive_is_immutable(self, service):
        draft = service.save_draft("u1", "s1", sample_plan())
        archive = service.confirm("u1", draft.id)
        assert archive.id
        assert archive.source_draft_id == draft.id
        assert archive.plan_json  # 非空快照

        with pytest.raises(ConflictException):
            service.edit_archive("u1", archive.id, {"title": "new"})

        next_draft = service.start_draft_from_archive("u1", archive.id)
        assert next_draft.source_archive_id == archive.id
        assert next_draft.is_read_only is False
        assert next_draft.plan["title"] == "京都三日游"

    def test_confirm_marks_source_draft_read_only(self, service):
        draft = service.save_draft("u1", "s1", sample_plan())
        service.confirm("u1", draft.id)
        reloaded = service.require_owned_draft("u1", draft.id)
        assert reloaded.is_read_only is True

    def test_confirm_twice_raises_conflict(self, service):
        draft = service.save_draft("u1", "s1", sample_plan())
        service.confirm("u1", draft.id)
        with pytest.raises(ConflictException):
            service.confirm("u1", draft.id)


# ---------------------------------------------------------------------------
# 对象级所有权校验
# ---------------------------------------------------------------------------


class TestTravelOwnership:
    def test_require_owned_draft_404_for_other_user(self, service):
        draft = service.save_draft("u1", "s1", sample_plan())
        with pytest.raises(NotFoundException):
            service.require_owned_draft("u2", draft.id)

    def test_require_owned_draft_404_for_missing(self, service):
        with pytest.raises(NotFoundException):
            service.require_owned_draft("u1", "does-not-exist")

    def test_confirm_rejects_other_user(self, service):
        draft = service.save_draft("u1", "s1", sample_plan())
        with pytest.raises(NotFoundException):
            service.confirm("u2", draft.id)

    def test_confirm_rejects_missing_draft(self, service):
        with pytest.raises(NotFoundException):
            service.confirm("u1", "does-not-exist")

    def test_start_draft_from_archive_rejects_other_user(self, service):
        draft = service.save_draft("u1", "s1", sample_plan())
        archive = service.confirm("u1", draft.id)
        with pytest.raises(NotFoundException):
            service.start_draft_from_archive("u2", archive.id)

    def test_edit_archive_rejects_other_user(self, service):
        draft = service.save_draft("u1", "s1", sample_plan())
        archive = service.confirm("u1", draft.id)
        # 即使不属于该用户，编辑存档也应拒绝；不可变存档优先抛 ConflictException
        with pytest.raises((NotFoundException, ConflictException)):
            service.edit_archive("u2", archive.id, {"title": "x"})
