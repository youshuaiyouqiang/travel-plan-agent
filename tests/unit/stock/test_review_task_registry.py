"""Task 5 失败测试——ReviewTaskRegistry 单元测试。

覆盖：
- create_task 返回唯一 task_id
- get_task 找不到返回 None
- update_status 流转 pending → running → completed
- list_by_user 仅返回该 user 的 task
- expire_after_seconds 后未访问的 task 应被自动清理
- 同 user 同 trade_date 进行中 → 复用同一 task_id（幂等）
"""

from __future__ import annotations

import time

import pytest

from application.stock.review_task_registry import (
    ReviewTask,
    ReviewTaskRegistry,
    ReviewTaskStatus,
)


class TestReviewTaskRegistryBasics:
    def test_create_task_returns_unique_id(self) -> None:
        reg = ReviewTaskRegistry()
        task_id_1 = reg.create_task(user_id="u1", trade_date="20260728")
        task_id_2 = reg.create_task(user_id="u2", trade_date="20260728")
        assert task_id_1 != task_id_2
        assert len(task_id_1) > 0

    def test_get_task_returns_created_task(self) -> None:
        reg = ReviewTaskRegistry()
        task_id = reg.create_task(user_id="u1", trade_date="20260728")
        task = reg.get_task(task_id)
        assert task is not None
        assert task.task_id == task_id
        assert task.user_id == "u1"
        assert task.trade_date == "20260728"
        assert task.status == ReviewTaskStatus.PENDING

    def test_get_task_unknown_returns_none(self) -> None:
        reg = ReviewTaskRegistry()
        assert reg.get_task("unknown-id") is None

    def test_update_status_to_running(self) -> None:
        reg = ReviewTaskRegistry()
        task_id = reg.create_task(user_id="u1", trade_date="20260728")
        reg.update_status(task_id, ReviewTaskStatus.RUNNING)
        task = reg.get_task(task_id)
        assert task is not None
        assert task.status == ReviewTaskStatus.RUNNING

    def test_update_status_to_completed_with_report_id(self) -> None:
        reg = ReviewTaskRegistry()
        task_id = reg.create_task(user_id="u1", trade_date="20260728")
        reg.update_status(
            task_id,
            ReviewTaskStatus.COMPLETED,
            report_id="rep-123",
        )
        task = reg.get_task(task_id)
        assert task is not None
        assert task.status == ReviewTaskStatus.COMPLETED
        assert task.report_id == "rep-123"
        assert task.error is None

    def test_update_status_to_failed_with_error(self) -> None:
        reg = ReviewTaskRegistry()
        task_id = reg.create_task(user_id="u1", trade_date="20260728")
        reg.update_status(
            task_id,
            ReviewTaskStatus.FAILED,
            error="LLM 不可用",
        )
        task = reg.get_task(task_id)
        assert task is not None
        assert task.status == ReviewTaskStatus.FAILED
        assert task.error == "LLM 不可用"
        assert task.report_id is None

    def test_update_status_unknown_task_raises(self) -> None:
        reg = ReviewTaskRegistry()
        with pytest.raises(KeyError):
            reg.update_status("missing", ReviewTaskStatus.RUNNING)


class TestListByUser:
    def test_list_by_user_filters_correctly(self) -> None:
        reg = ReviewTaskRegistry()
        reg.create_task(user_id="u1", trade_date="20260728")
        reg.create_task(user_id="u1", trade_date="20260727")
        reg.create_task(user_id="u2", trade_date="20260728")
        u1_tasks = reg.list_by_user("u1")
        u2_tasks = reg.list_by_user("u2")
        assert len(u1_tasks) == 2
        assert len(u2_tasks) == 1
        assert all(t.user_id == "u1" for t in u1_tasks)
        assert all(t.user_id == "u2" for t in u2_tasks)

    def test_list_by_user_sorted_descending(self) -> None:
        reg = ReviewTaskRegistry()
        reg.create_task(user_id="u1", trade_date="20260728")
        time.sleep(0.005)
        reg.create_task(user_id="u1", trade_date="20260727")
        time.sleep(0.005)
        reg.create_task(user_id="u1", trade_date="20260726")
        u1_tasks = reg.list_by_user("u1")
        # 按 updated_at DESC 排序：最后创建的（trade_date=20260726）排在最前
        assert u1_tasks[0].trade_date == "20260726"
        assert u1_tasks[-1].trade_date == "20260728"

    def test_list_by_user_empty(self) -> None:
        reg = ReviewTaskRegistry()
        assert reg.list_by_user("nobody") == []


