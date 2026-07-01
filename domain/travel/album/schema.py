from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass
class Photo:
    id: int = 0
    itinerary_id: str = ""
    user_id: str = ""
    file_name: str = ""
    file_size: int = 0
    mime_type: str = ""
    description: str = ""
    storage_path: str = ""
    thumbnail_path: str = ""
    day_index: int = 0
    tags: list[str] = None  # type: ignore[assignment]
    ai_description: str = ""
    latitude: float | None = None
    longitude: float | None = None
    is_cover: bool = False
    created_at: str = ""

    def __post_init__(self):
        if self.tags is None:
            self.tags = []

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "itinerary_id": self.itinerary_id,
            "user_id": self.user_id,
            "file_name": self.file_name,
            "file_size": self.file_size,
            "mime_type": self.mime_type,
            "description": self.description,
            "storage_path": self.storage_path,
            "thumbnail_path": self.thumbnail_path,
            "day_index": self.day_index,
            "tags": self.tags,
            "ai_description": self.ai_description,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "is_cover": self.is_cover,
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row: dict) -> Photo:
        tags_raw = row.get("tags", "[]")
        if isinstance(tags_raw, str):
            try:
                tags = json.loads(tags_raw)
            except (json.JSONDecodeError, ValueError):
                tags = []
        elif isinstance(tags_raw, list):
            tags = tags_raw
        else:
            tags = []

        lat = row.get("latitude")
        lng = row.get("longitude")

        return cls(
            id=row.get("id", 0),
            itinerary_id=row.get("itinerary_id", ""),
            user_id=row.get("user_id", ""),
            file_name=row.get("file_name", ""),
            file_size=int(row.get("file_size", 0)),
            mime_type=row.get("mime_type", ""),
            description=row.get("description", ""),
            storage_path=row.get("storage_path", ""),
            thumbnail_path=row.get("thumbnail_path", ""),
            day_index=int(row.get("day_index", 0)),
            tags=tags,
            ai_description=row.get("ai_description", ""),
            latitude=float(lat) if lat is not None else None,
            longitude=float(lng) if lng is not None else None,
            is_cover=bool(row.get("is_cover", 0)),
            created_at=row.get("created_at", ""),
        )
