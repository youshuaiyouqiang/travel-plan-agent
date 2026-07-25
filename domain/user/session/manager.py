from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from domain.user.session.ports import (
    SessionRepositoryPort,
    get_default_session_repository,
)
from domain.user.session.task_state import TaskStateStore


@dataclass
class Turn:
    role: str
    content: str
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class Session:
    session_id: str
    turns: list[Turn] = field(default_factory=list)
    summary: str = ""
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    disclosed_tools: list[str] = field(default_factory=list)
    delegation_agent_id: str | None = None
    delegation_started_at: float | None = None
    delegation_last_interaction: float | None = None
    user_id: str = ""
    # Task 1: 持久化会话模式与锚点
    mode: str = "yunhe_default"
    locked_agent_id: str | None = None
    news_id: str | None = None
    # P1-5：增量持久化标记，记录已写入数据库的 turn 数量。
    # 仅在持久化层使用，对外不可见；不参与比较与展示。
    _last_persisted_turn: int = field(default=0, repr=False, compare=False)

    def append(self, role: str, content: str) -> None:
        self.turns.append(Turn(role=role, content=content))
        self.updated_at = datetime.utcnow().isoformat()

    def recent_messages(self, limit: int) -> list[Turn]:
        return self.turns[-limit:]


class SessionManager:
    """会话管理器；通过 ``SessionRepositoryPort`` 访问持久化层。

    P2.1：原直连 ``get_connection()`` 的 SQL 已下沉到
    ``infrastructure.persistence.repositories.session.SqliteSessionRepository``。
    本类只负责会话的内存缓存、Redis 同步和业务逻辑编排。
    """

    def __init__(
        self,
        task_store: TaskStateStore | None = None,
        redis_store=None,
        repository: SessionRepositoryPort | None = None,
    ) -> None:
        self._repository = repository or get_default_session_repository()
        self._redis_store = redis_store
        self._sessions: dict[str, Session] = {}
        # 若未显式注入 task_store，则复用同一 repository 构造默认 TaskStateStore，
        # 保证 session 与 task 共享同一持久化后端。
        self._task_store = task_store or TaskStateStore(repository=self._repository)

    def get(self, session_id: str) -> Session:
        if session_id not in self._sessions:
            if self._redis_store:
                redis_session = self._redis_store.get(session_id)
                if redis_session:
                    self._sessions[session_id] = redis_session
                    return redis_session
            self._sessions[session_id] = self._load(session_id) or Session(session_id=session_id)
        return self._sessions[session_id]

    def save(self, session: Session, user_id: str = "") -> None:
        # 若显式传入 user_id 则覆盖 session.user_id（便于调用方在创建会话时即指定归属）
        if user_id:
            session.user_id = user_id
        self._repository.save_session(session)
        if self._redis_store:
            self._redis_store.save(session)

    def snapshot(self, session_id: str, *, user_id: str | None = None) -> dict | None:
        session = self.get(session_id)
        if not session:
            return None
        from dataclasses import asdict

        return {
            "session_id": session.session_id,
            "summary": session.summary,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "turns": [asdict(turn) for turn in session.turns],
            "task": self._task_store.snapshot(session_id, user_id=user_id or session_id),
        }

    # ===== 渐进式披露：disclosed_tools =====

    def get_disclosed_tools(self, session_id: str) -> list[str]:
        """获取会话中已披露的工具名列表。"""
        session = self.get(session_id)
        return session.disclosed_tools

    def set_disclosed_tools(self, session_id: str, tools: list[str]) -> None:
        """设置会话中已披露的工具名列表并持久化。"""
        session = self.get(session_id)
        session.disclosed_tools = list(tools)
        self.save(session)

    def add_disclosed_tool(self, session_id: str, tool_name: str) -> None:
        """添加一个已披露工具。"""
        session = self.get(session_id)
        if tool_name not in session.disclosed_tools:
            session.disclosed_tools.append(tool_name)
            self.save(session)

    # ===== 委派上下文（Phase 3 使用） =====

    def get_delegation(self, session_id: str) -> dict | None:
        """获取委派上下文。"""
        session = self.get(session_id)
        if not session.delegation_agent_id:
            return None
        return {
            "agent_id": session.delegation_agent_id,
            "started_at": session.delegation_started_at,
            "last_interaction": session.delegation_last_interaction,
        }

    def set_delegation(self, session_id: str, agent_id: str) -> None:
        """设置委派上下文。"""
        import time

        session = self.get(session_id)
        session.delegation_agent_id = agent_id
        session.delegation_started_at = time.time()
        session.delegation_last_interaction = time.time()
        self.save(session)

    def clear_delegation(self, session_id: str) -> None:
        """清除委派上下文。"""
        session = self.get(session_id)
        session.delegation_agent_id = None
        session.delegation_started_at = None
        session.delegation_last_interaction = None
        self.save(session)

    # ===== 列表与删除（供 Agent 委派，P2.1 收敛 infra 导入）=====

    def list_user_sessions(self, user_id: str) -> list[dict[str, Any]]:
        """列出用户的所有会话（按 updated_at 倒序）。"""
        return self._repository.list_sessions_by_user(user_id)

    def delete_session(self, session_id: str) -> None:
        """级联删除会话并清理内存缓存。"""
        self._repository.delete_session(session_id)
        self._sessions.pop(session_id, None)
        self._task_store._tasks.pop(session_id, None)

    # ===== 内部辅助 =====

    def _load(self, session_id: str) -> Session | None:
        return self._repository.load_session(session_id)


SessionStore = SessionManager