class TestIdempotency:
    def test_idempotent_pending_or_running(self) -> None:
        """同 user + trade_date 在 pending/running 状态下应返回同一 task_id。"""
        reg = ReviewTaskRegistry()
        id_1 = reg.create_task(user_id="u1", trade_date="20260728")
        id_2 = reg.create_task(user_id="u1", trade_date="20260728")
        assert id_1 == id_2

    def test_idempotent_after_running(self) -> None:
        reg = ReviewTaskRegistry()
        id_1 = reg.create_task(user_id="u1", trade_date="20260728")
        reg.update_status(id_1, ReviewTaskStatus.RUNNING)
        # 仍在进行中：第二次 create 应返回同一 task_id
        id_2 = reg.create_task(user_id="u1", trade_date="20260728")
        assert id_1 == id_2

    def test_new_task_after_completed(self) -> None:
        """completed 之后应创建新 task（重新生成复盘文）。"""
        reg = ReviewTaskRegistry()
        id_1 = reg.create_task(user_id="u1", trade_date="20260728")
        reg.update_status(id_1, ReviewTaskStatus.COMPLETED, report_id="r1")
        id_2 = reg.create_task(user_id="u1", trade_date="20260728")
        assert id_1 != id_2

    def test_new_task_after_failed(self) -> None:
        """failed 之后应创建新 task。"""
        reg = ReviewTaskRegistry()
        id_1 = reg.create_task(user_id="u1", trade_date="20260728")
        reg.update_status(id_1, ReviewTaskStatus.FAILED, error="err")
        id_2 = reg.create_task(user_id="u1", trade_date="20260728")
        assert id_1 != id_2


class TestTTL:
    def test_ttl_cleanup_drops_old_tasks(self, monkeypatch) -> None:
        """TTL 过期后未访问的 task 应被自动清理。"""
        reg = ReviewTaskRegistry(ttl_seconds=1, sweep_interval=1)
        task_id = reg.create_task(user_id="u1", trade_date="20260728")
        assert reg.get_task(task_id) is not None
        # 模拟 1.5s 后访问
        time.sleep(1.5)
        reg.sweep_expired()
        assert reg.get_task(task_id) is None

    def test_ttl_keeps_fresh_tasks(self) -> None:
        reg = ReviewTaskRegistry(ttl_seconds=60)
        task_id = reg.create_task(user_id="u1", trade_date="20260728")
        reg.sweep_expired()
        assert reg.get_task(task_id) is not None

    def test_get_task_resets_idle_clock(self) -> None:
        """get_task 命中应重置 idle 时钟，避免活跃 task 被清掉。"""
        reg = ReviewTaskRegistry(ttl_seconds=1, sweep_interval=1)
        task_id = reg.create_task(user_id="u1", trade_date="20260728")
        time.sleep(0.6)
        # 命中 get_task：重置 idle 时钟
        assert reg.get_task(task_id) is not None
        time.sleep(0.6)
        reg.sweep_expired()
        # 1.2s 但最近一次 get_task 在 0.6s 前；总计 1.2s 但 idle 从 0.6s 重算
        assert reg.get_task(task_id) is not None


class TestReviewTaskDataclass:
    def test_to_dict_round_trip(self) -> None:
        task = ReviewTask(
            task_id="t1",
            user_id="u1",
            trade_date="20260728",
            status=ReviewTaskStatus.COMPLETED,
            report_id="r1",
            error=None,
            created_at="2026-07-28T10:00:00+00:00",
            updated_at="2026-07-28T10:05:00+00:00",
        )
        d = task.to_dict()
        assert d["task_id"] == "t1"
        assert d["status"] == "completed"
        assert d["report_id"] == "r1"
        assert d["error"] is None
