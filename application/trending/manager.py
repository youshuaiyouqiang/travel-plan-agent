from __future__ import annotations

import json
import logging
import random
import re
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_CACHE_FILE = Path(__file__).resolve().parent.parent / "data" / "trending_cache.json"
_CACHE_TTL = 1800

_TRAVEL_KEYWORDS = [
    "旅游", "旅行", "景区", "景点", "机票", "酒店", "民宿",
    "高铁", "航班", "签证", "出境", "入境", "免签", "落地签",
    "度假", "避暑", "滑雪", "温泉", "海滩", "海岛",
    "自驾", "露营", "古镇", "古城", "世界遗产",
    "文旅", "黄金周", "小长假", "五一", "十一", "春节",
    "迪士尼", "环球影城", "主题乐园", "5A",
    "攻略", "打卡", "网红", "出片",
    "航司", "廉航", "航空", "出行", "出游", "游客", "旅客",
    "风景区", "公园", "博物馆", "名胜",
    "美食", "小吃", "餐厅", "特产", "住宿", "客栈", "旅馆",
]

_FALLBACK_ITEMS = [
    {
        "title": "九寨沟：人间仙境的四季之美",
        "tag": "自然风光",
        "summary": "九寨沟四季景色各异，春花夏瀑秋叶冬雪",
        "content": "九寨沟位于四川省阿坝藏族羌族自治州，以翠海、叠瀑、彩林、雪峰、藏情为特色。春季山花烂漫，夏季瀑布飞流，秋季彩林尽染，冬季银装素裹。最佳游览时间为9-11月，此时彩林最为壮观。门票旺季169元，淡季80元。建议游玩2-3天，可搭配黄龙景区一起游览。",
    },
    {
        "title": "青岛啤酒节：夏日狂欢指南",
        "tag": "节庆活动",
        "summary": "每年8月青岛国际啤酒节，感受啤酒与海风",
        "content": "青岛国际啤酒节每年8月中旬在青岛啤酒城举办，持续约16天。来自全球的啤酒品牌齐聚一堂，搭配青岛特色海鲜和德式建筑风情。除了品酒，还可以游览栈桥、八大关、崂山等景点。建议提前预订住宿，啤酒节期间酒店价格翻倍。交通方面，青岛地铁直达啤酒城站。",
    },
    {
        "title": "丽江古城：慢生活的正确打开方式",
        "tag": "古镇",
        "summary": "束河古镇比大研古城更安静，适合发呆放空",
        "content": "丽江古城分为大研古城和束河古镇两部分。大研古城商业气息浓厚，酒吧街热闹非凡；束河古镇相对安静，保留了更多纳西族原生态风貌。推荐住在束河，白天逛大研，晚上回束河享受宁静。必体验：纳西古乐表演、玉龙雪山一日游、泸沽湖两日游。美食推荐腊排骨火锅和鸡豆凉粉。",
    },
    {
        "title": "日本京都：千年古都的红叶季",
        "tag": "出境游",
        "summary": "11月京都红叶绝美，清水寺岚山不可错过",
        "content": "京都最佳红叶观赏期为11月中旬至12月上旬。推荐路线：清水寺→二年坂三年坂→祇园→岚山竹林→天龙寺。红叶季住宿需提前2个月预订。交通建议购买京都巴士一日券（700日元）或地铁+巴士组合券。美食推荐怀石料理、抹茶甜品和汤豆腐。签证需提前办理日本单次或多次签证。",
    },
    {
        "title": "318川藏线自驾全攻略",
        "tag": "自驾",
        "summary": "从成都到拉萨，一路雪山草原湖泊",
        "content": "318川藏线全程约2142公里，建议行程10-15天。从成都出发，途经康定、新都桥、理塘、芒康、左贡、八宿、波密、林芝，最终到达拉萨。关键注意事项：1)提前服用红景天预防高反 2)车辆需SUV以上，备好防滑链 3)沿途加油站间隔较远，见站就加 4)雨季(7-8月)易遇塌方，建议5-6月或9-10月出发 5)需办理边防证才能前往珠峰大本营。",
    },
    {
        "title": "三亚亲子游：带娃玩转海岛",
        "tag": "亲子",
        "summary": "亚特兰蒂斯水世界+蜈支洲岛，孩子最爱",
        "content": "三亚亲子游推荐5天4晚行程。Day1-2：亚特兰蒂斯酒店，享受水世界和水族馆，孩子可以玩一整天。Day3：蜈支洲岛，坐电瓶车环岛，海上项目适合大孩子。Day4：亚龙湾热带天堂森林公园，走玻璃栈道。Day5：三亚免税店购物+返程。住宿推荐海棠湾区域，沙滩质量好且相对安静。防晒是第一要务，SPF50+防晒霜必备。",
    },
    {
        "title": "西安：穿越千年的美食之旅",
        "tag": "美食",
        "summary": "肉夹馍凉皮泡馍biangbiang面，碳水天堂",
        "content": "西安不仅是十三朝古都，更是碳水爱好者的天堂。必吃清单：1)回民街的肉夹馍和酸梅汤 2)永兴坊的摔碗酒和biangbiang面 3)老孙家泡馍 4)子午路张记肉夹馍。景点方面，兵马俑必去（建议请讲解员），大雁塔晚上有音乐喷泉，城墙可以骑自行车环游。华清池和华山可以各安排一天。住宿推荐钟楼附近，交通便利。",
    },
    {
        "title": "云南大理：风花雪月的慢旅行",
        "tag": "度假",
        "summary": "洱海骑行+苍山徒步+古城闲逛",
        "content": "大理推荐4-5天行程。Day1：大理古城闲逛，人民路和洋人街。Day2：洱海环湖骑行或自驾，途经双廊、小普陀、喜洲古镇。Day3：苍山徒步，坐索道上山，走玉带路。Day4：沙溪古镇一日游，比大理更原生态。Day5：逛古城买扎染和银饰。住宿推荐双廊海景房或古城内客栈。最佳季节3-5月，春暖花开。注意防晒，高原紫外线很强。",
    },
    {
        "title": "泰国清迈：小城故事多",
        "tag": "出境游",
        "summary": "寺庙夜市丛林飞跃，性价比超高的度假地",
        "content": "清迈是泰国北部城市，消费水平比曼谷和普吉低30%左右。推荐体验：1)素贴山双龙寺看日落 2)周日夜市淘手工艺品 3)丛林飞跃体验 4)大象自然公园（拒绝骑象）5)泰式按摩 6)学做泰菜。住宿古城区内精品酒店约200-400元/晚。美食推荐凤飞飞猪脚饭、芒果糯米饭、冬阴功汤。签证可办落地签或提前电子签。11-2月是凉季，最适宜出行。",
    },
    {
        "title": "张家界：阿凡达取景地的震撼",
        "tag": "自然风光",
        "summary": "天门山玻璃栈道+武陵源核心景区",
        "content": "张家界核心景区为武陵源风景名胜区，包含张家界国家森林公园、天子山、杨家界等。建议游玩3-4天。Day1：天门山，走玻璃栈道，看天门洞。Day2-3：武陵源核心景区，乘百龙天梯上山，走袁家界（阿凡达取景地）、天子山、十里画廊。Day4：大峡谷玻璃桥。门票武陵源225元/4天，天门山278元。建议住武陵源标志门附近，方便进出景区。",
    },
    {
        "title": "厦门：文艺青年的海岛梦",
        "tag": "海岛",
        "summary": "鼓浪屿+曾厝垵+环岛路，小清新必去",
        "content": "厦门适合3-4天的悠闲行程。Day1：鼓浪屿一日游，提前在微信购票（35元往返），岛上步行游览日光岩、菽庄花园、皓月园。Day2：南普陀寺→厦门大学→沙坡尾→曾厝垵。Day3：环岛路骑行，从白城沙滩到黄厝沙滩。Day4：集美学村或八市吃海鲜。美食推荐沙茶面、海蛎煎、花生汤、土笋冻。住宿推荐曾厝垵民宿或中山路附近酒店。",
    },
    {
        "title": "新疆伊犁：6月最美花海",
        "tag": "季节推荐",
        "summary": "薰衣草花海+那拉提草原+赛里木湖",
        "content": "伊犁6-7月是最美的季节。推荐7天行程：Day1-2：伊宁市，逛喀赞其民俗村，看薰衣草（6月中下旬最盛）。Day3：赛里木湖，环湖自驾，湖水蓝得不真实。Day4-5：那拉提草原，骑马、住毡房。Day6：喀拉峻草原，比那拉提更原始壮阔。Day7：特克斯八卦城，世界唯一八卦布局的城市。交通建议飞伊宁机场，当地租车自驾。注意新疆与内地有2小时时差。",
    },
    {
        "title": "免签国家2024最新清单",
        "tag": "免签",
        "summary": "说走就走的旅行，这些国家免签了",
        "content": "截至2024年，对中国护照免签或落地签的热门目的地包括：东南亚——泰国（免签）、马来西亚（免签）、新加坡（免签）、印尼巴厘岛（落地签）；中东——阿联酋（免签）、卡塔尔（免签）；欧洲——塞尔维亚（免签）、波黑（免签）；非洲——毛里求斯（免签）、摩洛哥（免签）；美洲——厄瓜多尔（免签）、巴巴多斯（免签）。泰国、马来西亚、新加坡是近期新增免签，说走就走非常方便。",
    },
    {
        "title": "莫干山民宿：江浙沪周末避世",
        "tag": "民宿",
        "summary": "竹林深处的精品民宿，周末逃离城市",
        "content": "莫干山位于浙江德清县，距上海2.5小时车程、杭州1小时车程，是江浙沪最热门的周末度假地。民宿推荐：1)裸心谷——高端度假村，适合家庭 2)法国山居——法式乡村风格 3)大乐之野——设计感极强 4)原舍——性价比之选。活动推荐：竹林徒步、骑山地车、采茶体验、露天电影。最佳季节4-10月，冬季也有独特的雪景民宿体验。周末价格较高，建议周中出行。",
    },
    {
        "title": "西藏拉萨：朝圣者的终极目的地",
        "tag": "人文",
        "summary": "布达拉宫+大昭寺+八廓街，灵魂洗礼之旅",
        "content": "拉萨建议4-5天行程。Day1：休息适应海拔，逛八廓街。Day2：布达拉宫（需提前一天预约，200元门票），下午大昭寺。Day3：哲蚌寺+色拉寺（下午看辩经）。Day4：纳木措一日游或羊卓雍措半日游。Day5：八廓街买纪念品，体验藏式甜茶馆。注意事项：1)提前一周服用红景天 2)刚到拉萨不要剧烈运动 3)布达拉宫每天限流，必须提前预约 4)尊重当地宗教习俗，寺庙内不要拍照。",
    },
    {
        "title": "桂林山水：甲天下的诗意之旅",
        "tag": "自然风光",
        "summary": "漓江竹筏+阳朔西街+龙脊梯田",
        "content": "桂林推荐4-5天行程。Day1：桂林市区，象鼻山、两江四湖夜游。Day2：漓江竹筏（杨堤-兴坪段最精华），下午到阳朔，逛西街。Day3：阳朔十里画廊骑行，遇龙河竹筏。Day4：龙脊梯田一日游（金坑大寨最壮观）。Day5：返程。美食推荐桂林米粉、啤酒鱼、荔浦芋扣肉。最佳季节4-10月，秋季梯田金黄最美。阳朔住宿推荐遇龙河畔的民宿，推开窗就是山水画。",
    },
]

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


