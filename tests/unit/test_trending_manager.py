"""application/trending/manager.py 单元测试。

不访问真实网络；使用 monkeypatch 替换 httpx 与 HotspotService。
覆盖：_classify、refresh_pool、get_trending_travel、get_trending_news。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from application.trending import manager as trending


class TestClassify:
    def test_returns_default_for_unknown_title(self):
        assert trending._classify("一个普通的标题") == "热点"

    def test_tech_keywords(self):
        assert trending._classify("OpenAI 发布新大模型") == "科技"

    def test_finance_keywords(self):
        assert trending._classify("A股 大幅上涨") == "财经"

    def test_society_keywords(self):
        assert trending._classify("地震 救援正在进行") == "社会"

    def test_sports_keywords(self):
        assert trending._classify("奥运 乒乓球 决赛") == "体育"

    def test_entertainment_keywords(self):
        assert trending._classify("某明星 演唱会 票房") == "娱乐"

    def test_international_keywords(self):
        assert trending._classify("美国 俄罗斯 会晤") == "国际"

    def test_education_keywords(self):
        assert trending._classify("高考 志愿 录取") == "教育"

    def test_health_keywords(self):
        assert trending._classify("疫情 病例 增加") == "健康"

    def test_first_matching_category_wins(self):
        # 同时包含科技+财经关键词，应返回先匹配的（按 dict 顺序）
        result = trending._classify("AI 芯片 股市")
        # 科技在财经之前
        assert result == "科技"


class TestRefreshPool:
    @pytest.mark.asyncio
    async def test_returns_count_from_service(self, monkeypatch):
        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_result.count = 7
        mock_service.refresh = AsyncMock(return_value=mock_result)
        monkeypatch.setattr(
            "application.news.hotspot_service.get_default_service",
            lambda: mock_service,
        )
        count = await trending.refresh_pool()
        assert count == 7

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_items(self, monkeypatch):
        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_result.count = 0
        mock_service.refresh = AsyncMock(return_value=mock_result)
        monkeypatch.setattr(
            "application.news.hotspot_service.get_default_service",
            lambda: mock_service,
        )
        count = await trending.refresh_pool()
        assert count == 0


class TestGetTrendingTravel:
    @pytest.mark.asyncio
    async def test_returns_list_of_dicts_with_classified_tag(self, monkeypatch):
        mock_item = MagicMock()
        mock_item.id = "baidu-0"
        mock_item.title = "OpenAI 发布新模型"
        mock_item.summary = "AI 技术突破"
        mock_item.url = "https://example.com"
        mock_item.source = "baidu"

        mock_service = MagicMock()
        mock_service.list_current = AsyncMock(return_value=[mock_item])
        monkeypatch.setattr(
            "application.news.hotspot_service.get_default_service",
            lambda: mock_service,
        )

        result = await trending.get_trending_travel()
        assert len(result) == 1
        assert result[0]["id"] == "baidu-0"
        assert result[0]["title"] == "OpenAI 发布新模型"
        assert result[0]["tag"] == "科技"

    @pytest.mark.asyncio
    async def test_empty_list_when_no_items(self, monkeypatch):
        mock_service = MagicMock()
        mock_service.list_current = AsyncMock(return_value=[])
        monkeypatch.setattr(
            "application.news.hotspot_service.get_default_service",
            lambda: mock_service,
        )
        result = await trending.get_trending_travel()
        assert result == []


class TestGetTrendingNews:
    @pytest.mark.asyncio
    async def test_delegates_to_get_trending_travel(self, monkeypatch):
        mock_item = MagicMock()
        mock_item.id = "weibo-1"
        mock_item.title = "A股 大涨"
        mock_item.summary = ""
        mock_item.url = ""
        mock_item.source = "weibo"

        mock_service = MagicMock()
        mock_service.list_current = AsyncMock(return_value=[mock_item])
        monkeypatch.setattr(
            "application.news.hotspot_service.get_default_service",
            lambda: mock_service,
        )
        result = await trending.get_trending_news()
        assert len(result) == 1
        assert result[0]["tag"] == "财经"
