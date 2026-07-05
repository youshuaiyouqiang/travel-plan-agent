from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CreateItineraryRequest(BaseModel):
    title: str = Field(
        min_length=1,
        max_length=200,
        description="行程标题",
    )
    destination: str = Field(
        min_length=1,
        max_length=200,
        description="目的地",
    )
    start_date: str = Field(
        default="",
        description="开始日期",
    )
    end_date: str = Field(
        default="",
        description="结束日期",
    )
    session_id: str = Field(
        default="",
        description="会话ID",
    )
    budget: str = Field(
        default="",
        description="预算",
    )
    raw_content: str = Field(
        default="",
        description="原始内容",
    )
    status: str = Field(
        default="planning",
        description="行程状态",
    )
    days: list[dict] | None = Field(
        default=None,
        description="行程天数列表",
    )


class UpdateItineraryRequest(BaseModel):
    model_config = ConfigDict(extra="allow")


class CompareItinerariesRequest(BaseModel):
    ids: list[str | int] = Field(
        min_length=2,
        max_length=4,
        description="行程ID列表",
    )


class ConfirmPlanRequest(BaseModel):
    plan_type: str = Field(
        description="方案类型: sightseeing/budget",
    )
    itinerary_id: str = Field(
        default="",
        description="行程ID",
    )


class RevokeConfirmRequest(BaseModel):
    itinerary_id: str = Field(
        default="",
        description="行程ID",
    )


class CheckinActivityRequest(BaseModel):
    checked_in: bool = Field(
        default=True,
        description="是否打卡",
    )


class UpdateActivityCostRequest(BaseModel):
    actual_cost: float = Field(
        default=0,
        description="实际花费",
    )


class CreateShareLinkRequest(BaseModel):
    expires_at: str = Field(
        default="",
        description="过期时间",
    )


class UpdatePhotoRequest(BaseModel):
    description: str | None = Field(
        default=None,
        description="照片描述",
    )
    day_index: int | None = Field(
        default=None,
        description="天数索引",
    )
    tags: list[str] | None = Field(
        default=None,
        description="标签列表",
    )
