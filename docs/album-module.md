# 相册管理模块 — 开发文档

## 1. 模块概述

为 Claw 旅行助手新增「相册管理」模块，允许用户上传、浏览、删除旅行照片。每张照片关联到具体行程（itinerary），支持按行程分组查看。

---

## 2. 功能需求

| 功能 | 说明 |
|------|------|
| 上传照片 | 用户可为某个行程上传一张或多张照片，支持 JPG/PNG/WEBP，单文件上限 10MB |
| 浏览相册 | 按行程维度查看照片列表，支持缩略图 + 原图两级展示 |
| 删除照片 | 用户可删除自己上传的照片（单张或批量） |
| 照片信息 | 每张照片记录：所属行程、上传时间、文件名、文件大小、描述（可选） |

---

## 3. 数据库设计

在 `infra/db.py` 的 `_SCHEMA` 中新增表：

```sql
CREATE TABLE IF NOT EXISTS album_photos (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    itinerary_id  TEXT NOT NULL,
    user_id       TEXT NOT NULL,
    file_name     TEXT NOT NULL DEFAULT '',
    file_size     INTEGER NOT NULL DEFAULT 0,
    mime_type     TEXT NOT NULL DEFAULT '',
    description   TEXT NOT NULL DEFAULT '',
    storage_path  TEXT NOT NULL DEFAULT '',   -- 本地磁盘相对路径
    thumbnail_path TEXT NOT NULL DEFAULT '',   -- 缩略图相对路径
    created_at    TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (itinerary_id) REFERENCES itineraries(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_photos_itinerary ON album_photos(itinerary_id);
CREATE INDEX IF NOT EXISTS idx_photos_user ON album_photos(user_id);
```

**字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 自增主键 |
| itinerary_id | TEXT | 关联行程 ID，外键关联 itineraries 表，级联删除 |
| user_id | TEXT | 上传者用户 ID |
| file_name | TEXT | 原始文件名 |
| file_size | INTEGER | 文件字节数 |
| mime_type | TEXT | MIME 类型，如 `image/jpeg` |
| description | TEXT | 照片描述（可选） |
| storage_path | TEXT | 原图在磁盘上的相对路径，如 `album/abc123.jpg` |
| thumbnail_path | TEXT | 缩略图相对路径，如 `album/thumb_abc123.jpg` |
| created_at | TEXT | 上传时间 |

---

## 4. 文件存储方案

| 项目 | 方案 |
|------|------|
| 存储根目录 | `settings.data_dir / "album"`，即 `data/album/` |
| 文件命名 | `{uuid_hex}{ext}`，如 `a1b2c3d4e5f6.jpg` |
| 缩略图命名 | `thumb_{uuid_hex}{ext}` |
| 缩略图规格 | 最大边 300px，等比缩放，使用 Pillow |
| 单文件上限 | 10MB |
| 允许格式 | `image/jpeg`、`image/png`、`image/webp` |

---

## 5. 后端设计

### 5.1 新增文件结构

```
core/
  album/
    __init__.py
    schema.py        # Photo 数据类
    repository.py   # 数据库操作
    service.py      # 文件存储 + 缩略图生成逻辑
```

### 5.2 Schema（`core/album/schema.py`）

```python
from __future__ import annotations
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
    created_at: str = ""

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
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row: dict) -> Photo:
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
            created_at=row.get("created_at", ""),
        )
```

### 5.3 Repository（`core/album/repository.py`）

```python
from __future__ import annotations
import logging
from datetime import datetime
from infra.db import get_connection
from core.album.schema import Photo

logger = logging.getLogger(__name__)


class AlbumRepository:

    def add_photo(self, itinerary_id: str, user_id: str,
                  file_name: str, file_size: int, mime_type: str,
                  storage_path: str, thumbnail_path: str,
                  description: str = "") -> Photo:
        conn = get_connection()
        now = datetime.utcnow().isoformat()
        cursor = conn.execute(
            "INSERT INTO album_photos "
            "(itinerary_id, user_id, file_name, file_size, mime_type, "
            "description, storage_path, thumbnail_path, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (itinerary_id, user_id, file_name, file_size, mime_type,
             description, storage_path, thumbnail_path, now),
        )
        conn.commit()
        return Photo(
            id=cursor.lastrowid,
            itinerary_id=itinerary_id,
            user_id=user_id,
            file_name=file_name,
            file_size=file_size,
            mime_type=mime_type,
            description=description,
            storage_path=storage_path,
            thumbnail_path=thumbnail_path,
            created_at=now,
        )

    def get_photo(self, photo_id: int) -> Photo | None:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM album_photos WHERE id = ?", (photo_id,)
        ).fetchone()
        if not row:
            return None
        return Photo.from_row(dict(row))

    def list_photos(self, itinerary_id: str) -> list[Photo]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM album_photos WHERE itinerary_id = ? ORDER BY created_at DESC",
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
```

