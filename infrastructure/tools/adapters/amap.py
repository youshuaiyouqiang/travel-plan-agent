from __future__ import annotations

import json
import logging
import os
import subprocess

from .base import ToolHandler, ToolSpec, bind_tool

logger = logging.getLogger(__name__)

AMAP_KEY = os.environ.get("AMAP_WEBSERVICE_KEY", "")
_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "skills", "amap-maps", "scripts", "amap_tool.py")


def _run_amap(args: list[str]) -> dict:
    if not AMAP_KEY:
        return {"is_error": True, "content": "AMAP_WEBSERVICE_KEY 环境变量未设置，无法使用高德地图服务"}
    cmd = ["python", _SCRIPT] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                                env={**os.environ, "AMAP_WEBSERVICE_KEY": AMAP_KEY})
        if result.returncode != 0:
            return {"is_error": True, "content": f"高德地图调用失败: {result.stderr[:500]}"}
        try:
            data = json.loads(result.stdout)
            # 检查高德 API 返回的业务错误
            status = str(data.get("status", ""))
            infocode = str(data.get("infocode", ""))
            if status == "0" or infocode in ("10009", "10001", "10002", "10003", "10004", "10005", "10006", "10007", "10008", "10010", "10011", "10012", "10013", "10014", "10015", "10016", "10017", "10019", "10020", "10021", "10022", "10023", "10024", "10025", "10026", "10027", "10028", "10029", "10030", "10031"):
                info = data.get("info", "未知错误")
                error_code = data.get("infocode", "")
                logger.warning("Amap API error: info=%s infocode=%s", info, error_code)
                return {"is_error": True, "content": f"高德地图服务暂不可用（{info}），请稍后重试或跳过此步骤"}
            return {"is_error": False, "content": json.dumps(data, ensure_ascii=False, indent=2)}
        except json.JSONDecodeError:
            return {"is_error": False, "content": result.stdout[:3000]}
    except subprocess.TimeoutExpired:
        return {"is_error": True, "content": "高德地图请求超时"}
    except Exception as e:
        return {"is_error": True, "content": f"高德地图调用异常: {e}"}


async def _search_poi(arguments: dict) -> dict:
    keywords = str(arguments.get("keywords", "")).strip()
    city = str(arguments.get("city", "")).strip()
    if not keywords:
        return {"is_error": True, "content": "missing keywords"}
    args = ["poi", keywords]
    if city:
        args.extend(["--city", city])
    return _run_amap(args)


async def _search_nearby(arguments: dict) -> dict:
    lng = str(arguments.get("lng", "")).strip()
    lat = str(arguments.get("lat", "")).strip()
    keywords = str(arguments.get("keywords", "")).strip()
    if not lng or not lat:
        return {"is_error": True, "content": "missing lng/lat coordinates"}
    args = ["around", lng, lat]
    if keywords:
        args.extend(["--keywords", keywords])
    return _run_amap(args)


async def _plan_route(arguments: dict) -> dict:
    origin = str(arguments.get("from", "")).strip()
    dest = str(arguments.get("to", "")).strip()
    mode = str(arguments.get("mode", "drive")).strip()
    if not origin or not dest:
        return {"is_error": True, "content": "missing origin or destination"}
    if mode == "walk":
        return _run_amap(["walk", "--from", origin, "--to", dest])
    return _run_amap(["drive", "--from", origin, "--to", dest])


async def _get_weather(arguments: dict) -> dict:
    city = str(arguments.get("city", "")).strip()
    extensions = str(arguments.get("extensions", "all")).strip()
    if not city:
        return {"is_error": True, "content": "missing city"}
    return _run_amap(["weather", city, "--extensions", extensions])


async def _geocode(arguments: dict) -> dict:
    address = str(arguments.get("address", "")).strip()
    if not address:
        return {"is_error": True, "content": "missing address"}
    return _run_amap(["geocode", address])


def get_amap_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="amap_search_poi",
            description="搜索POI兴趣点",
            category="Web",
            parameters={
                "type": "object",
                "properties": {
                    "keywords": {"type": "string", "description": "搜索关键词"},
                    "city": {"type": "string", "description": "城市名,可选"},
                },
                "required": ["keywords"],
            },
        ),
        ToolSpec(
            name="amap_search_nearby",
            description="搜索附近POI",
            category="Web",
            parameters={
                "type": "object",
                "properties": {
                    "lng": {"type": "string", "description": "经度"},
                    "lat": {"type": "string", "description": "纬度"},
                    "keywords": {"type": "string", "description": "关键词,可选"},
                },
                "required": ["lng", "lat"],
            },
        ),
        ToolSpec(
            name="amap_plan_route",
            description="规划路线",
            category="Web",
            parameters={
                "type": "object",
                "properties": {
                    "from": {"type": "string", "description": "起点地址"},
                    "to": {"type": "string", "description": "终点地址"},
                    "mode": {"type": "string", "description": "方式:drive/walk,默认drive", "enum": ["drive", "walk"]},
                },
                "required": ["from", "to"],
            },
        ),
        ToolSpec(
            name="amap_get_weather",
            description="查询城市天气",
            category="Web",
            parameters={
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名"},
                    "extensions": {"type": "string", "description": "base/all,默认all", "enum": ["base", "all"]},
                },
                "required": ["city"],
            },
        ),
        ToolSpec(
            name="amap_geocode",
            description="地址转坐标",
            category="Web",
            parameters={
                "type": "object",
                "properties": {
                    "address": {"type": "string", "description": "地址文本"},
                },
                "required": ["address"],
            },
        ),
    ]


def get_amap_handlers() -> dict[str, ToolHandler]:
    return {
        "amap_search_poi": _search_poi,
        "amap_search_nearby": _search_nearby,
        "amap_plan_route": _plan_route,
        "amap_get_weather": _get_weather,
        "amap_geocode": _geocode,
    }