def _is_travel_related(title: str) -> bool:
    return any(kw in title for kw in _TRAVEL_KEYWORDS)


def _load_cache() -> tuple[list[dict[str, str]], float] | None:
    if not _CACHE_FILE.exists():
        return None
    try:
        raw = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        return raw.get("items", []), raw.get("fetched_at", 0)
    except Exception:
        return None


def _load_pool() -> list[dict[str, str]] | None:
    pool_file = _CACHE_FILE.parent / "trending_pool.json"
    if not pool_file.exists():
        return None
    try:
        raw = json.loads(pool_file.read_text(encoding="utf-8"))
        fetched_at = raw.get("fetched_at", 0)
        if time.time() - fetched_at < _CACHE_TTL:
            return raw.get("items", [])
        return None
    except Exception:
        return None


def _save_pool(items: list[dict[str, str]]) -> None:
    pool_file = _CACHE_FILE.parent / "trending_pool.json"
    pool_file.parent.mkdir(parents=True, exist_ok=True)
    pool_file.write_text(
        json.dumps({"items": items, "fetched_at": time.time()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _save_cache(items: list[dict[str, str]]) -> None:
    _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_FILE.write_text(
        json.dumps({"items": items, "fetched_at": time.time()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


async def _fetch_baidu_travel() -> list[dict[str, str]]:
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(
                "https://top.baidu.com/api/board?platform=pc&tab=travel",
                headers={"User-Agent": _UA},
            )
            if resp.status_code != 200:
                logger.warning("Baidu travel API returned %s", resp.status_code)
                return []
            data = resp.json()
            cards = data.get("data", {}).get("cards", [])
            results: list[dict[str, str]] = []
            for card in cards:
                for item in card.get("content", []):
                    word = item.get("word", "").strip()
                    if not word:
                        continue
                    desc = item.get("desc", "").strip()
                    show = item.get("show", [])
                    img = item.get("img", "").strip()
                    hot_score = item.get("hotScore", "")
                    hot_change = item.get("hotChange", "")
                    tag = "旅游"
                    summary = ""
                    if desc:
                        parts = desc.split(" ", 1)
                        tag = parts[0].strip()[:4] if len(parts) > 1 else desc[:4]
                        summary = parts[1].strip() if len(parts) > 1 else ""
                    if len(show) > 1:
                        summary = show[1]
                    elif not summary:
                        summary = f"探索{word}的精彩旅行体验"
                    title = word
                    content = desc or summary or f"关于{word}的旅游资讯"
                    result: dict[str, str] = {
                        "title": title,
                        "tag": tag,
                        "summary": summary,
                        "content": content,
                    }
                    if img:
                        result["img"] = img
                    if hot_score:
                        result["hotScore"] = hot_score
                    if hot_change:
                        result["hotChange"] = hot_change
                    results.append(result)
            return results
    except Exception as e:
        logger.warning("Failed to fetch baidu travel: %s", e)
        return []


async def _fetch_baidu_hot() -> list[dict[str, str]]:
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(
                "https://top.baidu.com/board?tab=realtime",
                headers={"User-Agent": _UA},
            )
            if resp.status_code != 200:
                return []
            titles = re.findall(r'"word"\s*:\s*"([^"]+)"', resp.text)
            results: list[dict[str, str]] = []
            for title in titles:
                title = title.strip()
                if title and _is_travel_related(title):
                    results.append({"title": title, "tag": "热搜", "summary": "旅游相关热搜话题", "content": f"{title}——旅游相关热搜话题，了解更多详情请咨询旅行助手"})
            return results
    except Exception as e:
        logger.warning("Failed to fetch baidu hot search: %s", e)
        return []


async def _fetch_toutiao_hot() -> list[dict[str, str]]:
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
            results: list[dict[str, str]] = []
            for item in items:
                title = item.get("Title", "").strip()
                if title and _is_travel_related(title):
                    results.append({"title": title, "tag": "头条", "summary": "旅游相关热点资讯", "content": f"{title}——旅游相关热点资讯，了解更多详情请咨询旅行助手"})
            return results
    except Exception as e:
        logger.warning("Failed to fetch toutiao hot: %s", e)
        return []


async def _fetch_all_sources() -> list[dict[str, str]]:
    import asyncio
    results = await asyncio.gather(
        _fetch_baidu_travel(),
        _fetch_baidu_hot(),
        _fetch_toutiao_hot(),
    )
    pool: list[dict[str, str]] = []
    seen: set[str] = set()
    for source_items in results:
        for item in source_items:
            if item["title"] not in seen:
                seen.add(item["title"])
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


async def get_trending_travel(*, refresh: bool = False) -> list[dict[str, str]]:
    if not refresh:
        cached = _load_cache()
        if cached:
            items, fetched_at = cached
            if time.time() - fetched_at < _CACHE_TTL:
                return items

    fallback = _FALLBACK_ITEMS.copy()
    online_pool = _load_pool()
    if online_pool is None or len(online_pool) < 8:
        online_pool = await _fetch_all_sources()
        if online_pool:
            _save_pool(online_pool)

    online_with_content = [item for item in (online_pool or []) if item.get("content")]
    if online_with_content:
        online_sample = random.sample(online_with_content, min(4, len(online_with_content)))
        fallback_sample = random.sample(fallback, min(4, len(fallback)))
        items = online_sample + fallback_sample
        random.shuffle(items)
    else:
        items = random.sample(fallback, min(8, len(fallback)))

    _save_cache(items)
    return items
