"""Task 2 — 新闻抓取器：从 enabled 来源抓取新闻条目。

设计要点：
- 适配层：将 ``application.trending.manager`` 中已稳定的抓取函数包装成
  ``async def fetch(source: Source) -> list[NewsItem]`` 协议。
- 域名 → provider 的映射通过 ``_match_provider`` 完成，未匹配的域名返回空。
- 抓取失败时返回空列表，不抛异常；上层会跳过该来源。
- 仅返回标题、来源、URL、摘要；绝不返回新闻全文。
"""

from __future__ import annotations

import logging

from application.news.models import NewsItem, Source

logger = logging.getLogger(__name__)

# 域名子串 → provider 标识的映射。新增来源只需在此登记域名子串。
_DOMAIN_DISPATCH: dict[str, str] = {
    "baidu.com": "baidu",
    "toutiao.com": "toutiao",
    "weibo.com": "weibo",
    "zhihu.com": "zhihu",
}


def _match_provider(domain: str) -> str | None:
    domain_lower = (domain or "").lower()
    for key, provider in _DOMAIN_DISPATCH.items():
        if key in domain_lower:
            return provider
    return None


class NewsFetcher:
    """从 enabled 来源抓取新闻条目。

    实现策略：根据来源域名匹配内置 provider，调用对应抓取函数。
    未匹配的域名（如测试用的 ``enabled.example``）返回空列表。
    """

    async def fetch(self, source: Source) -> list[NewsItem]:
        provider = _match_provider(source.domain)
        if provider is None:
            return []
        try:
            # Lazy import 避免与 trending/manager.py 形成循环依赖。
            from application.trending import manager as trending

            fetcher = {
                "baidu": trending._fetch_baidu_hot,
                "toutiao": trending._fetch_toutiao_hot,
                "weibo": trending._fetch_weibo_hot,
                "zhihu": trending._fetch_zhihu_hot,
            }.get(provider)
            if fetcher is None:
                return []
            raw_items = await fetcher()
        except Exception as e:
            logger.warning("Failed to fetch from %s: %s", source.domain, e)
            return []

        items: list[NewsItem] = []
        for idx, raw in enumerate(raw_items):
            title = (raw.get("title") or "").strip()
            if not title:
                continue
            items.append(
                NewsItem(
                    id=f"{provider}-{idx}",
                    title=title[:200],
                    source=str(raw.get("source") or source.name),
                    url=str(raw.get("url") or ""),
                    summary=str(raw.get("summary") or "")[:300],
                    published_at="",
                )
            )
        return items