### 5.4 Service（`core/album/service.py`）

```python
from __future__ import annotations

import uuid
import logging
from pathlib import Path

from PIL import Image
from config import settings
from core.album.schema import Photo
from core.album.repository import AlbumRepository

logger = logging.getLogger(__name__)

ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
THUMB_MAX_SIZE = 300


class AlbumService:

    def __init__(self):
        self.repo = AlbumRepository()
        self.album_dir = settings.data_dir / "album"
        self.album_dir.mkdir(parents=True, exist_ok=True)

    def upload(self, itinerary_id: str, user_id: str,
               file_name: str, file_bytes: bytes, mime_type: str,
               description: str = "") -> Photo:
        if mime_type not in ALLOWED_MIME:
            raise ValueError(f"不支持的文件类型: {mime_type}")
        if len(file_bytes) > MAX_FILE_SIZE:
            raise ValueError("文件大小超过 10MB 限制")

        ext = self._mime_to_ext(mime_type)
        uid = uuid.uuid4().hex[:16]
        storage_name = f"{uid}{ext}"
        storage_path = self.album_dir / storage_name
        storage_path.write_bytes(file_bytes)

        thumb_name = f"thumb_{uid}{ext}"
        thumb_path = self.album_dir / thumb_name
        self._create_thumbnail(storage_path, thumb_path)

        return self.repo.add_photo(
            itinerary_id=itinerary_id,
            user_id=user_id,
            file_name=file_name,
            file_size=len(file_bytes),
            mime_type=mime_type,
            storage_path=f"album/{storage_name}",
            thumbnail_path=f"album/{thumb_name}",
            description=description,
        )

    def delete(self, photo_id: int, user_id: str) -> bool:
        photo = self.repo.get_photo(photo_id)
        if not photo:
            raise ValueError("照片不存在")
        if photo.user_id != user_id:
            raise PermissionError("无权删除此照片")

        # 删除磁盘文件
        for path_key in ("storage_path", "thumbnail_path"):
            rel = getattr(photo, path_key, "")
            if rel:
                full = settings.data_dir / rel
                if full.exists():
                    full.unlink()

        return self.repo.delete_photo(photo_id)

    def list_photos(self, itinerary_id: str) -> list[Photo]:
        return self.repo.list_photos(itinerary_id)

    def _create_thumbnail(self, src: Path, dst: Path) -> None:
        try:
            img = Image.open(src)
            img.thumbnail((THUMB_MAX_SIZE, THUMB_MAX_SIZE))
            img.save(dst)
        except Exception as e:
            logger.warning("缩略图生成失败: %s", e)

    @staticmethod
    def _mime_to_ext(mime: str) -> str:
        return {".jpg": ".jpg", "image/jpeg": ".jpg",
                "image/png": ".png", "image/webp": ".webp"}.get(mime, ".jpg")
```

---

## 6. API 接口设计

在 `api/server.py` 中新增以下路由。

### 6.1 上传照片

```
POST /api/itineraries/{itinerary_id}/photos
```

Content-Type: `multipart/form-data`

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| files | file[] | 是 | 一个或多个图片文件 |
| description | string | 否 | 照片描述（对所有文件统一设置） |

**成功响应：**

```json
{
  "photos": [
    {
      "id": 1,
      "itinerary_id": "a1b2c3d4",
      "user_id": "ee3d2c304e265393",
      "file_name": "风景.jpg",
      "file_size": 2048000,
      "mime_type": "image/jpeg",
      "description": "富士山远眺",
      "storage_path": "album/a1b2c3d4e5f6.jpg",
      "thumbnail_path": "album/thumb_a1b2c3d4e5f6.jpg",
      "created_at": "2026-06-03T10:00:00"
    }
  ]
}
```

**错误码：**

| 状态码 | 说明 |
|--------|------|
| 400 | 行程不存在 / 文件类型不支持 / 文件过大 |
| 401 | 未登录 |

### 6.2 获取行程相册

```
GET /api/itineraries/{itinerary_id}/photos
```

**响应：**

