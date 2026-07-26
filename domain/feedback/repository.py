"""对话质量反馈 — 👍/👎 + quality_issues 持久化。

社会版核心：反馈是产品迭代的重要数据来源。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from domain.feedback.ports import (
    FeedbackRepositoryPort,
    get_default_feedback_repository,
)


@dataclass
class QualityIssue:
    """质量问题记录。"""

    id: int | None = None
    session_id: str = ""
    user_id: str = ""
    rating: str = ""  # "good" | "bad"
    issue_type: str = ""  # "inaccurate" | "tool_error" | "delegation_error" | "other"
    comment: str = ""  # 用户文字反馈
    agent_id: str = ""  # 涉及智能体
    message_snippet: str = ""  # 用户消息片段
    created_at: str = ""


class FeedbackRepository:
    """反馈数据仓储；通过 ``FeedbackRepositoryPort`` 访问持久化层。

    P2.5：原直连 ``get_connection()`` 的 SQL 已下沉到
    ``infrastructure.persistence.repositories.feedback.SqliteFeedbackRepository``。
    本类只负责委托持久化操作，保持既有调用方的无参构造兼容。
    """

    def __init__(self, repository: FeedbackRepositoryPort | None = None) -> None:
        self._repository = repository or get_default_feedback_repository()

    def init_table(self) -> None:
        self._repository.init_table()

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
        """记录一条反馈。返回记录 ID。"""
        return self._repository.record(
            session_id=session_id,
            user_id=user_id,
            rating=rating,
            issue_type=issue_type,
            comment=comment,
            agent_id=agent_id,
            message_snippet=message_snippet,
        )

    def list_by_user(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """查询用户的反馈记录。"""
        return self._repository.list_by_user(user_id, limit)

    def count_by_rating(self, rating: str = "bad") -> int:
        """统计某种评分的数量。"""
        return self._repository.count_by_rating(rating)
