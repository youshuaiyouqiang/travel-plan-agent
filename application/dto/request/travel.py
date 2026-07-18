"""Task 2 — 旅行草稿编辑请求 DTO。

设计要点：
- 所有请求模型使用 ``ConfigDict(extra="forbid")``，拒绝多余字段以防止注入。
- ``EditActivityRequest`` 仅暴露可编辑字段；手工编辑字段记入草稿的 ``manual_edit_fields``。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CreateDraftRequest(BaseModel):
    """创建草稿请求。"""

    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(min_length=1, max_length=128)
    plan: dict


class EditActivityRequest(BaseModel):
    """手工编辑活动请求；仅允许可编辑字段，多余字段拒绝。"""

    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=200)
    time_slot: str | None = Field(default=None, max_length=64)
    location: str | None = Field(default=None, max_length=300)
    note: str | None = Field(default=None, max_length=1000)


class RefreshApplyRequest(BaseModel):
    """应用刷新预览中用户勾选的变更 ID 列表。"""

    model_config = ConfigDict(extra="forbid")
    change_ids: list[str] = Field(default_factory=list)