```json
{
  "itinerary_id": "a1b2c3d4",
  "photos": [
    {
      "id": 1,
      "file_name": "风景.jpg",
      "file_size": 2048000,
      "mime_type": "image/jpeg",
      "description": "富士山远眺",
      "thumbnail_path": "album/thumb_a1b2c3d4e5f6.jpg",
      "storage_path": "album/a1b2c3d4e5f6.jpg",
      "created_at": "2026-06-03T10:00:00"
    }
  ],
  "total": 1
}
```

### 6.3 删除照片

```
DELETE /api/itineraries/{itinerary_id}/photos/{photo_id}
```

**响应：**

```json
{
  "detail": "已删除"
}
```

**错误码：**

| 状态码 | 说明 |
|--------|------|
| 403 | 非照片所有者 |
| 404 | 照片不存在 |

### 6.4 获取原图文件

```
GET /api/album/{storage_path}
```

**公开访问（需登录）**，直接返回图片二进制流。

Content-Type: 对应的 MIME 类型。

### 6.5 获取缩略图

```
GET /api/album/thumbs/{thumbnail_path}
```

与原图接口类似，返回缩略图二进制流。

---

## 7. API 路由实现参考

在 `api/server.py` 中新增以下代码：

```python
from fastapi import UploadFile, File, Form
from core.album.service import AlbumService

_album_service = AlbumService()


@app.post("/api/itineraries/{itinerary_id}/photos")
async def upload_photos(
    itinerary_id: str,
    request: Request,
    files: list[UploadFile] = File(...),
    description: str = Form(""),
):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})

    # 校验行程归属
    itin = _itinerary_repo.get_itinerary(itinerary_id)
    if not itin or not _user_owns_itinerary(user_id, itin):
        return JSONResponse(status_code=400, content={"detail": "行程不存在"})

    photos = []
    for f in files:
        file_bytes = await f.read()
        try:
            photo = _album_service.upload(
                itinerary_id=itinerary_id,
                user_id=user_id,
                file_name=f.filename or "",
                file_bytes=file_bytes,
                mime_type=f.content_type or "image/jpeg",
                description=description,
            )
            photos.append(photo.to_dict())
        except ValueError as e:
            return JSONResponse(status_code=400, content={"detail": str(e)})
    return {"photos": photos}


@app.get("/api/itineraries/{itinerary_id}/photos")
async def list_photos(itinerary_id: str, request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    photos = _album_service.list_photos(itinerary_id)
    return {
        "itinerary_id": itinerary_id,
        "photos": [p.to_dict() for p in photos],
        "total": len(photos),
    }


@app.delete("/api/itineraries/{itinerary_id}/photos/{photo_id}")
async def delete_photo(itinerary_id: str, photo_id: int, request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    try:
        _album_service.delete(photo_id, user_id)
    except ValueError:
        return JSONResponse(status_code=404, content={"detail": "照片不存在"})
    except PermissionError:
        return JSONResponse(status_code=403, content={"detail": "无权删除此照片"})
    return {"detail": "已删除"}


from fastapi.responses import FileResponse


@app.get("/api/album/{file_path:path}")
async def serve_album_image(file_path: str, request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    full_path = settings.data_dir / file_path
    if not full_path.exists():
        return JSONResponse(status_code=404, content={"detail": "文件不存在"})
    return FileResponse(str(full_path))
```

---

## 8. 前端设计

### 8.1 新增文件

```
frontend/src/
  pages/
    AlbumPage.tsx          # 相册页面
  components/
    album/
      PhotoGrid.tsx        # 照片网格展示
      PhotoUpload.tsx      # 上传组件
      PhotoPreview.tsx     # 图片预览（大图弹窗）
  hooks/
    useAlbumStore.ts       # 相册状态管理
```

### 8.2 路由配置

在 `App.tsx` 中新增：

```tsx
<Route
  path="/itinerary/:id/album"
  element={
    <PrivateRoute>
      <AlbumPage />
    </PrivateRoute>
  }
/>
```

### 8.3 页面交互

1. **相册页面** (`AlbumPage.tsx`)
   - 顶部显示行程标题 + 照片数量
   - 「上传照片」按钮，点击弹出上传面板
   - 照片网格展示（使用缩略图），点击可预览大图
   - 每张照片右上角有删除按钮（仅上传者可见）
   - 支持多选批量删除

