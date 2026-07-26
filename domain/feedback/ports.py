"""对话质量反馈仓储端口。

P2.5 引入：将 ``quality_issues`` 表的访问从 domain 层下沉到 infrastructure，
领域层只消费此端口。

端口由消费方（domain）定义，由 ``infrastructure.persistence.repositories.feedback``
提供 ``SqliteFeedbackRepository`` 实现，在 ``init_db()`` 中装配默认实例。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class FeedbackRepositoryPort(Protocol):
    """``quality_issues`` 表的读写端口。

    实现必须保证：
    - 所有 SQL 参数化；
    - ``init_table`` 使用 ``CREATE TABLE IF NOT EXISTS``，幂等；
    - ``record`` 截断 ``message_snippet`` 至 500 字。
    """

    def init_table(self) -> None:
        """幂等建表（防御性；迁移已建表）。"""
        ...

    def record(
        self,
        *,
        session_id: str,
        user_id: str,
        rating: str,
        issue_type: str = "other",
        comment: str = "",
        agent_id: str = "",
        message_snippet: str = "",
    ) -> int:
        """记录一条反馈，返回记录 ID。"""
        ...

    def list_by_user(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """查询用户的反馈记录，按 created_at 倒序。"""
        ...

    def count_by_rating(self, rating: str = "bad") -> int:
        """统计某种评分的数量。"""
        ...


# ── 默认仓储装配（过渡方案，同 P2.1–P2.4）───────────────────

_default_repository: FeedbackRepositoryPort | None = None


def configure_default_feedback_repository(repository: FeedbackRepositoryPort) -> None:
    """注册全局默认反馈仓储（由组合根调用）。"""
    global _default_repository
    _default_repository = repository


def get_default_feedback_repository() -> FeedbackRepositoryPort:
    """获取全局默认反馈仓储；未配置时抛 RuntimeError。"""
    if _default_repository is None:
        raise RuntimeError(
            "FeedbackRepositoryPort 未配置：请在组合根调用 "
            "configure_default_feedback_repository() 或显式注入 repository 参数。"
        )
    return _default_repository
