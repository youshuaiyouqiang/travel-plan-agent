"""Task 2 — 缓存热点池应用服务。

设计要点：
- ``list_current`` 只读缓存，绝不触发外部抓取（业务红线：``GET /hotspots`` 严禁抓取）。
- ``refresh`` 仅从 ``enabled`` 来源抓取；非 ``enabled`` 由 ``SourceService`` 过滤。
- ``HotspotRepository`` 基于 JSON 文件 + 内存缓存；不保存新闻全文，仅保存元数据。
- ``HotspotNormalizer`` 负责合并多源批次、按标题去重。
- ``HotspotService`` 持有 ``repository``（公共属性，供测试预填充缓存）和
  ``_fetcher``（私有属性，供测试断言调用次数）。
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from application.news.models import NewsItem, RefreshResult, Source
from application.news.source_service import SourceService

logger = logging.getLogger(__name__)

_DEFAULT_CACHE_FILE = (
    Path(__file__).resolve().parents[2] / "data" / "hotspot_cache.json"
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class NewsFetcherProtocol(Protocol):
    """新闻抓取器协议。

    实现方需提供 ``async def fetch(source: Source) -> list[NewsItem]``；
    抓取失败应返回空列表，不抛异常，由调用方据此跳过该来源。
    """

    async def fetch(self, source: Source) -> list[NewsItem]:  # pragma: no cover - 协议定义
        ...


class HotspotRepository:
    """热点池缓存仓库：可选 JSON 文件持久化 + 内存缓存。

    - ``cache_path=None``：纯内存模式（默认），仅在进程内有效，便于测试隔离。
    - ``cache_path=Path(...)``：在内存缓存基础上同步落盘，供跨进程共享。

    方法：
    - ``save_items``：直接覆盖当前缓存（用于测试预填充或外部注入）。
    - ``replace_current``：刷新流程专用，会附带 ``fetched_at`` 时间戳。
    - ``list_current``：读取缓存，遵守 limit。
    - ``get_by_id``：按 ID 精确查找，未命中返回 None。
    """

    def __init__(self, cache_path: Path | None = None) -> None:
        self._cache_path: Path | None = cache_path
        self._items: list[NewsItem] = []
        self._loaded: bool = False

    def _load(self) -> list[NewsItem]:
        if self._loaded:
            return self._items
        if self._cache_path is None or not self._cache_path.exists():
            self._items = []
        else:
            try:
                raw = json.loads(self._cache_path.read_text(encoding="utf-8"))
                self._items = [
                    NewsItem(
                        id=str(item.get("id", "")),
                        title=str(item.get("title", "")),
                        source=str(item.get("source", "")),
                        url=str(item.get("url", "")),
                        summary=str(item.get("summary", "")),
                        published_at=str(item.get("published_at", "")),
                    )
                    for item in raw.get("items", [])
                    if item.get("id") and item.get("title")
                ]
            except Exception:
                logger.warning("Hotspot cache load failed; starting empty", exc_info=True)
                self._items = []
        self._loaded = True
        return self._items

    def save_items(self, items: list[NewsItem]) -> None:
        """覆盖当前缓存（测试预填充 / 外部注入场景）。"""
        self._items = list(items)
        self._loaded = True
        self._persist()

    def replace_current(self, items: list[NewsItem], fetched_at: str) -> None:
        """刷新流程专用：原子替换缓存并写入 ``fetched_at`` 时间戳。"""
        self._items = list(items)
        self._loaded = True
        self._persist(fetched_at=fetched_at)

    def list_current(self, limit: int = 12) -> list[NewsItem]:
        """读取缓存前 ``limit`` 条；不触发外部抓取。"""
        return self._load()[:limit]

    def get_by_id(self, news_id: str) -> NewsItem | None:
        """按 ID 精确查找；未命中返回 None。"""
        for item in self._load():
            if item.id == news_id:
                return item
        return None

    def _persist(self, fetched_at: str | None = None) -> None:
        if self._cache_path is None:
            return
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "items": [
                    {
                        "id": item.id,
                        "title": item.title,
                        "source": item.source,
                        "url": item.url,
                        "summary": item.summary,
                        "published_at": item.published_at,
                    }
                    for item in self._items
                ],
                "fetched_at": fetched_at or _now_iso(),
            }
            self._cache_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            logger.warning("Hotspot cache persist failed", exc_info=True)


class HotspotNormalizer:
    """合并多源批次并按标题去重。"""

    def normalize_and_deduplicate(
        self, batches: list[list[NewsItem]]
    ) -> list[NewsItem]:
        seen: set[str] = set()
        merged: list[NewsItem] = []
        for batch in batches:
            for item in batch:
                key = (item.title or "").strip()
                if not key or key in seen:
                    continue
                seen.add(key)
                merged.append(item)
        return merged


class HotspotService:
    """热点池应用服务。"""

    def __init__(
        self,
        sources: SourceService,
        fetcher: NewsFetcherProtocol,
        repository: HotspotRepository | None = None,
        normalizer: HotspotNormalizer | None = None,
    ) -> None:
        self._sources = sources
        self._fetcher = fetcher
        # repository 为公共属性：测试通过它预填充缓存，路由层通过它 get_by_id。
        self.repository: HotspotRepository = repository or HotspotRepository()
        self._normalizer: HotspotNormalizer = normalizer or HotspotNormalizer()

    async def refresh(self) -> RefreshResult:
        """抓取所有 ``enabled`` 来源，去重后原子替换缓存。

        - 无 ``enabled`` 来源时返回 ``count=0`` 且不触发任何抓取。
        - 单个来源抓取失败由 fetcher 自行兜底返回空列表，不影响其他来源。
        """
        enabled = self._sources.list_enabled_sources()
        if not enabled:
            return RefreshResult(count=0, fetched_at=_now_iso(), sources_used=[])
        batches = await asyncio.gather(
            *(self._fetcher.fetch(source) for source in enabled)
        )
        items = self._normalizer.normalize_and_deduplicate(list(batches))
        fetched_at = _now_iso()
        self.repository.replace_current(items, fetched_at)
        return RefreshResult(
            count=len(items),
            fetched_at=fetched_at,
            sources_used=[source.domain for source in enabled],
        )

    async def list_current(self, limit: int = 12) -> list[NewsItem]:
        """读取缓存前 ``limit`` 条；绝不触发外部抓取。"""
        return self.repository.list_current(limit=limit)


# ---------------------------------------------------------------------------
# 兼容函数：供 server.py 启动期 warmup 与 trending/manager.py 包装层调用
# ---------------------------------------------------------------------------


_default_service: HotspotService | None = None


def get_default_service() -> HotspotService:
    """返回进程级默认 ``HotspotService`` 实例（懒加载）。

    供 ``application.trending.manager`` 包装层与启动期 warmup 使用；
    路由层应通过 ``request.app.state.hotspot_service`` 注入测试替身。
    生产环境通过显式 ``cache_path`` 启用文件持久化，跨进程共享缓存。
    """
    global _default_service
    if _default_service is None:
        from infrastructure.news.fetchers import NewsFetcher

        _default_service = HotspotService(
            sources=SourceService(),
            fetcher=NewsFetcher(),
            repository=HotspotRepository(cache_path=_DEFAULT_CACHE_FILE),
        )
    return _default_service


def reset_default_service() -> None:
    """重置默认实例（仅用于测试隔离）。"""
    global _default_service
    _default_service = None
