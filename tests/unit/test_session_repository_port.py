"""P2.1 SessionRepositoryPort 的 fake 实现与消费者单元测试。

验证 domain/application 层的 SessionManager、TaskStateStore、SessionService
可通过 fake 端口运行，不创建 SQLite 文件、不访问真实网络。

这保证后续 P2 聚合在切换 SQLite 实现时，领域逻辑的行为不回归。
"""

from __future__ import annotations

from typing import Any

import pytest

from application.exceptions import NotFoundException, ValidationException
from application.session.service import SessionService
from domain.user.session.manager import Session, SessionManager, Turn
from domain.user.session.task_state import TaskRecord, TaskStatus, TaskStateStore


# ── Fake 实现 ──────────────────────────────────────────────


class FakeSessionRepository:
    """``SessionRepositoryPort`` 的内存 fake，供单元测试使用。"""

    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._turns: dict[str, list[dict[str, Any]]] = {}
        self._tasks: dict[str, dict[str, Any]] = {}

    # Session 聚合

    def save_session(self, session: Session) -> None:
        self._sessions[session.session_id] = {
            "session_id": session.session_id,
            "user_id": session.user_id,
            "summary": session.summary,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "disclosed_tools": list(session.disclosed_tools),
            "delegation_agent_id": session.delegation_agent_id,
            "delegation_started_at": session.delegation_started_at,
            "delegation_last_interaction": session.delegation_last_interaction,
            "mode": session.mode,
            "locked_agent_id": session.locked_agent_id,
            "news_id": session.news_id,
        }
        existing = self._turns.get(session.session_id, [])
        last_persisted = getattr(session, "_last_persisted_turn", 0)
        for turn in session.turns[last_persisted:]:
            existing.append({"role": turn.role, "content": turn.content, "created_at": turn.created_at})
        self._turns[session.session_id] = existing
        session._last_persisted_turn = len(session.turns)

    def load_session(self, session_id: str) -> Session | None:
        data = self._sessions.get(session_id)
        if data is None:
            return None
        turns = [
            Turn(role=t["role"], content=t["content"], created_at=t["created_at"])
            for t in self._turns.get(session_id, [])
        ]
        session = Session(
            session_id=data["session_id"],
            turns=turns,
            summary=data["summary"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            disclosed_tools=list(data["disclosed_tools"]),
            delegation_agent_id=data["delegation_agent_id"],
            delegation_started_at=data["delegation_started_at"],
            delegation_last_interaction=data["delegation_last_interaction"],
            user_id=data["user_id"],
            mode=data["mode"],
            locked_agent_id=data["locked_agent_id"],
            news_id=data["news_id"],
        )
        session._last_persisted_turn = len(turns)
        return session

    # 会话模式记录

    def create_session_row(
        self,
        *,
        session_id: str,
        user_id: str,
        mode: str,
        locked_agent_id: str | None,
        news_id: str | None,
    ) -> None:
        from datetime import datetime

        now = datetime.utcnow().isoformat()
        self._sessions[session_id] = {
            "session_id": session_id,
            "user_id": user_id,
            "summary": "",
            "created_at": now,
            "updated_at": now,
            "disclosed_tools": [],
            "delegation_agent_id": None,
            "delegation_started_at": None,
            "delegation_last_interaction": None,
            "mode": mode,
            "locked_agent_id": locked_agent_id,
            "news_id": news_id,
        }
        self._tasks[session_id] = {
            "session_id": session_id,
            "user_id": user_id,
            "status": "idle",
            "goal": "",
            "latest_user_message": "",
            "latest_reply": "",
            "pending_prompt": "",
            "trace_summary": "",
            "metadata": {},
            "created_at": now,
            "updated_at": now,
        }

    def get_session_record(self, session_id: str) -> dict[str, Any] | None:
        data = self._sessions.get(session_id)
        if data is None:
            return None
        return {
            "session_id": data["session_id"],
            "user_id": data["user_id"],
            "mode": data["mode"],
            "locked_agent_id": data["locked_agent_id"],
            "news_id": data["news_id"],
        }

    def update_session_mode(
        self,
        *,
        session_id: str,
        mode: str,
        locked_agent_id: str | None,
        news_id: str | None,
    ) -> None:
        data = self._sessions.get(session_id)
        if data is not None:
            data["mode"] = mode
            data["locked_agent_id"] = locked_agent_id
            data["news_id"] = news_id

    # 方案确认（P3.3b）

    def get_confirmed_plan(self, session_id: str) -> dict[str, Any] | None:
        data = self._sessions.get(session_id)
        if data is None:
            return None
        return {
            "confirmed_plan": data.get("confirmed_plan"),
            "confirmed_at": data.get("confirmed_at"),
        }

    def set_confirmed_plan(self, *, session_id: str, plan_type: str, now: str) -> None:
        data = self._sessions.get(session_id)
        if data is not None:
            data["confirmed_plan"] = plan_type
            data["confirmed_at"] = now

    def clear_confirmed_plan(self, session_id: str) -> None:
        data = self._sessions.get(session_id)
        if data is not None:
            data["confirmed_plan"] = None
            data["confirmed_at"] = None

    # 列表与消息

    def list_sessions_by_user(self, user_id: str) -> list[dict[str, Any]]:
        result = []
        for data in self._sessions.values():
            if data["user_id"] == user_id:
                turns = self._turns.get(data["session_id"], [])
                first_msg = next((t["content"] for t in turns if t["role"] == "user"), "")
                result.append({
                    "session_id": data["session_id"],
                    "title": data["summary"] or (first_msg[:60] if first_msg else "新对话"),
                    "created_at": data["created_at"],
                    "updated_at": data["updated_at"],
                    "message_count": len(turns),
                })
        result.sort(key=lambda x: x["updated_at"], reverse=True)
        return result

    def find_session_ids_by_user(self, user_id: str) -> list[str]:
        """列出用户在 tasks 表中的去重 session_id（fake 实现）。"""
        seen: list[str] = []
        for sid, task in self._tasks.items():
            if task.get("user_id") == user_id and sid and sid not in seen:
                seen.append(sid)
        return seen

    def get_session_messages(self, session_id: str) -> list[dict[str, Any]]:
        return list(self._turns.get(session_id, []))

    # 删除

    def delete_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        self._turns.pop(session_id, None)
        self._tasks.pop(session_id, None)

    # Task 状态

    def save_task(self, task: TaskRecord) -> None:
        self._tasks[task.session_id] = {
            "session_id": task.session_id,
            "user_id": task.user_id,
            "status": task.status.value,
            "goal": task.goal,
            "latest_user_message": task.latest_user_message,
            "latest_reply": task.latest_reply,
            "pending_prompt": task.pending_prompt,
            "trace_summary": task.trace_summary,
            "metadata": dict(task.metadata),
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        }

    def load_task(self, session_id: str) -> TaskRecord | None:
        data = self._tasks.get(session_id)
        if data is None:
            return None
        try:
            status = TaskStatus(data["status"])
        except ValueError:
            status = TaskStatus.IDLE
        return TaskRecord(
            session_id=data["session_id"],
            user_id=data["user_id"],
            status=status,
            goal=data["goal"],
            latest_user_message=data["latest_user_message"],
            latest_reply=data["latest_reply"],
            pending_prompt=data["pending_prompt"],
            trace_summary=data["trace_summary"],
            metadata=dict(data["metadata"]),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )


# ── SessionManager 单元测试 ────────────────────────────────


class TestSessionManagerWithFake:
    """SessionManager 通过 fake 端口运行，不创建 SQLite 文件。"""

    def test_save_and_load_session(self):
        repo = FakeSessionRepository()
        manager = SessionManager(repository=repo)

        session = manager.get("test-session")
        session.append("user", "hello")
        session.append("assistant", "hi there")
        session.summary = "a test chat"
        session.user_id = "user-1"
        manager.save(session)

        # 新 manager 实例从 fake 重新加载
        manager2 = SessionManager(repository=repo)
        loaded = manager2.get("test-session")
        assert loaded.session_id == "test-session"
        assert len(loaded.turns) == 2
        assert loaded.turns[0].content == "hello"
        assert loaded.turns[1].content == "hi there"
        assert loaded.summary == "a test chat"
        assert loaded.user_id == "user-1"

    def test_incremental_turn_persistence(self):
        """增量持久化：保存后新增 turn，再次保存只插入新 turn。"""
        repo = FakeSessionRepository()
        manager = SessionManager(repository=repo)

        session = manager.get("inc-test")
        session.append("user", "msg1")
        manager.save(session)
        assert len(repo._turns["inc-test"]) == 1

        session.append("assistant", "reply1")
        session.append("user", "msg2")
        manager.save(session)
        assert len(repo._turns["inc-test"]) == 3

    def test_load_nonexistent_returns_new_session(self):
        repo = FakeSessionRepository()
        manager = SessionManager(repository=repo)
        session = manager.get("nonexistent")
        assert session.session_id == "nonexistent"
        assert session.turns == []

    def test_list_user_sessions(self):
        repo = FakeSessionRepository()
        manager = SessionManager(repository=repo)

        session = manager.get("list-test")
        session.user_id = "user-list"
        session.append("user", "first message")
        manager.save(session)

        sessions = manager.list_user_sessions("user-list")
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == "list-test"
        assert sessions[0]["message_count"] == 1

    def test_delete_session(self):
        repo = FakeSessionRepository()
        manager = SessionManager(repository=repo)

        session = manager.get("del-test")
        session.user_id = "user-del"
        manager.save(session)
        assert "del-test" in repo._sessions

        manager.delete_session("del-test")
        assert "del-test" not in repo._sessions
        assert "del-test" not in manager._sessions

    def test_snapshot(self):
        repo = FakeSessionRepository()
        manager = SessionManager(repository=repo)

        session = manager.get("snap-test")
        session.append("user", "snap msg")
        manager.save(session)

        snap = manager.snapshot("snap-test")
        assert snap is not None
        assert snap["session_id"] == "snap-test"
        assert len(snap["turns"]) == 1
        assert "task" in snap


# ── TaskStateStore 单元测试 ────────────────────────────────


class TestTaskStateStoreWithFake:
    """TaskStateStore 通过 fake 端口运行，不创建 SQLite 文件。"""

    def test_get_creates_default_task(self):
        repo = FakeSessionRepository()
        store = TaskStateStore(repository=repo)
        task = store.get("new-task", user_id="user-1")
        assert task.session_id == "new-task"
        assert task.user_id == "user-1"
        assert task.status == TaskStatus.IDLE

    def test_save_and_reload(self):
        repo = FakeSessionRepository()
        store = TaskStateStore(repository=repo)

        task = store.get("persist-task", user_id="user-1")
        task.mark_in_progress(goal="test goal", latest_user_message="hello")
        store.save(task)

        store2 = TaskStateStore(repository=repo)
        loaded = store2.get("persist-task", user_id="user-1")
        assert loaded.status == TaskStatus.IN_PROGRESS
        assert loaded.goal == "test goal"
        assert loaded.latest_user_message == "hello"

    def test_user_id_update_on_mismatch(self):
        repo = FakeSessionRepository()
        store = TaskStateStore(repository=repo)

        task = store.get("uid-task", user_id="user-1")
        task.save = lambda: store.save(task)  # 不保存，仅测试 get 行为

        # 模拟用户 ID 变更
        loaded = store.get("uid-task", user_id="user-2")
        assert loaded.user_id == "user-2"


# ── SessionService 单元测试 ────────────────────────────────


class TestSessionServiceWithFake:
    """SessionService 通过 fake 端口运行，不创建 SQLite 文件。"""

    def test_create_session(self):
        repo = FakeSessionRepository()
        service = SessionService(
            available_agent_ids={"travel", "academic"},
            repository=repo,
        )
        record = service.create(
            user_id="user-1",
            mode="yunhe_default",
        )
        assert record.user_id == "user-1"
        assert record.mode == "yunhe_default"
        assert record.session_id  # 生成的不为空

    def test_create_agent_locked_requires_id(self):
        repo = FakeSessionRepository()
        service = SessionService(repository=repo)
        with pytest.raises(ValidationException):
            service.create(user_id="user-1", mode="agent_locked")

    def test_create_agent_locked_invalid_agent(self):
        repo = FakeSessionRepository()
        service = SessionService(
            available_agent_ids={"travel", "academic"},
            repository=repo,
        )
        with pytest.raises(ValidationException):
            service.create(
                user_id="user-1",
                mode="agent_locked",
                locked_agent_id="unknown",
            )

    def test_create_agent_locked_valid(self):
        repo = FakeSessionRepository()
        service = SessionService(
            available_agent_ids={"travel", "academic"},
            repository=repo,
        )
        record = service.create(
            user_id="user-1",
            mode="agent_locked",
            locked_agent_id="travel",
        )
        assert record.locked_agent_id == "travel"

    def test_require_owned_not_found(self):
        repo = FakeSessionRepository()
        service = SessionService(repository=repo)
        with pytest.raises(NotFoundException):
            service.require_owned(user_id="user-1", session_id="nonexistent")

    def test_require_owned_wrong_user(self):
        repo = FakeSessionRepository()
        service = SessionService(repository=repo)
        service.create(user_id="user-1", mode="yunhe_default")
        # 获取刚创建的 session_id
        record = list(repo._sessions.values())[0]
        with pytest.raises(NotFoundException):
            service.require_owned(user_id="user-2", session_id=record["session_id"])

    def test_update_mode(self):
        repo = FakeSessionRepository()
        service = SessionService(
            available_agent_ids={"travel", "academic"},
            repository=repo,
        )
        created = service.create(user_id="user-1", mode="yunhe_default")
        updated = service.update_mode(
            user_id="user-1",
            session_id=created.session_id,
            mode="agent_locked",
            locked_agent_id="travel",
        )
        assert updated.mode == "agent_locked"
        assert updated.locked_agent_id == "travel"

    def test_update_mode_rejects_news_locked(self):
        repo = FakeSessionRepository()
        service = SessionService(repository=repo)
        created = service.create(user_id="user-1", mode="yunhe_default")
        with pytest.raises(ValidationException):
            service.update_mode(
                user_id="user-1",
                session_id=created.session_id,
                mode="news_analysis_locked",
            )

    def test_create_news_analysis_locked(self):
        """news_analysis_locked 模式可在服务层内部创建。"""
        repo = FakeSessionRepository()
        service = SessionService(repository=repo)
        record = service.create(
            user_id="user-1",
            mode="news_analysis_locked",
            locked_agent_id="news",
            news_id="hotspot-123",
        )
        assert record.mode == "news_analysis_locked"
        assert record.locked_agent_id == "news"
        assert record.news_id == "hotspot-123"


# ── 端口协议验证 ────────────────────────────────────────────


class TestSessionRepositoryPort:
    """验证 SqliteSessionRepository 和 FakeSessionRepository 均满足端口协议。"""

    def test_fake_satisfies_port(self):
        from domain.user.session.ports import SessionRepositoryPort

        repo = FakeSessionRepository()
        assert isinstance(repo, SessionRepositoryPort)

    def test_sqlite_satisfies_port(self):
        from domain.user.session.ports import SessionRepositoryPort
        from infrastructure.persistence.repositories.session import SqliteSessionRepository

        repo = SqliteSessionRepository()
        assert isinstance(repo, SessionRepositoryPort)
