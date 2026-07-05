#!/usr/bin/env python3
"""和风天气 CLI 工具。

使用和风天气 API 获取实时天气、日预报和小时预报。

环境变量:
    WEATHER_API_KEY  和风天气 API 密钥

示例:
    python3 qweather_tool.py now "北京"
    python3 qweather_tool.py daily "上海" --days 7
    python3 qweather_tool.py hourly "101010100" --hours 24
"""

import argparse
import asyncio
import json
import os
import sys
from urllib.parse import urlencode

# 和风天气 API 配置
# 使用正确的 API 主机（从日志中发现的正确主机）
API_HOST = "j7759g3k38.re.qweatherapi.com"
GEO_HOST = API_HOST


async def http_get(url: str, params: dict) -> dict:
    """使用 urllib 发送 HTTP GET 请求"""
    try:
        from urllib.request import urlopen, Request
        from urllib.error import HTTPError, URLError

        full_url = f"{url}?{urlencode(params)}"
        req = Request(full_url)
        req.add_header("Accept-Encoding", "gzip, deflate")
        req.add_header("User-Agent", "QWeatherTool/1.0")

        try:
            with urlopen(req, timeout=15) as response:
                data = response.read().decode("utf-8")
                return json.loads(data)
        except HTTPError as e:
            return {"code": str(e.code), "message": str(e.reason)}
        except URLError as e:
            return {"code": "NETWORK_ERROR", "message": str(e.reason)}
    except Exception as e:
        # 如果 urllib 失败，尝试使用 httpx（如果已安装）
        try:
            import httpx

            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(url, params=params)
                return response.json()
        except ImportError:
            return {"code": "IMPORT_ERROR", "message": f"httpx not installed and urllib failed: {str(e)}"}


async def city_lookup(location: str, lang: str = "zh", range_param: str = "cn") -> dict:
    """城市查询"""
    url = f"https://{GEO_HOST}/geo/v2/city/lookup"
    params = {
        "location": location,
        "lang": lang,
        "range": range_param,
        "key": get_api_key(),
    }
    return await http_get(url, params)


async def weather_now(location_id: str, lang: str = "zh", unit: str = "metric") -> dict:
    """获取实时天气"""
    url = f"https://{API_HOST}/v7/weather/now"
    params = {
        "location": location_id,
        "lang": lang,
        "unit": "m" if unit == "metric" else "i",
        "key": get_api_key(),
    }
    return await http_get(url, params)


async def weather_daily(location_id: str, days: int = 7, lang: str = "zh", unit: str = "metric") -> dict:
    """获取日预报天气"""
    # 验证 days 参数
    if days not in [3, 7, 10, 15, 30]:
        days = 7

    url = f"https://{API_HOST}/v7/weather/{days}d"
    params = {
        "location": location_id,
        "lang": lang,
        "unit": "m" if unit == "metric" else "i",
        "key": get_api_key(),
    }
    return await http_get(url, params)


async def weather_hourly(location_id: str, hours: int = 24, lang: str = "zh", unit: str = "metric") -> dict:
    """获取小时预报天气"""
    # 验证 hours 参数
    if hours not in [24, 72, 168]:
        hours = 24

    url = f"https://{API_HOST}/v7/weather/{hours}h"
    params = {
        "location": location_id,
        "lang": lang,
        "unit": "m" if unit == "metric" else "i",
        "key": get_api_key(),
    }
    return await http_get(url, params)


def get_api_key() -> str:
    """获取 API 密钥"""
    api_key = os.environ.get("WEATHER_API_KEY", "")
    if not api_key:
        print("错误: 请设置环境变量 WEATHER_API_KEY", file=sys.stderr)
        sys.exit(1)
    return api_key


async def query_location(location: str, lang: str = "zh"):
    """查询地点信息"""
    result = await city_lookup(location, lang=lang)
    print(json.dumps(result, ensure_ascii=False, indent=2))


