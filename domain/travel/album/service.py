from __future__ import annotations

import io
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

from config import settings
from domain.travel.album.schema import Photo
from domain.travel.album.repository import AlbumRepository

logger = logging.getLogger(__name__)

ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
THUMB_MAX_SIZE = 300


def _extract_exif(file_bytes: bytes) -> dict:
    """从图片字节中提取 EXIF 信息（GPS、拍摄时间等）。"""
    result: dict = {"latitude": None, "longitude": None, "taken_at": None}
    try:
        from PIL import Image
        from PIL.ExifTags import GPSTAGS, TAGS

        img = Image.open(io.BytesIO(file_bytes))
        exif_data = img._getexif()
        if not exif_data:
            return result

        gps_info: dict = {}
        for tag_id, value in exif_data.items():
            tag = TAGS.get(tag_id, tag_id)
            if tag == "GPSInfo":
                for gps_tag_id in value:
                    gps_tag = GPSTAGS.get(gps_tag_id, gps_tag_id)
                    gps_info[gps_tag] = value[gps_tag_id]
            elif tag == "DateTimeOriginal":
                result["taken_at"] = str(value)

        # 解析 GPS
        if gps_info:
            lat = _convert_to_degrees(gps_info.get("GPSLatitude"))
            lng = _convert_to_degrees(gps_info.get("GPSLongitude"))
            if lat is not None and lng is not None:
                if gps_info.get("GPSLatitudeRef", "N") == "S":
                    lat = -lat
                if gps_info.get("GPSLongitudeRef", "E") == "W":
                    lng = -lng
                result["latitude"] = lat
                result["longitude"] = lng
    except Exception as e:
        logger.debug("EXIF extraction failed: %s", e)
    return result


def _convert_to_degrees(value) -> float | None:
    """将 GPS 坐标从度分秒转为十进制度数。"""
    try:
        d, m, s = value
        return float(d) + float(m) / 60.0 + float(s) / 3600.0
    except (TypeError, ValueError):
        return None


def _match_day_index(taken_at: str | None, itinerary_id: str) -> int:
    """根据照片拍摄时间和行程日期匹配 day_index。"""
    if not taken_at:
        return 0
    try:
        from infra.db import get_connection
        conn = get_connection()
        row = conn.execute(
            "SELECT start_date FROM itineraries WHERE id = ?",
            (itinerary_id,),
        ).fetchone()
        if not row or not row["start_date"]:
            return 0
        start = datetime.fromisoformat(row["start_date"])
        # EXIF 日期格式: "2026:06:03 10:00:00"
        taken_str = taken_at.replace(":", "-", 2)
        taken = datetime.fromisoformat(taken_str)
        delta = (taken.date() - start.date()).days
        return max(0, delta + 1) if delta >= 0 else 0
    except Exception:
        return 0


async def _generate_ai_description(file_bytes: bytes, mime_type: str) -> tuple[str, list[str]]:
    """调用多模态模型生成照片描述和标签。"""
    try:
        import base64
        from openai import AsyncOpenAI

        api_key = settings.api_key or ""
        if not api_key:
            return "", []

        client = AsyncOpenAI(api_key=api_key, base_url=settings.base_url)
        b64 = base64.b64encode(file_bytes).decode()
        data_url = f"data:{mime_type};base64,{b64}"

        response = await client.chat.completions.create(
            model=settings.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        },
                        {
                            "type": "text",
                            "text": (
                                "请用中文简要描述这张旅行照片的内容（一句话），"
                                "并提取3-5个标签关键词。"
                                "严格返回JSON格式：{\"description\": \"...\", \"tags\": [\"标签1\", \"标签2\"]}"
                            ),
                        },
                    ],
                }
            ],
            max_tokens=200,
        )
        text = response.choices[0].message.content or ""
        # 解析 JSON
        import re
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            desc = str(data.get("description", ""))
            tags = [str(t) for t in data.get("tags", [])]
            return desc, tags
    except Exception as e:
        logger.warning("AI description generation failed: %s", e)
    return "", []