2. **上传组件** (`PhotoUpload.tsx`)
   - 支持拖拽上传和点击选择文件
   - 限制文件类型为 JPG/PNG/WEBP
   - 限制单文件 10MB
   - 上传进度条展示
   - 可选填照片描述

3. **预览组件** (`PhotoPreview.tsx`)
   - 点击缩略图弹出大图
   - 支持左右切换
   - 显示照片信息（文件名、上传时间、描述）

### 8.4 状态管理（`useAlbumStore.ts`）

```typescript
interface Photo {
  id: number
  itinerary_id: string
  user_id: string
  file_name: string
  file_size: number
  mime_type: string
  description: string
  storage_path: string
  thumbnail_path: string
  created_at: string
}

interface AlbumState {
  photos: Photo[]
  loading: boolean
  fetchPhotos: (itineraryId: string) => Promise<void>
  uploadPhotos: (itineraryId: string, files: File[], description?: string) => Promise<void>
  deletePhoto: (itineraryId: string, photoId: number) => Promise<void>
}
```

---

## 9. 配置项

在 `config.py` 的 `Settings` 类中新增：

```python
album_max_file_size: int = 10 * 1024 * 1024   # 单文件最大字节数，默认 10MB
album_allowed_types: str = "image/jpeg,image/png,image/webp"  # 允许的 MIME 类型
album_thumbnail_size: int = 300                # 缩略图最大边长
album_storage_dir: str = "album"               # 存储子目录名
```

---

## 10. 依赖变更

`requirements.txt` 新增：

```
Pillow>=10.0.0
python-multipart>=0.0.6   # FastAPI 文件上传依赖
```

---

## 11. 数据库迁移

在 `infra/db.py` 的 `_run_migrations` 函数中新增：

```python
# Migration: 创建 album_photos 表
existing_tables = {row[0] for row in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table'"
).fetchall()}
if "album_photos" not in existing_tables:
    conn.executescript("""
        CREATE TABLE album_photos (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            itinerary_id  TEXT NOT NULL,
            user_id       TEXT NOT NULL,
            file_name     TEXT NOT NULL DEFAULT '',
            file_size     INTEGER NOT NULL DEFAULT 0,
            mime_type     TEXT NOT NULL DEFAULT '',
            description   TEXT NOT NULL DEFAULT '',
            storage_path  TEXT NOT NULL DEFAULT '',
            thumbnail_path TEXT NOT NULL DEFAULT '',
            created_at    TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (itinerary_id) REFERENCES itineraries(id) ON DELETE CASCADE
        );
        CREATE INDEX idx_photos_itinerary ON album_photos(itinerary_id);
        CREATE INDEX idx_photos_user ON album_photos(user_id);
    """)
    conn.commit()
    logger.info("Migration: created album_photos table")
```

---

## 12. 开发步骤

| 步骤 | 内容 | 涉及文件 |
|------|------|----------|
| 1 | 数据库：新增 `album_photos` 表 + 迁移 | `infra/db.py` |
| 2 | 后端 Schema | 新建 `core/album/schema.py`、`core/album/__init__.py` |
| 3 | 后端 Repository | 新建 `core/album/repository.py` |
| 4 | 后端 Service（文件存储 + 缩略图） | 新建 `core/album/service.py` |
| 5 | API 路由 | `api/server.py` |
| 6 | 配置项 | `config.py` |
| 7 | 依赖安装 | `requirements.txt` |
| 8 | 前端：状态管理 | 新建 `useAlbumStore.ts` |
| 9 | 前端：组件开发 | 新建 `PhotoGrid.tsx`、`PhotoUpload.tsx`、`PhotoPreview.tsx` |
| 10 | 前端：相册页面 | 新建 `AlbumPage.tsx` |
| 11 | 前端：路由配置 | `App.tsx` |
| 12 | 行程详情页添加「相册」入口 | `ItineraryOverview.tsx` |

---

## 13. 注意事项

1. **安全性**：文件上传需校验 MIME 类型，防止伪造扩展名上传恶意文件；文件存储路径不应暴露给前端，通过 API 代理访问。
2. **性能**：缩略图在上传时生成，浏览相册时只返回缩略图路径，按需加载原图。
3. **存储清理**：删除照片时同步删除磁盘文件；行程删除时通过外键级联删除照片记录，但磁盘文件需在 Service 层补充清理逻辑。
4. **并发**：SQLite 写入时注意线程安全，当前项目使用 `threading.local` 管理连接，无需额外处理。
5. **扩展性**：后续可考虑支持照片排序、相册封面设置、照片标注地理位置等功能。
