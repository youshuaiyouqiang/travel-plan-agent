from __future__ import annotations

import logging

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse as FastAPIFileResponse

from application.dto.request.itinerary import UpdatePhotoRequest
from application.exceptions import (
    ForbiddenException,
    NotFoundException,
    UnauthorizedException,
    ValidationException,
)
from config import settings
from domain.travel.album.service import AlbumService
from domain.travel.itinerary.repository import ItineraryRepository
from domain.user.auth.token import verify_token

logger = logging.getLogger(__name__)

# 照片路由（挂载时 prefix="/itineraries"）
router = APIRouter()

# 相册文件服务路由（挂载时 prefix="/album"）
album_serve_router = APIRouter()

_itinerary_repo = ItineraryRepository()
_album_service = AlbumService()


def _user_owns_itinerary(user_id: str, itin) -> bool:
    """检查用户是否拥有该行程的所有权。"""
    if itin.user_id and itin.user_id == user_id:
        return True
    if itin.session_id:
        from infrastructure.persistence.database import get_connection
        conn = get_connection()
        row = conn.execute(
            "SELECT 1 FROM tasks WHERE user_id = ? AND session_id = ? LIMIT 1",
            (user_id, itin.session_id),
        ).fetchone()
        if row:
            return True
    if itin.user_id:
        from domain.user.auth.auth import UserStore
        us = UserStore()
        existing = us.get_by_id(itin.user_id)
        if not existing:
            return True
    return False


@router.post("/{itinerary_id}/photos")
async def upload_photos(
    itinerary_id: str,
    request: Request,
    files: list[UploadFile] = File(...),
    description: str = Form(""),
    day_index: int = Form(0),
):
    user_id: str | None = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    itin = _itinerary_repo.get_itinerary(itinerary_id)
    if not itin or not _user_owns_itinerary(user_id, itin):
        raise NotFoundException("行程", itinerary_id)

    photos = []
    for f in files:
        file_bytes = await f.read()
        try:
            photo = await _album_service.upload(
                itinerary_id=itinerary_id,
                user_id=user_id,
                file_name=f.filename or "",
                file_bytes=file_bytes,
                mime_type=f.content_type or "image/jpeg",
                description=description,
                day_index=day_index,
            )
            photos.append(photo.to_dict())
        except ValueError as e:
            raise ValidationException(str(e))
    return {"photos": photos}


@router.get("/{itinerary_id}/photos")
async def list_photos(
    itinerary_id: str,
    request: Request,
    day_index: int = 0,
    tag: str = "",
):
    user_id: str | None = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    if tag:
        photos = _album_service.list_photos_by_tag(itinerary_id, tag)
    elif day_index > 0:
        photos = _album_service.list_photos(itinerary_id, day_index)
    else:
        photos = _album_service.list_photos(itinerary_id)

    tags = _album_service.get_all_tags(itinerary_id)
    cover = _album_service.repo.get_cover(itinerary_id)

    return {
        "itinerary_id": itinerary_id,
        "photos": [p.to_dict() for p in photos],
        "total": len(photos),
        "tags": tags,
        "cover": cover.to_dict() if cover else None,
    }


@router.delete("/{itinerary_id}/photos/{photo_id}")
async def delete_photo(itinerary_id: str, photo_id: int, request: Request):
    user_id: str | None = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    try:
        _album_service.delete(photo_id, user_id)
    except ValueError:
        raise NotFoundException("照片", photo_id)
    except PermissionError:
        raise ForbiddenException("无权删除此照片")
    return {"detail": "已删除"}


@router.patch("/{itinerary_id}/photos/{photo_id}")
async def update_photo(
    itinerary_id: str,
    photo_id: int,
    req: UpdatePhotoRequest,
    request: Request,
):
    user_id: str | None = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    _album_service.update_photo(
        photo_id,
        description=req.description,
        day_index=req.day_index,
        tags=req.tags,
    )
    photo = _album_service.repo.get_photo(photo_id)
    if not photo:
        raise NotFoundException("照片", photo_id)
    return photo.to_dict()


@router.post("/{itinerary_id}/photos/{photo_id}/cover")
async def set_cover(itinerary_id: str, photo_id: int, request: Request):
    user_id: str | None = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    try:
        photo = _album_service.set_cover(itinerary_id, photo_id)
        return photo.to_dict()
    except ValueError as e:
        raise ValidationException(str(e))


@router.get("/{itinerary_id}/photos/map")
async def get_photo_locations(itinerary_id: str, request: Request):
    user_id: str | None = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    photos = _album_service.get_photos_with_location(itinerary_id)
    return {
        "itinerary_id": itinerary_id,
        "markers": [
            {
                "photo_id": p.id,
                "latitude": p.latitude,
                "longitude": p.longitude,
                "description": p.ai_description or p.description or p.file_name,
                "day_index": p.day_index,
                "thumbnail_path": p.thumbnail_path,
            }
            for p in photos
        ],
    }


@router.post("/{itinerary_id}/travelogue")
async def generate_travelogue(itinerary_id: str, request: Request):
    user_id: str | None = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    try:
        content = await _album_service.generate_travelogue(itinerary_id)
        return {"itinerary_id": itinerary_id, "content": content}
    except ValueError as e:
        raise ValidationException(str(e))


@album_serve_router.get("/{file_path:path}")
async def serve_album_image(file_path: str, request: Request):
    # P0-6：<img> 标签无法携带 Authorization header，本端点跳过全局中间件，
    # 此处自行校验 query token。建议未来引入一次性 token 或短时效 token。
    user_id: str | None = getattr(request.state, "user_id", None)
    if not user_id:
        token = request.query_params.get("token", "")
        if token:
            user_id = verify_token(token)
    if not user_id:
        raise UnauthorizedException()

    full_path = settings.data_dir / "album" / file_path
    if not full_path.exists():
        raise NotFoundException("文件", file_path)
    return FastAPIFileResponse(str(full_path))
