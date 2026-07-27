"""会话与任务状态的持久化端口。

P2.1 引入：将 ``sessions`` / ``session_turns`` / ``tasks`` 三张表的访问从
domain/application 层下沉到 infrastructure，领域层只消费此端口。

端口由消费方（domain）定义，由 ``infrastructure.persistence.repositories.session``
提供 SQLite 实现，在组合根（``app.py`` 的 ``build_orchestrator``）或 ``init_db()``
中装配。测试可用 fake 实现替代，不创建 SQLite 文件。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:  # 避免循环导入；Protocol 仅用于静态类型检查
    from domain.user.session.manager import Session
    from domain.user.session.task_state import TaskRecord


@runtime_checkable
class SessionRepositoryPort(Protocol):
    """会话与任务状态的读写端口。

    涵盖三类操作：
    1. ``Session`` 聚合（``sessions`` + ``session_turns`` 表）：完整会话的加载与持久化。
    2. 会话模式记录（``sessions`` 表的模式/锁定字段）：供 ``SessionService`` 使用。
    3. ``TaskRecord``（``tasks`` 表）：任务状态的加载与持久化。

    实现必须保证：
    - 所有 SQL 参数化，表名来自硬编码白名单；
    - ``save_session`` 支持增量 turn 插入（由 ``Session._last_persisted_turn`` 标记）；
    - 资源不存在时返回 ``None`` 或空列表，由应用层决定 404 语义。
    """

    # ── Session 聚合 ────────────────────────────────────────

    def save_session(self, session: Session) -> None:
        """Upsert 会话行并增量插入未持久化的 turns。"""
        ...

    def load_session(self, session_id: str) -> Session | None:
        """加载会话及其全部 turns；不存在返回 None。"""
        ...

    # ── 会话模式记录（供 SessionService）────────────────────

    def create_session_row(
        self,
        *,
        session_id: str,
        user_id: str,
        mode: str,
        locked_agent_id: str | None,
        news_id: str | None,
    ) -> None:
        """新建会话行并同步插入 tasks 行（list_by_user 依赖 user_id 过滤）。"""
        ...

    def get_session_record(self, session_id: str) -> dict[str, Any] | None:
        """读取会话的模式/锁定字段；不存在返回 None。

        返回 dict 含 ``session_id``/``user_id``/``mode``/``locked_agent_id``/``news_id``。
        """
        ...

    def update_session_mode(
        self,
        *,
        session_id: str,
        mode: str,
        locked_agent_id: str | None,
        news_id: str | None,
    ) -> None:
        """更新会话模式与锁定字段。"""
        ...

    # ── 方案确认（P3.3b 引入，供 ConfirmPlanService 使用）─────────

    def get_confirmed_plan(self, session_id: str) -> dict[str, Any] | None:
        """读取会话的 ``confirmed_plan`` / ``confirmed_at`` 字段。

        Returns:
            含 ``confirmed_plan`` 与 ``confirmed_at`` 的 dict；会话不存在
            或字段为 NULL 时对应值为 ``None``。会话行不存在时整体返回 ``None``。
        """
        ...

    def set_confirmed_plan(self, *, session_id: str, plan_type: str, now: str) -> None:
        """更新会话的 ``confirmed_plan`` 与 ``confirmed_at``。"""
        ...

    def clear_confirmed_plan(self, session_id: str) -> None:
        """清空会话的 ``confirmed_plan`` 与 ``confirmed_at``（置 NULL）。"""
        ...

    # ── 列表与消息 ──────────────────────────────────────────

    def list_sessions_by_user(self, user_id: str) -> list[dict[str, Any]]:
        """列出用户的所有会话，按 updated_at 倒序。"""
        ...

    def find_session_ids_by_user(self, user_id: str) -> list[str]:
        """列出用户在 ``tasks`` 表中的去重 ``session_id``（排除空字符串）。

        P3.3b 引入：供 ``api/v1/itinerary.py`` 的 ``list_itineraries`` 路由
        查找用户关联会话，避免 api 层直接查询 ``tasks`` 表。
        """
        ...

    def get_session_messages(self, session_id: str) -> list[dict[str, Any]]:
        """按时间顺序返回会话的所有消息。"""
        ...

    def get_recent_assistant_turns(
        self, session_id: str, *, limit: int = 20
    ) -> list[dict[str, Any]]:
        """按 turn_index 倒序返回最近的 ``limit`` 条 assistant 消息。

        P7 引入：供 ``domain.travel.tools.generate_itinerary_overview`` 在
        tool handler 中按反向顺序扫描最近 assistant 内容以提取行程内容；
        替代之前直接 ``SELECT ... FROM session_turns`` 的内联 SQL。
        """
        ...

    def get_user_id_by_session(self, session_id: str) -> str | None:
        """按 ``session_id`` 从 ``tasks`` 表查 ``user_id``；不存在返回 None。

        P7 引入：供 ``domain.travel.tools.generate_itinerary_overview`` 在
        tool handler 中推断 user_id；替代之前直接 ``SELECT user_id FROM tasks``
        的内联 SQL。
        """
        ...

    # ── 删除 ────────────────────────────────────────────────

    def delete_session(self, session_id: str) -> None:
        """级联删除会话：session_turns → sessions → tasks。"""
        ...

    # ── Task 状态 ───────────────────────────────────────────

    def save_task(self, task: TaskRecord) -> None:
        """Upsert 任务状态行。"""
        ...

    def load_task(self, session_id: str) -> TaskRecord | None:
        """加载任务状态；不存在返回 None。"""
        ...


# ── 默认仓储装配（过渡方案）─────────────────────────────────
#
# 组合根（``app.py``）或 ``init_db()`` 在初始化数据库后调用
# ``configure_default_session_repository()`` 注册 SQLite 实现。
# domain/application 消费者在未显式注入时回退到此默认值，
# 从而保持既有测试的 ``SessionManager()`` / ``SessionService()``
# 无参构造兼容。P3 收敛组合根后，路由改为从容器取服务，此全局
# 变量可移除。

_default_repository: SessionRepositoryPort | None = None


def configure_default_session_repository(repository: SessionRepositoryPort) -> None:
    """注册全局默认会话仓储（由组合根调用）。"""
    global _default_repository
    _default_repository = repository


def get_default_session_repository() -> SessionRepositoryPort:
    """获取全局默认会话仓储；未配置时抛 RuntimeError。"""
    if _default_repository is None:
        raise RuntimeError(
            "SessionRepositoryPort 未配置：请在组合根调用 "
            "configure_default_session_repository() 或显式注入 repository 参数。"
        )
    return _default_repository
