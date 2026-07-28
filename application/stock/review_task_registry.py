"""复盘任务注册表——内存版。

设计要点（AGENTS.md §4 业务边界 + §8 端口先于实现）：
- 内存存储；不持久化（重启即清空，符合"任务状态"短期语义）
- 同 user + trade_date 在 pending/running 状态下创建 task 幂等
  返回同一 task_id（避免用户重复点击"生成复盘"重复跑 LLM）
- completed / failed / no_data / degraded 之后再创建 → 新 task_id
  （允许用户主动重新生成复盘文）
- TTL 过期清理（默认 1 小时；sweep_interval 30 分钟）
- 暴露给 application 层；api 层通过 app.state.stock_task_registry 取用

线程安全：使用 ``threading.Lock`` 保护 _tasks dict（FastAPI 可能在多线程跑 sync 端点）。
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ReviewTaskStatus(str, Enum):
    """复盘任务状态枚举。"""

    PENDING = "pending"  # 已创建，未启动
    RUNNING = "running"  # 正在跑 LLM
    COMPLETED = "completed"  # 正常完成
    DEGRADED = "degraded"  # LLM 输出缺章节，已存档降级版本
    NO_DATA = "no_data"  # 数据全空，不调 LLM
    FAILED = "failed"  # 异常失败


@dataclass
class ReviewTask:
    """单条复盘任务记录。"""

    task_id: str
    user_id: str
    trade_date: str
    status: ReviewTaskStatus
    report_id: str | None = None
    error: str | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    last_accessed_at: float = field(default_factory=time.monotonic)

    def to_dict(self) -> dict[str, Any]:
        """序列化为 API 响应 dict。"""
        return {
            "task_id": self.task_id,
            "user_id": self.user_id,
            "trade_date": self.trade_date,
            "status": self.status.value,
            "report_id": self.report_id,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class ReviewTaskRegistry:
    """复盘任务注册表。

    线程安全；进程内单例。所有方法都是同步的（O(1) 或 O(n)，
    n 极小：单用户单日最多保留几十条）。
    """

    def __init__(self, ttl_seconds: int = 3600, sweep_interval: int = 1800) -> None:
        """构造注册表。

        Args:
            ttl_seconds: 任务空闲 TTL（秒）。get_task 命中会重置 idle 时钟。
            sweep_interval: 主动 sweep 间隔（秒）。仅 ``sweep_expired()`` 调用时生效。
        """
        self._tasks: dict[str, ReviewTask] = {}
        self._lock = threading.Lock()
        self._ttl_seconds = ttl_seconds
        self._sweep_interval = sweep_interval

    def create_task(self, *, user_id: str, trade_date: str) -> str:
        """创建或复用 task。

        幂等规则：
        - 若 (user_id, trade_date) 已有 PENDING/RUNNING task → 返回其 task_id
        - 否则生成新 task_id 并插入 PENDING 记录
        """
        with self._lock:
            existing = self._find_active_for_user_date(user_id, trade_date)
            if existing is not None:
                return existing.task_id
            task_id = uuid.uuid4().hex
            task = ReviewTask(
                task_id=task_id,
                user_id=user_id,
                trade_date=trade_date,
                status=ReviewTaskStatus.PENDING,
            )
            self._tasks[task_id] = task
            return task_id

    def get_task(self, task_id: str) -> ReviewTask | None:
        """按 task_id 查询；命中时刷新 last_accessed_at。"""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            task.last_accessed_at = time.monotonic()
            return task

    def update_status(
        self,
        task_id: str,
        status: ReviewTaskStatus,
        *,
        report_id: str | None = None,
        error: str | None = None,
    ) -> None:
        """更新任务状态。task_id 不存在时抛 KeyError。"""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise KeyError(f"task_id {task_id!r} not found in registry")
            task.status = status
            if report_id is not None:
                task.report_id = report_id
            if error is not None:
                task.error = error
            task.updated_at = datetime.now(timezone.utc).isoformat()
            task.last_accessed_at = time.monotonic()

    def list_by_user(self, user_id: str) -> list[ReviewTask]:
        """列出某 user 的全部 task，按 updated_at DESC 排序。"""
        with self._lock:
            matched = [t for t in self._tasks.values() if t.user_id == user_id]
        matched.sort(key=lambda t: t.updated_at, reverse=True)
        return matched

    def sweep_expired(self, now: float | None = None) -> int:
        """清理 TTL 过期且未活跃访问的 task；返回清理条数。

        Args:
            now: 当前 monotonic 时间。None 时取 ``time.monotonic()``。
        """
        if now is None:
            now = time.monotonic()
        with self._lock:
            expired_ids = [
                tid
                for tid, t in self._tasks.items()
                if now - t.last_accessed_at > self._ttl_seconds
            ]
            for tid in expired_ids:
                del self._tasks[tid]
        return len(expired_ids)

    def size(self) -> int:
        """当前 task 数量（仅供测试与监控）。"""
        with self._lock:
            return len(self._tasks)

    # ── 内部辅助 ──

    def _find_active_for_user_date(
        self, user_id: str, trade_date: str
    ) -> ReviewTask | None:
        """在持有锁的前提下查找 (user_id, trade_date) 的 PENDING/RUNNING task。"""
        for t in self._tasks.values():
            if (
                t.user_id == user_id
                and t.trade_date == trade_date
                and t.status
                in (ReviewTaskStatus.PENDING, ReviewTaskStatus.RUNNING)
            ):
                return t
        return None
