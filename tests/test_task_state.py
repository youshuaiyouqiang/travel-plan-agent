"""Tests for core/task_state.py — TaskStatus, TaskRecord, TaskStateStore"""
import pytest

from domain.user.session.task_state import TaskStatus, TaskRecord, TaskStateStore
from infrastructure.persistence.database import init_db, reset_connection


class TestTaskStatus:
    def test_all_values(self):
        assert TaskStatus.IDLE.value == "idle"
        assert TaskStatus.IN_PROGRESS.value == "in_progress"
        assert TaskStatus.NEEDS_USER_INPUT.value == "needs_user_input"
        assert TaskStatus.NEEDS_CONFIRMATION.value == "needs_confirmation"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"

    def test_from_string(self):
        assert TaskStatus("in_progress") == TaskStatus.IN_PROGRESS
        assert TaskStatus("needs_user_input") == TaskStatus.NEEDS_USER_INPUT

    def test_invalid_string_raises(self):
        with pytest.raises(ValueError):
            TaskStatus("nonexistent_status")


class TestTaskRecord:
    def test_defaults(self):
        record = TaskRecord(session_id="s1", user_id="u1")
        assert record.status == TaskStatus.IDLE
        assert record.goal == ""
        assert record.latest_user_message == ""
        assert record.latest_reply == ""
        assert record.pending_prompt == ""
        assert record.trace_summary == ""
        assert record.metadata == {}
        assert record.created_at
        assert record.updated_at

    def test_mark_in_progress(self):
        record = TaskRecord(session_id="s1", user_id="u1")
        record.mark_in_progress(goal="search the web", latest_user_message="查一下天气")
        assert record.status == TaskStatus.IN_PROGRESS
        assert record.goal == "search the web"
        assert record.latest_user_message == "查一下天气"
        assert record.updated_at

    def test_mark_waiting_needs_user_input(self):
        record = TaskRecord(session_id="s1", user_id="u1")
        record.mark_waiting(
            status=TaskStatus.NEEDS_USER_INPUT,
            prompt="请问您要搜索什么？",
            reply="我需要更多信息",
        )
        assert record.status == TaskStatus.NEEDS_USER_INPUT
        assert record.pending_prompt == "请问您要搜索什么？"
        assert record.latest_reply == "我需要更多信息"

    def test_mark_waiting_needs_confirmation(self):
        record = TaskRecord(session_id="s1", user_id="u1")
        record.mark_waiting(
            status=TaskStatus.NEEDS_CONFIRMATION,
            prompt="确认发送消息？",
            reply="等待确认",
        )
        assert record.status == TaskStatus.NEEDS_CONFIRMATION
        assert record.pending_prompt == "确认发送消息？"

    def test_mark_finished_completed(self):
        record = TaskRecord(session_id="s1", user_id="u1")
        record.mark_finished(status=TaskStatus.COMPLETED, reply="已完成")
        assert record.status == TaskStatus.COMPLETED
        assert record.latest_reply == "已完成"
        assert record.pending_prompt == ""

    def test_mark_finished_failed(self):
        record = TaskRecord(session_id="s1", user_id="u1")
        record.mark_finished(status=TaskStatus.FAILED, reply="任务失败")
        assert record.status == TaskStatus.FAILED
        assert record.pending_prompt == ""

    def test_state_transition_sequence(self):
        record = TaskRecord(session_id="s1", user_id="u1")
        assert record.status == TaskStatus.IDLE

        record.mark_in_progress(goal="send message", latest_user_message="发消息给张三")
        assert record.status == TaskStatus.IN_PROGRESS

        record.mark_waiting(
            status=TaskStatus.NEEDS_CONFIRMATION,
            prompt="确认发送？",
            reply="等待确认",
        )
        assert record.status == TaskStatus.NEEDS_CONFIRMATION

        record.mark_finished(status=TaskStatus.COMPLETED, reply="已发送")
        assert record.status == TaskStatus.COMPLETED
        assert record.pending_prompt == ""


class TestTaskStateStore:
    @pytest.fixture(autouse=True)
    def _setup_db(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.db"
        monkeypatch.setattr("config.settings.database_path", db_path)
        reset_connection()
        init_db(db_path)

    def test_get_creates_new_record(self):
        store = TaskStateStore()
        task = store.get("new_task", user_id="u1")
        assert task.session_id == "new_task"
        assert task.user_id == "u1"
        assert task.status == TaskStatus.IDLE

    def test_save_and_reload(self):
        store = TaskStateStore()
        task = store.get("persist_task", user_id="u1")
        task.mark_in_progress(goal="do something", latest_user_message="do it")
        store.save(task)

        store2 = TaskStateStore()
        loaded = store2.get("persist_task", user_id="u1")
        assert loaded.status == TaskStatus.IN_PROGRESS
        assert loaded.goal == "do something"

    def test_snapshot(self):
        store = TaskStateStore()
        task = store.get("snap_task", user_id="u1")
        task.mark_in_progress(goal="goal", latest_user_message="msg")
        store.save(task)

        snap = store.snapshot("snap_task", user_id="u1")
        assert snap["session_id"] == "snap_task"
        assert snap["status"] == "in_progress"
        assert snap["goal"] == "goal"

    def test_update_user_id(self):
        store = TaskStateStore()
        task = store.get("uid_task", user_id="u1")
        assert task.user_id == "u1"

        task2 = store.get("uid_task", user_id="u2")
        assert task2.user_id == "u2"