async def query_now(location: str, lang: str = "zh", unit: str = "metric"):
    """查询实时天气"""
    # 先查询地点 ID
    geo_result = await city_lookup(location, lang=lang)

    if geo_result.get("code") != "200":
        print(f"地点查询失败: {json.dumps(geo_result, ensure_ascii=False)}")
        return

    location_id = geo_result["location"][0]["id"]
    location_name = geo_result["location"][0]["name"]

    # 查询实时天气
    weather_result = await weather_now(location_id, lang=lang, unit=unit)

    # 组合结果
    output = {
        "location": {
            "id": location_id,
            "name": location_name,
        },
        "weather": weather_result,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


async def query_daily(location: str, days: int = 7, lang: str = "zh", unit: str = "metric"):
    """查询日预报天气"""
    # 先查询地点 ID
    geo_result = await city_lookup(location, lang=lang)

    if geo_result.get("code") != "200":
        print(f"地点查询失败: {json.dumps(geo_result, ensure_ascii=False)}")
        return

    location_id = geo_result["location"][0]["id"]
    location_name = geo_result["location"][0]["name"]
    adm = geo_result["location"][0].get("adm1", "")

    # 查询天气预报
    weather_result = await weather_daily(location_id, days=days, lang=lang, unit=unit)

    # 组合结果
    output = {
        "location": {
            "id": location_id,
            "name": location_name,
            "adm": adm,
        },
        "forecast": weather_result.get("daily", []),
        "update_time": weather_result.get("updateTime", ""),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


async def query_hourly(location: str, hours: int = 24, lang: str = "zh", unit: str = "metric"):
    """查询小时预报天气"""
    # 先查询地点 ID
    geo_result = await city_lookup(location, lang=lang)

    if geo_result.get("code") != "200":
        print(f"地点查询失败: {json.dumps(geo_result, ensure_ascii=False)}")
        return

    location_id = geo_result["location"][0]["id"]
    location_name = geo_result["location"][0]["name"]

    # 查询小时预报
    weather_result = await weather_hourly(location_id, hours=hours, lang=lang, unit=unit)

    # 组合结果
    output = {
        "location": {
            "id": location_id,
            "name": location_name,
        },
        "hourly": weather_result.get("hourly", []),
        "update_time": weather_result.get("updateTime", ""),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


async def main():
    """主函数"""
    command_aliases = {
        "forecast": "daily",
        "weather": "daily",
    }
    if len(sys.argv) > 1 and sys.argv[1] in command_aliases:
        sys.argv[1] = command_aliases[sys.argv[1]]

    parser = argparse.ArgumentParser(
        description="和风天气 CLI 工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s now "北京"
  %(prog)s daily "上海" --days 7
  %(prog)s hourly "101010100" --hours 24
        """.replace("%(prog)s", "qweather_tool.py"),
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # 地点查询
    lookup_parser = subparsers.add_parser("lookup", help="查询地点信息")
    lookup_parser.add_argument("location", nargs="?", help="地点名称或 ID")
    lookup_parser.add_argument("--location", dest="location_opt", help="地点名称或 ID")
    lookup_parser.add_argument("--lang", default="zh", help="语言 (zh/en/ja/fr)")

    # 实时天气
    now_parser = subparsers.add_parser("now", help="查询实时天气")
    now_parser.add_argument("location", nargs="?", help="地点名称或 ID")
    now_parser.add_argument("--location", dest="location_opt", help="地点名称或 ID")
    now_parser.add_argument("--lang", default="zh", help="语言 (zh/en/ja/fr)")
    now_parser.add_argument("--unit", default="metric", help="单位 (metric/imperial)")

    # 日预报
    daily_parser = subparsers.add_parser("daily", help="查询日预报天气")
    daily_parser.add_argument("location", nargs="?", help="地点名称或 ID")
    daily_parser.add_argument("--location", dest="location_opt", help="地点名称或 ID")
    daily_parser.add_argument("--days", type=int, default=7, help="预报天数 (3/7/10/15/30)")
    daily_parser.add_argument("--lang", default="zh", help="语言 (zh/en/ja/fr)")
    daily_parser.add_argument("--unit", default="metric", help="单位 (metric/imperial)")

    # 小时预报
    hourly_parser = subparsers.add_parser("hourly", help="查询小时预报天气")
    hourly_parser.add_argument("location", nargs="?", help="地点名称或 ID")
    hourly_parser.add_argument("--location", dest="location_opt", help="地点名称或 ID")
    hourly_parser.add_argument("--hours", type=int, default=24, help="预报小时数 (24/72/168)")
    hourly_parser.add_argument("--lang", default="zh", help="语言 (zh/en/ja/fr)")
    hourly_parser.add_argument("--unit", default="metric", help="单位 (metric/imperial)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # 检查 API Key
    api_key = os.environ.get("WEATHER_API_KEY")
    if not api_key:
        print("错误: 请设置环境变量 WEATHER_API_KEY", file=sys.stderr)
        sys.exit(1)

    try:
        location = getattr(args, "location", None) or getattr(args, "location_opt", None)
        if not location:
            parser.error("location is required")
        if args.command == "lookup":
            await query_location(location, args.lang)
        elif args.command == "now":
            await query_now(location, args.lang, args.unit)
        elif args.command == "daily":
            await query_daily(location, args.days, args.lang, args.unit)
        elif args.command == "hourly":
            await query_hourly(location, args.hours, args.lang, args.unit)
    except KeyboardInterrupt:
        print("\n操作已取消")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