class AlbumService:

    def __init__(self):
        self.repo = AlbumRepository()
        self.album_dir = settings.data_dir / "album"
        self.album_dir.mkdir(parents=True, exist_ok=True)

    async def upload(self, *, itinerary_id: str, user_id: str,
                     file_name: str, file_bytes: bytes, mime_type: str,
                     description: str = "", day_index: int = 0) -> Photo:
        if mime_type not in ALLOWED_MIME:
            raise ValueError(f"不支持的文件类型: {mime_type}")
        if len(file_bytes) > MAX_FILE_SIZE:
            raise ValueError("文件大小超过 10MB 限制")

        # 验证图片合法性
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(file_bytes))
            img.verify()
        except Exception:
            raise ValueError("文件不是有效的图片")
        # 重新打开用于后续操作（verify 后需重新加载）
        try:
            from PIL import Image as PILImage
            PILImage.open(io.BytesIO(file_bytes))
        except Exception:
            raise ValueError("文件不是有效的图片")

        ext = self._mime_to_ext(mime_type)
        uid = uuid.uuid4().hex[:16]
        storage_name = f"{uid}{ext}"
        storage_path = self.album_dir / storage_name
        storage_path.write_bytes(file_bytes)

        thumb_name = f"thumb_{uid}{ext}"
        thumb_path = self.album_dir / thumb_name
        self._create_thumbnail(storage_path, thumb_path)

        # 提取 EXIF 信息
        exif = _extract_exif(file_bytes)
        latitude = exif.get("latitude")
        longitude = exif.get("longitude")

        # 匹配行程天数
        if day_index <= 0:
            day_index = _match_day_index(exif.get("taken_at"), itinerary_id)

        # AI 描述和标签（异步）
        ai_desc, tags = await _generate_ai_description(file_bytes, mime_type)

        # 如果用户没提供描述，使用 AI 描述
        final_description = description or ai_desc

        return self.repo.add_photo(
            itinerary_id=itinerary_id,
            user_id=user_id,
            file_name=file_name,
            file_size=len(file_bytes),
            mime_type=mime_type,
            storage_path=storage_name,
            thumbnail_path=thumb_name,
            description=final_description,
            day_index=day_index,
            tags=tags,
            ai_description=ai_desc,
            latitude=latitude,
            longitude=longitude,
        )

    def delete(self, photo_id: int, user_id: str) -> bool:
        photo = self.repo.get_photo(photo_id)
        if not photo:
            raise ValueError("照片不存在")
        if photo.user_id != user_id:
            raise PermissionError("无权删除此照片")

        # 删除磁盘文件
        for path_attr in ("storage_path", "thumbnail_path"):
            rel = getattr(photo, path_attr, "")
            if rel:
                full = settings.data_dir / "album" / rel
                if full.exists():
                    full.unlink()

        return self.repo.delete_photo(photo_id)

    def list_photos(self, itinerary_id: str, day_index: int | None = None) -> list[Photo]:
        return self.repo.list_photos(itinerary_id, day_index)

    def set_cover(self, itinerary_id: str, photo_id: int) -> Photo:
        self.repo.set_cover(itinerary_id, photo_id)
        photo = self.repo.get_photo(photo_id)
        if not photo:
            raise ValueError("照片不存在")
        return photo

    def update_photo(self, photo_id: int, *, description: str | None = None,
                     day_index: int | None = None, tags: list[str] | None = None) -> bool:
        return self.repo.update_photo(photo_id, description=description,
                                      day_index=day_index, tags=tags)

    def get_all_tags(self, itinerary_id: str) -> list[str]:
        return self.repo.get_all_tags(itinerary_id)

    def list_photos_by_tag(self, itinerary_id: str, tag: str) -> list[Photo]:
        return self.repo.list_photos_by_tag(itinerary_id, tag)

    def get_photos_with_location(self, itinerary_id: str) -> list[Photo]:
        return self.repo.get_photos_with_location(itinerary_id)

    async def generate_travelogue(self, itinerary_id: str) -> str:
        """根据行程安排和照片生成图文游记。"""
        from infra.db import get_connection
        from core.llm import OpenAILLM

        conn = get_connection()
        itin_row = conn.execute(
            "SELECT * FROM itineraries WHERE id = ?", (itinerary_id,)
        ).fetchone()
        if not itin_row:
            raise ValueError("行程不存在")

        # 获取行程天数和活动
        days_rows = conn.execute(
            "SELECT * FROM itinerary_days WHERE itinerary_id = ? ORDER BY day_index",
            (itinerary_id,),
        ).fetchall()

        itinerary_text = ""
        for day in days_rows:
            day_id = day["id"]
            acts = conn.execute(
                "SELECT * FROM itinerary_activities WHERE day_id = ? ORDER BY activity_index",
                (day_id,),
            ).fetchall()
            itinerary_text += f"\n第{day['day_index']}天（{day['date']}）：{day['title']}\n"
            for act in acts:
                itinerary_text += f"  - {act['time_slot']} {act['title']}（{act['location']}）\n"

        # 获取照片信息
        photos = self.repo.list_photos(itinerary_id)
        photo_descriptions = []
        for p in photos:
            desc = p.ai_description or p.description or p.file_name
            # day_index=0 表示未关联天数，归入第1天
            day_idx = p.day_index if p.day_index > 0 else 1
            photo_descriptions.append(f"- [第{day_idx}天] 【photo:{p.id}】{desc}")

        photos_text = "\n".join(photo_descriptions) if photo_descriptions else "暂无照片"

        prompt = (
            "你是一位旅行游记作者。请根据以下行程安排和照片描述，生成一篇生动的图文游记。\n"
            "要求：\n"
            "- 用第一人称，像发朋友圈一样自然\n"
            "- 按天组织内容，每天一段\n"
            "- 在合适的位置插入照片标记，格式必须严格保持为 【photo:照片ID】（不要替换为文字描述）\n"
            "- 包含感受、小贴士、美食推荐等\n"
            "- 风格轻松有趣，不要太正式\n\n"
            f"行程安排：\n{itinerary_text}\n\n"
            f"照片描述：\n{photos_text}"
        )

        llm = OpenAILLM()
        result = await llm.complete(
            system="你是一位旅行游记作者，擅长写生动有趣的旅行分享。",
            messages=[{"role": "user", "content": prompt}],
        )
        return result

    def _create_thumbnail(self, src: Path, dst: Path) -> None:
        try:
            from PIL import Image
            img = Image.open(src)
            img.thumbnail((THUMB_MAX_SIZE, THUMB_MAX_SIZE))
            img.save(dst)
        except Exception as e:
            logger.warning("缩略图生成失败: %s", e)

    @staticmethod
    def _mime_to_ext(mime: str) -> str:
        return {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(mime, ".jpg")
