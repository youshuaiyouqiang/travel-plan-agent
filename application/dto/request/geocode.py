from __future__ import annotations

from pydantic import BaseModel, Field


class BatchGeocodeRequest(BaseModel):
    addresses: list[str] = Field(
        min_length=1,
        max_length=20,
        description="地址列表",
    )


class IntlGeocodeRequest(BaseModel):
    address: str = Field(
        min_length=1,
        description="地址",
    )
    city: str = Field(
        default="",
        description="城市",
    )
