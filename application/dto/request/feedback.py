from __future__ import annotations

from pydantic import BaseModel, Field


class FeedbackRequest(BaseModel):
    session_id: str = Field(
        min_length=1,
        description="会话ID",
    )
    rating: str = Field(
        default="bad",
        pattern=r"^(good|bad)$",
        description="评分: good/bad",
    )
    issue_type: str = Field(
        default="other",
        pattern=r"^(inaccurate|tool_error|delegation_error|other)$",
        description="问题类型",
    )
    comment: str = Field(
        default="",
        max_length=1000,
        description="评论",
    )
    agent_id: str = Field(
        default="",
        description="智能体ID",
    )
    message_snippet: str = Field(
        default="",
        max_length=500,
        description="消息片段",
    )
