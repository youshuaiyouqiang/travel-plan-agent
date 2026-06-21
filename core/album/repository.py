from __future__ import annotations

import json
import logging
from datetime import datetime

from infra.db import get_connection
from core.album.schema import Photo

logger = logging.getLogger(__name__)


class AlbumRepository:

    def add_photo(self, *, itinerary_id: str, user_id: str,
                  file_name: str, file_size: int, mime_type: str,
                  storage_path: str, thumbnail_path: str,
                  description: str = "", day_index: int = 0,
                  tags: list[str] | None = None,
                  ai_description: str = "",
                  latitude: float | None = None,
                  longitude: float | None = None,
                  is_cover: bool = False) -> Photo:
        conn = get_connection()
        now = datetime.utcnow().isoformat()
        tags_json = json.dumps(tags or [], ensure_ascii=False)
        conn.execute(
            "INSERT INTO album_photos "
            "(itinerary_id, user_id, file_name, file_size, mime_type, "
            "description, storage_path, thumbnail_path, day_index, "
            "tags, ai_description, latitude, longitude, is_cover, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (itinerary_id, user_id, file_name, file_size, mime_type,
             description, storage_path, thumbnail_path, day_index,
             tags_json, ai_description, latitude, longitude,
             1 if is_cover else 0, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM album_photos WHERE rowid = last_insert_rowid()").fetchone()
        return Photo.from_row(dict(row)) if row else Photo()

    def get_photo(self, photo_id: int) -> Photo | None:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM album_photos WHERE id = ?", (photo_id,)
        ).fetchone()
        if not row:
            return None
        return Photo.from_row(dict(row))

    def list_photos(self, itinerary_id: str, day_index: int | None = None) -> list[Photo]:
        conn = get_connection()
        if day_index is not None and day_index > 0:
            rows = conn.execute(
                "SELECT * FROM album_photos WHERE itinerary_id = ? AND day_index = ? ORDER BY created_at DESC",
                (itinerary_id, day_index),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM album_photos WHERE itinerary_id = ? ORDER BY day_index, created_at DESC",
                (itinerary_id,),
            ).fetchall()
        return [Photo.from_row(dict(r)) for r in rows]

    def delete_photo(self, photo_id: int) -> bool:
        conn = get_connection()
        cursor = conn.execute(
            "DELETE FROM album_photos WHERE id = ?", (photo_id,)
        )
        conn.commit()
        return cursor.rowcount > 0

    def count_photos(self, itinerary_id: str) -> int:
        conn = get_connection()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM album_photos WHERE itinerary_id = ?",
            (itinerary_id,),
        ).fetchone()
        return row["cnt"] if row else 0

    def set_cover(self, itinerary_id: str, photo_id: int) -> None:
        conn = get_connection()
        conn.execute(
            "UPDATE album_photos SET is_cover = 0 WHERE itinerary_id = ?",
            (itinerary_id,),
        )
        conn.execute(
            "UPDATE album_photos SET is_cover = 1 WHERE id = ? AND itinerary_id = ?",
            (photo_id, itinerary_id),
        )
        conn.commit()

    def get_cover(self, itinerary_id: str) -> Photo | None:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM album_photos WHERE itinerary_id = ? AND is_cover = 1",
            (itinerary_id,),
        ).fetchone()
        return Photo.from_row(dict(row)) if row else None

    def update_photo(self, photo_id: int, *, description: str | None = None,
                     day_index: int | None = None, tags: list[str] | None = None) -> bool:
        conn = get_connection()
        sets: list[str] = []
        params: list = []
        if description is not None:
            sets.append("description = ?")
            params.append(description)
        if day_index is not None:
            sets.append("day_index = ?")
            params.append(day_index)
        if tags is not None:
            sets.append("tags = ?")
            params.append(json.dumps(tags, ensure_ascii=False))
        if not sets:
            return False
        params.append(photo_id)
        conn.execute(f"UPDATE album_photos SET {', '.join(sets)} WHERE id = ?", params)
        conn.commit()
        return True

    def get_all_tags(self, itinerary_id: str) -> list[str]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT tags FROM album_photos WHERE itinerary_id = ? AND tags != '[]'",
            (itinerary_id,),
        ).fetchall()
        tag_set: set[str] = set()
        for row in rows:
            try:
                tags = json.loads(row["tags"])
                tag_set.update(tags)
            except (json.JSONDecodeError, ValueError):
                pass
        return sorted(tag_set)

    def list_photos_by_tag(self, itinerary_id: str, tag: str) -> list[Photo]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM album_photos WHERE itinerary_id = ? ORDER BY day_index, created_at DESC",
            (itinerary_id,),
        ).fetchall()
        result = []
        for r in rows:
            photo = Photo.from_row(dict(r))
            if tag in (photo.tags or []):
                result.append(photo)
        return result

    def get_photos_with_location(self, itinerary_id: str) -> list[Photo]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM album_photos WHERE itinerary_id = ? AND latitude IS NOT NULL AND longitude IS NOT NULL ORDER BY day_index, created_at",
            (itinerary_id,),
        ).fetchall()
        return [Photo.from_row(dict(r)) for r in rows]
