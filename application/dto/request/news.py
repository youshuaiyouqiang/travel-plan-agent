from __future__ import annotations

from pydantic import BaseModel, Field


class NewsFavoriteRequest(BaseModel):
    """新闻收藏请求。

    业务红线：不保存新闻全文；收藏仅保存标题、来源、URL、摘要、标签与时间。
    """

    title: str = Field(
        min_length=1,
        max_length=200,
        description="新闻标题",
    )
    summary: str = Field(
        default="",
        max_length=500,
        description="新闻摘要",
    )
    url: str = Field(
        default="",
        max_length=1000,
        description="新闻链接",
    )
    source: str = Field(
        default="",
        max_length=32,
        description="新闻来源",
    )
    tag: str = Field(
        default="",
        max_length=32,
        description="新闻标签",
    )
