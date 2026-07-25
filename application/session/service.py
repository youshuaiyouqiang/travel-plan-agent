"""会话模式持久化与所有权校验应用服务。

设计要点：
- 用户 API 只允许设置 ``yunhe_default`` 或 ``agent_locked``；
  ``news_analysis_locked`` 由新闻分析服务在内部调用 :py:meth:`create` 创建。
- 所有读取/更新都通过 :py:meth:`require_owned` 校验所有权；不属于该用户的会话统一
  抛出 :class:`NotFoundException`，由全局异常处理器转 404，避免泄漏存在性。
- ``agent_locked`` 必须指定一个 ``locked_agent_id``，且该 Agent 必须在初始化时
  传入的 ``available_agent_ids`` 白名单中。云合自身（``yunhe``）是调度员，不可锁定。

P2.1：原直连 ``get_connection()`` 的 SQL 已下沉到
``infrastructure.persistence.repositories.session.SqliteSessionRepository``，
本服务通过 ``SessionRepositoryPort`` 端口访问持久化层。
"""

from __future__ import annotations

import os
from datetime import datetime

from application.exceptions import NotFoundException, ValidationException
from application.session.schema import SessionMode, SessionRecord
from domain.user.session.ports import (
    SessionRepositoryPort,
    get_default_session_repository,
)


class SessionService:
    """会话模式应用服务。"""

    def __init__(
        self,
        available_agent_ids: set[str] | None = None,
        repository: SessionRepositoryPort | None = None,
    ) -> None:
        # 默认仅 travel/academic 可被用户锁定；yunhe 是调度员，news 是内部锚点 Agent。
        self._available_agent_ids: set[str] = set(available_agent_ids or {"travel", "academic"})
        self._repository = repository or get_default_session_repository()

    # ------------------------------------------------------------------
    # 创建
    # ------------------------------------------------------------------

    def create(
        self,
        *,
        user_id: str,
        mode: SessionMode,
        locked_agent_id: str | None = None,
        news_id: str | None = None,
    ) -> SessionRecord:
        """创建一个新会话并持久化其模式。

        服务层接受全部三种模式；用户 API 在调用前需自行拒绝
        ``news_analysis_locked``，详见 :py:meth:`update_mode`。
        """
        self._validate_mode_and_lock(mode, locked_agent_id, news_id)
        session_id = os.urandom(8).hex()
        self._repository.create_session_row(
            session_id=session_id,
            user_id=user_id,
            mode=mode,
            locked_agent_id=locked_agent_id,
            news_id=news_id,
        )
        return SessionRecord(
            session_id=session_id,
            user_id=user_id,
            mode=mode,
            locked_agent_id=locked_agent_id,
            news_id=news_id,
        )

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    def require_owned(self, *, user_id: str, session_id: str) -> SessionRecord:
        """读取会话；未找到或不属于该用户均抛 :class:`NotFoundException`。"""
        record = self._get(session_id)
        if record is None or record.user_id != user_id:
            raise NotFoundException("session", session_id)
        return record

    # ------------------------------------------------------------------
    # 更新模式
    # ------------------------------------------------------------------

    def update_mode(
        self,
        *,
        user_id: str,
        session_id: str,
        mode: SessionMode,
        locked_agent_id: str | None = None,
    ) -> SessionRecord:
        """更新会话模式。

        用户 API 不允许设置 ``news_analysis_locked``；该限制在此处再次防御性校验，
        以保证即使路由层遗漏也无法绕过。
        """
        if mode == "news_analysis_locked":
            raise ValidationException("不允许通过用户 API 设置新闻研判锁定")
        self._validate_mode_and_lock(mode, locked_agent_id, None)
        existing = self.require_owned(user_id=user_id, session_id=session_id)
        self._repository.update_session_mode(
            session_id=session_id,
            mode=mode,
            locked_agent_id=locked_agent_id,
            news_id=None,
        )
        return SessionRecord(
            session_id=existing.session_id,
            user_id=existing.user_id,
            mode=mode,
            locked_agent_id=locked_agent_id,
            news_id=None,
        )

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _validate_mode_and_lock(
        self,
        mode: SessionMode,
        locked_agent_id: str | None,
        news_id: str | None,
    ) -> None:
        if mode == "agent_locked":
            if not locked_agent_id:
                raise ValidationException("agent_locked 模式必须指定 locked_agent_id")
            if locked_agent_id not in self._available_agent_ids:
                raise ValidationException(f"不可用的智能体: {locked_agent_id}")
        elif mode == "news_analysis_locked":
            if not locked_agent_id or not news_id:
                raise ValidationException(
                    "news_analysis_locked 模式必须指定 locked_agent_id 和 news_id"
                )
        elif mode == "yunhe_default":
            if locked_agent_id or news_id:
                raise ValidationException(
                    "yunhe_default 模式不能指定 locked_agent_id 或 news_id"
                )
        else:  # pragma: no cover - 由 Literal 类型守护，运行时不应到达
            raise ValidationException(f"未知的会话模式: {mode}")

    def _get(self, session_id: str) -> SessionRecord | None:
        row = self._repository.get_session_record(session_id)
        if row is None:
            return None
        return SessionRecord(
            session_id=row["session_id"],
            user_id=row["user_id"],
            mode=row["mode"],
            locked_agent_id=row["locked_agent_id"],
            news_id=row["news_id"],
        )
