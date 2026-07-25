"""infrastructure/news/fetchers.py 单元测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from application.news.models import Source
from infrastructure.news.fetchers import NewsFetcher, _match_provider


def _make_source(
    *,
    id: str = "s1",
    name: str = "example",
    domain: str = "example.com",
    status: str = "enabled",
) -> Source:
    """构造测试用 Source（填满所有必填字段）。"""
    return Source(
        id=id,
        name=name,
        domain=domain,
        tier="t1",
        status=status,  # type: ignore[arg-type]
        scoring_mode="ai_candidate",
        ai_score=None,
        ai_reason="",
        ai_subscores="{}",
        created_at="",
        updated_at="",
    )


class TestMatchProvider:
    def test_returns_baidu_for_baidu_domain(self):
        assert _match_provider("top.baidu.com") == "baidu"

    def test_returns_toutiao_for_toutiao_domain(self):
        assert _match_provider("www.toutiao.com") == "toutiao"

    def test_returns_weibo_for_weibo_domain(self):
        assert _match_provider("weibo.com") == "weibo"

    def test_returns_zhihu_for_zhihu_domain(self):
        assert _match_provider("zhihu.com") == "zhihu"

    def test_returns_none_for_unknown_domain(self):
        assert _match_provider("example.com") is None

    def test_returns_none_for_empty_string(self):
        assert _match_provider("") is None

    def test_returns_none_for_none(self):
        assert _match_provider(None) is None  # type: ignore[arg-type]

    def test_case_insensitive_match(self):
        assert _match_provider("BAIDU.COM") == "baidu"


class TestNewsFetcherFetch:
    @pytest.mark.asyncio
    async def test_returns_empty_for_unknown_provider(self):
        fetcher = NewsFetcher()
        source = _make_source(domain="example.com")
        result = await fetcher.fetch(source)
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_fetch_exception(self, monkeypatch):
        fetcher = NewsFetcher()
        source = _make_source(name="baidu", domain="baidu.com")

        async def _raise():
            raise RuntimeError("network down")

        # 模拟 trending._fetch_baidu_hot 抛错
        import application.trending.manager as trending

        monkeypatch.setattr(trending, "_fetch_baidu_hot", _raise)

        result = await fetcher.fetch(source)
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_items_from_provider(self, monkeypatch):
        fetcher = NewsFetcher()
        source = _make_source(name="baidu", domain="baidu.com")

        async def _fake_fetch():
            return [
                {"title": "新闻 1", "url": "https://1.com", "source": "baidu", "summary": "摘要1"},
                {"title": "新闻 2", "url": "https://2.com", "source": "baidu", "summary": "摘要2"},
            ]

        import application.trending.manager as trending

        monkeypatch.setattr(trending, "_fetch_baidu_hot", _fake_fetch)

        result = await fetcher.fetch(source)
        assert len(result) == 2
        assert result[0].id == "baidu-0"
        assert result[0].title == "新闻 1"
        assert result[1].id == "baidu-1"

    @pytest.mark.asyncio
    async def test_skips_items_with_empty_title(self, monkeypatch):
        fetcher = NewsFetcher()
        source = _make_source(name="baidu", domain="baidu.com")

        async def _fake_fetch():
            return [
                {"title": "", "url": "", "source": "", "summary": ""},
                {"title": "valid", "url": "", "source": "", "summary": ""},
            ]

        import application.trending.manager as trending

        monkeypatch.setattr(trending, "_fetch_baidu_hot", _fake_fetch)

        result = await fetcher.fetch(source)
        assert len(result) == 1
        assert result[0].title == "valid"

    @pytest.mark.asyncio
    async def test_truncates_long_title_and_summary(self, monkeypatch):
        fetcher = NewsFetcher()
        source = _make_source(name="baidu", domain="baidu.com")

        async def _fake_fetch():
            return [
                {
                    "title": "x" * 500,
                    "url": "",
                    "source": "",
                    "summary": "y" * 500,
                }
            ]

        import application.trending.manager as trending

        monkeypatch.setattr(trending, "_fetch_baidu_hot", _fake_fetch)

        result = await fetcher.fetch(source)
        assert len(result) == 1
        assert len(result[0].title) <= 200
        assert len(result[0].summary) <= 300

    @pytest.mark.asyncio
    async def test_uses_source_name_when_raw_source_empty(self, monkeypatch):
        fetcher = NewsFetcher()
        source = _make_source(name="百度热搜", domain="baidu.com")

        async def _fake_fetch():
            return [{"title": "x", "url": "", "source": "", "summary": ""}]

        import application.trending.manager as trending

        monkeypatch.setattr(trending, "_fetch_baidu_hot", _fake_fetch)

        result = await fetcher.fetch(source)
        assert result[0].source == "百度热搜"
