"""Task 2 — trending/manager 兼容包装层。

历史责任：抓取百度/头条/微博/知乎热搜并缓存。
现状：被 ``application.news.hotspot_service.HotspotService`` 替代。
本模块保留：
- 底层抓取函数 ``_fetch_baidu_hot`` / ``_fetch_toutiao_hot`` /
  ``_fetch_weibo_hot`` / ``_fetch_zhihu_hot``，供
  ``infrastructure.news.fetchers.NewsFetcher`` 复用。
- 公共 API ``refresh_pool`` / ``get_trending_travel`` /
  ``get_trending_news`` 改为薄包装，委托给默认 ``HotspotService`` 实例，
  以避免破坏 ``api/server.py`` 与 ``api/v1/news.py`` 的现有 import。
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

# 通用新闻分类关键词（用于给热搜打标签）
_CATEGORY_KEYWORDS = {
    "科技": [
        "AI", "人工智能", "芯片", "手机", "互联网", "算法", "大模型", "算力",
        "5G", "6G", "量子", "机器人", "自动驾驶", "腾讯", "阿里", "字节",
        "华为", "苹果", "谷歌", "微软", "OpenAI", "百度", "Meta",
    ],
    "财经": [
        "股市", "A股", "基金", "央行", "降准", "降息", "利率", "GDP", "CPI",
        "经济", "通胀", "汇率", "美元", "人民币", "楼 市", "房价", "上市",
        "IPO", "市值", "比特币", "加密货币",
    ],
    "社会": [
        "警方", "事故", "救援", "地震", "洪水", "暴雨", "台风", "火灾",
        "遇难", "伤亡", "失踪", "调查", "通报", "警方通报",
    ],
    "体育": [
        "奥运", "世界杯", "NBA", "CBA", "中超", "足球", "篮球", "网球",
        "乒乓球", "羽毛球", "游泳", "田径", "冠军", "决赛", "半决赛",
        "联赛", "夺冠",
    ],
    "娱乐": [
        "电影", "电视剧", "综艺", "明星", "演员", "歌手", "演唱会", "票房",
        "首映", "出道", "离婚", "结婚", "热搜",
    ],
    "国际": [
        "美国", "俄罗斯", "乌克兰", "欧盟", "日本", "韩国", "朝鲜", "伊朗",
        "以色列", "巴勒斯坦", "联合国", "北约", "G7", "G20", "访问", "会晤",
        "峰会",
    ],
    "教育": [
        "高考", "中考", "考研", "大学", "高校", "招生", "录取", "分数",
        "志愿", "毕业", "就业", "招聘", "考公", "公务员",
    ],
    "健康": [
        "疫情", "新冠", "病毒", "疫苗", "医院", "病例", "感染", "确诊",
        "医疗", "药品", "医保",
    ],
}


def _classify(title: str) -> str:
    """根据标题关键词给新闻打分类标签。"""
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in title for kw in keywords):
            return category
    return "热点"


async def _fetch_baidu_hot() -> list[dict]:
    """百度实时热搜榜（通用新闻）。"""
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(
                "https://top.baidu.com/api/board?platform=pc&tab=realtime",
                headers={"User-Agent": _UA},
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            cards = data.get("data", {}).get("cards", [])
            results: list[dict] = []
            for card in cards:
                for item in card.get("content", []):
                    word = item.get("word", "").strip()
                    if not word:
                        continue
                    desc = item.get("desc", "").strip()
                    raw_url = item.get("rawUrl", "") or item.get("url", "")
                    hot_score = item.get("hotScore", "")
                    results.append(
                        {
                            "title": word,
                            "tag": _classify(word),
                            "summary": desc[:80] if desc else "",
                            "url": raw_url,
                            "hotScore": hot_score,
                            "source": "baidu",
                        }
                    )
            return results
    except Exception as e:
        logger.warning("Failed to fetch baidu hot: %s", e)
        return []


async def _fetch_toutiao_hot() -> list[dict]:
    """今日头条热榜。"""
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(
                "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc",
                headers={"User-Agent": _UA},
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            items = data.get("data", [])
            results: list[dict] = []
            for item in items:
                title = item.get("Title", "").strip()
                if not title:
                    continue
                url = item.get("Url", "") or item.get("url", "")
                results.append(
                    {
                        "title": title,
                        "tag": _classify(title),
                        "summary": "头条热点资讯",
                        "url": url,
                        "hotScore": str(item.get("HotValue", "")),
                        "source": "toutiao",
                    }
                )
            return results
    except Exception as e:
        logger.warning("Failed to fetch toutiao hot: %s", e)
        return []


async def _fetch_weibo_hot() -> list[dict]:
    """微博热搜榜。"""
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(
                "https://weibo.com/ajax/side/hotSearch",
                headers={"User-Agent": _UA},
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            realtime = data.get("data", {}).get("realtime", [])
            results: list[dict] = []
            for item in realtime:
                word = item.get("word", "").strip()
                if not word:
                    continue
                note = item.get("note", "") or word
                label = item.get("label_name", "") or "热搜"
                num = item.get("num", 0)
                word_scheme = item.get("word_scheme", word)
                url = f"https://s.weibo.com/weibo?q=%23{word_scheme}%23"
                results.append(
                    {
                        "title": note,
                        "tag": _classify(note),
                        "summary": f"微博{label}",
                        "url": url,
                        "hotScore": str(num),
                        "source": "weibo",
                    }
                )
            return results
    except Exception as e:
        logger.warning("Failed to fetch weibo hot: %s", e)
        return []


async def _fetch_zhihu_hot() -> list[dict]:
    """知乎热榜。"""
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(
                "https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total?limit=50",
                headers={"User-Agent": _UA},
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            items = data.get("data", [])
            results: list[dict] = []
            for entry in items:
                target = entry.get("target", {})
                title = target.get("title", "").strip()
                if not title:
                    continue
                qid = target.get("id", "")
                excerpt = target.get("excerpt", "") or ""
                detail_text = entry.get("detail_text", "")
                url = f"https://www.zhihu.com/question/{qid}"
                results.append(
                    {
                        "title": title,
                        "tag": _classify(title),
                        "summary": excerpt[:80] if excerpt else "知乎热榜",
                        "url": url,
                        "hotScore": detail_text.replace("万热度", "万") if detail_text else "",
                        "source": "zhihu",
                    }
                )
            return results
    except Exception as e:
        logger.warning("Failed to fetch zhihu hot: %s", e)
        return []


async def _fetch_all_sources() -> list[dict]:
    """并发抓取所有热搜源，合并去重。"""
    import asyncio

    results = await asyncio.gather(
        _fetch_baidu_hot(),
        _fetch_toutiao_hot(),
        _fetch_weibo_hot(),
        _fetch_zhihu_hot(),
    )
    pool: list[dict] = []
    seen: set[str] = set()
    for source_items in results:
        for item in source_items:
            title_key = item["title"].strip()
            if title_key and title_key not in seen:
                seen.add(title_key)
                pool.append(item)
    return pool


# ---------------------------------------------------------------------------
# 薄包装：委托给 HotspotService（保留旧 API 签名以兼容现有 import）
# ---------------------------------------------------------------------------


async def refresh_pool() -> int:
    """刷新热点池；返回条目数。

    委托给默认 ``HotspotService`` 实例；仅抓取 ``enabled`` 来源，
    非 enabled 由 ``SourceService`` 过滤。
    """
    from application.news.hotspot_service import get_default_service

    service = get_default_service()
    result = await service.refresh()
    if result.count:
        logger.info("Hotspot pool refreshed: %d items", result.count)
    else:
        logger.info("Hotspot pool refresh: no enabled sources or no items fetched")
    return result.count


async def get_trending_travel(*, refresh: bool = False) -> list[dict]:
    """向后兼容：返回热点列表（dict 形式）。

    ``refresh`` 参数已废弃：本函数始终只读缓存，外部抓取由定时器与
    ``HotspotService.refresh`` 负责。保留参数以兼容现有调用签名。
    """
    from application.news.hotspot_service import get_default_service

    service = get_default_service()
    items = await service.list_current()
    return [
        {
            "id": item.id,
            "title": item.title,
            "summary": item.summary,
            "url": item.url,
            "source": item.source,
            "tag": _classify(item.title),
            "hotScore": "",
        }
        for item in items
    ]


async def get_trending_news(*, refresh: bool = False) -> list[dict]:
    """获取热搜新闻（新函数名，语义更清晰）。"""
    return await get_trending_travel(refresh=refresh)
