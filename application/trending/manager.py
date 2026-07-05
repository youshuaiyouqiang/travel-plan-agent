from __future__ import annotations

import json
import logging
import random
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_CACHE_FILE = Path(__file__).resolve().parent.parent / "data" / "trending_cache.json"
_CACHE_TTL = 1800

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

# 通用新闻分类关键词（用于给热搜打标签）
_CATEGORY_KEYWORDS = {
    "科技": [
        "AI",
        "人工智能",
        "芯片",
        "手机",
        "互联网",
        "算法",
        "大模型",
        "算力",
        "5G",
        "6G",
        "量子",
        "机器人",
        "自动驾驶",
        "腾讯",
        "阿里",
        "字节",
        "华为",
        "苹果",
        "谷歌",
        "微软",
        "OpenAI",
        "百度",
        "Meta",
    ],
    "财经": [
        "股市",
        "A股",
        "基金",
        "央行",
        "降准",
        "降息",
        "利率",
        "GDP",
        "CPI",
        "经济",
        "通胀",
        "汇率",
        "美元",
        "人民币",
        "楼 市",
        "房价",
        "上市",
        "IPO",
        "市值",
        "比特币",
        "加密货币",
    ],
    "社会": [
        "警方",
        "事故",
        "救援",
        "地震",
        "洪水",
        "暴雨",
        "台风",
        "火灾",
        "遇难",
        "伤亡",
        "失踪",
        "调查",
        "通报",
        "警方通报",
    ],
    "体育": [
        "奥运",
        "世界杯",
        "NBA",
        "CBA",
        "中超",
        "足球",
        "篮球",
        "网球",
        "乒乓球",
        "羽毛球",
        "游泳",
        "田径",
        "冠军",
        "决赛",
        "半决赛",
        "联赛",
        "夺冠",
    ],
    "娱乐": [
        "电影",
        "电视剧",
        "综艺",
        "明星",
        "演员",
        "歌手",
        "演唱会",
        "票房",
        "首映",
        "出道",
        "离婚",
        "结婚",
        "热搜",
    ],
    "国际": [
        "美国",
        "俄罗斯",
        "乌克兰",
        "欧盟",
        "日本",
        "韩国",
        "朝鲜",
        "伊朗",
        "以色列",
        "巴勒斯坦",
        "联合国",
        "北约",
        "G7",
        "G20",
        "访问",
        "会晤",
        "峰会",
    ],
    "教育": [
        "高考",
        "中考",
        "考研",
        "大学",
        "高校",
        "招生",
        "录取",
        "分数",
        "志愿",
        "毕业",
        "就业",
        "招聘",
        "考公",
        "公务员",
    ],
    "健康": ["疫情", "新冠", "病毒", "疫苗", "医院", "病例", "感染", "确诊", "医疗", "药品", "医保"],
}


def _classify(title: str) -> str:
    """根据标题关键词给新闻打分类标签。"""
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in title for kw in keywords):
            return category
    return "热点"


def _load_cache() -> tuple[list[dict], float] | None:
    if not _CACHE_FILE.exists():
        return None
    try:
        raw = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        return raw.get("items", []), raw.get("fetched_at", 0)
    except Exception:
        return None


def _load_pool() -> list[dict] | None:
    """加载热搜池（不校验时效，作为抓取失败时的兜底缓存）。"""
    pool_file = _CACHE_FILE.parent / "trending_pool.json"
    if not pool_file.exists():
        return None
    try:
        raw = json.loads(pool_file.read_text(encoding="utf-8"))
        return raw.get("items", [])
    except Exception:
        return None


def _save_pool(items: list[dict]) -> None:
    pool_file = _CACHE_FILE.parent / "trending_pool.json"
    pool_file.parent.mkdir(parents=True, exist_ok=True)
    pool_file.write_text(
        json.dumps({"items": items, "fetched_at": time.time()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _save_cache(items: list[dict]) -> None:
    _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_FILE.write_text(
        json.dumps({"items": items, "fetched_at": time.time()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


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
                            "content": desc or f"百度热搜：{word}",
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
                        "content": f"{title}——头条热点资讯",
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
                        "content": f"{note}——微博热搜话题",
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
                        "content": f"{title}——知乎热榜讨论。{excerpt}",
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
    """并发抓取所有热搜源，合并去重，按热度排序。"""
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


async def refresh_pool() -> int:
    pool = await _fetch_all_sources()
    if pool:
        _save_pool(pool)
        logger.info("Trending pool refreshed: %d items", len(pool))
    else:
        logger.warning("Trending pool refresh failed: no items fetched")
    return len(pool)


async def get_trending_travel(*, refresh: bool = False) -> list[dict]:
    """获取热搜新闻列表（保留旧函数名以兼容已有 import）。

    策略：
    1. 优先返回 30 分钟内的缓存
    2. 缓存过期则尝试抓取新数据
    3. 抓取失败则使用上次 pool 缓存
    4. 都没有则返回空列表
    """
    if not refresh:
        cached = _load_cache()
        if cached:
            items, fetched_at = cached
            if time.time() - fetched_at < _CACHE_TTL:
                return items

    online_pool = await _fetch_all_sources()
    if online_pool:
        _save_pool(online_pool)
    else:
        # 抓取失败，兜底使用上次 pool 缓存
        online_pool = _load_pool() or []
        if online_pool:
            logger.info("Using cached trending pool as fallback: %d items", len(online_pool))

    if not online_pool:
        return []

    # 按来源混合采样，最多 12 条
    by_source: dict[str, list[dict]] = {}
    for item in online_pool:
        src = item.get("source", "other")
        by_source.setdefault(src, []).append(item)

    items: list[dict] = []
    per_source = max(1, 12 // max(1, len(by_source)))
    for _src, lst in by_source.items():
        items.extend(lst[:per_source])
    items = items[:12]
    random.shuffle(items)

    _save_cache(items)
    return items


async def get_trending_news(*, refresh: bool = False) -> list[dict]:
    """获取热搜新闻（新函数名，语义更清晰）。"""
    return await get_trending_travel(refresh=refresh)
