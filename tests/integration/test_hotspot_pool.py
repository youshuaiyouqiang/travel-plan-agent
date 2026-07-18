"""Task 2 — 热点池缓存与刷新的集成测试。

覆盖范围：
- ``HotspotService.list_current`` 只读缓存，不触发外部抓取
- ``HotspotService.refresh`` 从 ``enabled`` 来源抓取并原子替换缓存
- ``refresh`` 跳过非 ``enabled`` 来源
- ``list_current`` 遵守 limit 参数

业务红线：
- ``GET /hotspots`` 只读缓存，严禁发起外部抓取。
- 定时器仅抓取已启用来源。
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from application.news.hotspot_service import HotspotService
from application.news.models import NewsItem, RefreshResult
from application.news.source_service import SourceService
from infrastructure.persistence.database import init_db, reset_connection


# ---------------------------------------------------------------------------
# 共享 fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_hotspot_pool.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()


@dataclass
class FakeFetcher:
    """记录调用次数并返回预设条目的假抓取器。"""

    items: list[NewsItem]
    calls: int = 0
    fetched_domains: list[str] = None

    def __post_init__(self) -> None:
        if self.fetched_domains is None:
            self.fetched_domains = []

    async def fetch(self, source) -> list[NewsItem]:
        self.calls += 1
        self.fetched_domains.append(source.domain)
        return list(self.items)


@pytest.fixture
def fake_fetcher() -> FakeFetcher:
    return FakeFetcher(items=[NewsItem(id="n2", title="B", source="S", url="https://s/b", summary="y")])


@pytest.fixture
def source_service(db) -> SourceService:
    return SourceService()


@pytest.fixture
def enabled_source(source_service):
    """创建一个 enabled 来源供 refresh 抓取。"""
    candidate = source_service.create_candidate("enabled.example", 0.8, "verified")
    return source_service.review_source("admin-1", candidate.id, "enabled", "verified")


@pytest.fixture
def service(source_service, fake_fetcher) -> HotspotService:
    return HotspotService(sources=source_service, fetcher=fake_fetcher)


# ---------------------------------------------------------------------------
# list_current — 只读缓存
# ---------------------------------------------------------------------------


class TestListCurrent:
    @pytest.mark.asyncio
    async def test_hotspot_read_uses_cache_without_external_fetch(self, service, fake_fetcher):
        service.repository.save_items(
            [NewsItem(id="n1", title="A", source="S", url="https://s/a", summary="x")]
        )
        items = await service.list_current()
        assert [item.id for item in items] == ["n1"]
        assert fake_fetcher.calls == 0

    @pytest.mark.asyncio
    async def test_list_current_respects_limit(self, service):
        items = [
            NewsItem(id=f"n{i}", title=f"T{i}", source="S", url=f"https://s/{i}", summary="")
            for i in range(20)
        ]
        service.repository.save_items(items)
        result = await service.list_current(limit=5)
        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_list_current_empty_when_no_cache(self, service, fake_fetcher):
        items = await service.list_current()
        assert items == []
        assert fake_fetcher.calls == 0


# ---------------------------------------------------------------------------
# refresh — 抓取并替换缓存
# ---------------------------------------------------------------------------


class TestRefresh:
    @pytest.mark.asyncio
    async def test_refresh_fetches_from_enabled_sources(
        self, service, fake_fetcher, enabled_source
    ):
        result = await service.refresh()
        assert isinstance(result, RefreshResult)
        assert result.count == 1
        assert fake_fetcher.calls == 1
        assert "enabled.example" in fake_fetcher.fetched_domains

    @pytest.mark.asyncio
    async def test_refresh_replaces_previous_items(
        self, service, fake_fetcher, enabled_source
    ):
        service.repository.save_items(
            [NewsItem(id="old", title="Old", source="S", url="https://s/old", summary="")]
        )
        fake_fetcher.items = [
            NewsItem(id="new", title="New", source="S", url="https://s/new", summary="")
        ]
        await service.refresh()
        items = await service.list_current()
        assert [i.id for i in items] == ["new"]

    @pytest.mark.asyncio
    async def test_refresh_skips_non_enabled_sources(self, service, fake_fetcher, source_service):
        """pending 来源不应被抓取。"""
        source_service.create_candidate("pending.example", 0.5, "initial")
        result = await service.refresh()
        assert result.count == 0
        assert fake_fetcher.calls == 0

    @pytest.mark.asyncio
    async def test_refresh_no_enabled_sources_returns_zero(self, service, fake_fetcher):
        result = await service.refresh()
        assert result.count == 0
        assert fake_fetcher.calls == 0
