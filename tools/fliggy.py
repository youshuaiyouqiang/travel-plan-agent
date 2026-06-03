from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess

from .base import ToolHandler, ToolSpec, bind_tool

logger = logging.getLogger(__name__)

_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "skills", "fliggy-travel", "scripts", "flyai_quick.py")


def _find_flyai() -> str | None:
    env_bin = os.environ.get("FLYAI_BIN", "").strip()
    if env_bin and os.path.exists(env_bin):
        return env_bin
    return shutil.which("flyai")


def _run_flyai(args: list[str]) -> dict:
    flyai_bin = _find_flyai()
    if not flyai_bin:
        return {"is_error": True, "content": "flyai-cli 未安装，请先运行 skills/fliggy-travel/scripts/setup.py"}
    cmd = [flyai_bin] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, encoding="utf-8", errors="replace")
        output = (result.stdout or "").strip() or (result.stderr or "").strip()
        if not output:
            return {"is_error": True, "content": "飞猪搜索无结果"}
        try:
            data = json.loads(output)
            return {"is_error": False, "content": json.dumps(data, ensure_ascii=False, indent=2)}
        except json.JSONDecodeError:
            return {"is_error": False, "content": output[:3000]}
    except subprocess.TimeoutExpired:
        return {"is_error": True, "content": "飞猪搜索超时"}
    except Exception as e:
        return {"is_error": True, "content": f"飞猪搜索异常: {e}"}


def _normalize_transport_args(arguments: dict) -> dict:
    mapping = {
        "origin": ["origin", "from", "departure", "departure_city", "start_city", "start"],
        "destination": ["destination", "to", "arrival", "arrival_city", "end_city", "end", "city"],
        "date": ["date", "dep_date", "departure_date", "depDate", "travel_date", "start_date"],
    }
    result = {}
    for canonical, variants in mapping.items():
        for v in variants:
            if v in arguments and arguments[v]:
                result[canonical] = arguments[v]
                break
    return result


async def _search_flight(arguments: dict) -> dict:
    normalized = _normalize_transport_args(arguments)
    origin = str(normalized.get("origin", "")).strip()
    destination = str(normalized.get("destination", "")).strip()
    dep_date = str(normalized.get("date", "")).strip()
    if not origin or not destination or not dep_date:
        return {"is_error": True, "content": "missing origin/destination/date"}
    return _run_flyai(["search-flight", "--origin", origin, "--destination", destination, "--dep-date", dep_date])


async def _search_train(arguments: dict) -> dict:
    normalized = _normalize_transport_args(arguments)
    origin = str(normalized.get("origin", "")).strip()
    destination = str(normalized.get("destination", "")).strip()
    dep_date = str(normalized.get("date", "")).strip()
    if not origin or not destination or not dep_date:
        return {"is_error": True, "content": "missing origin/destination/date"}
    return _run_flyai(["search-train", "--origin", origin, "--destination", destination, "--dep-date", dep_date])


def _normalize_hotel_args(arguments: dict) -> dict:
    mapping = {
        "destination": ["destination", "city", "dest", "dest_name", "location"],
        "check_in": ["check_in", "checkIn", "checkin", "checkInDate", "check_in_date", "checkin_date", "startDate", "start_date"],
        "check_out": ["check_out", "checkOut", "checkout", "checkOutDate", "check_out_date", "checkout_date", "endDate", "end_date"],
    }
    result = {}
    for canonical, variants in mapping.items():
        for v in variants:
            if v in arguments and arguments[v]:
                result[canonical] = arguments[v]
                break
    return result


async def _search_hotel(arguments: dict) -> dict:
    normalized = _normalize_hotel_args(arguments)
    dest_name = str(normalized.get("destination", "")).strip()
    check_in = str(normalized.get("check_in", "")).strip()
    check_out = str(normalized.get("check_out", "")).strip()
    if not dest_name or not check_in or not check_out:
        return {"is_error": True, "content": "missing destination/check_in/check_out"}
    return _run_flyai(["search-hotel", "--dest-name", dest_name, "--check-in-date", check_in, "--check-out-date", check_out])


async def _keyword_search(arguments: dict) -> dict:
    query = str(arguments.get("query", "")).strip()
    if not query:
        return {"is_error": True, "content": "missing query"}
    return _run_flyai(["keyword-search", "--query", query])


async def _ai_search(arguments: dict) -> dict:
    query = str(arguments.get("query", "")).strip()
    if not query:
        return {"is_error": True, "content": "missing query"}
    return _run_flyai(["ai-search", "--query", query])


def get_fliggy_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="fliggy_search_flight",
            description="搜索机票",
            category="Web",
            parameters={
                "type": "object",
                "properties": {
                    "origin": {"type": "string", "description": "出发城市"},
                    "destination": {"type": "string", "description": "目的城市"},
                    "date": {"type": "string", "description": "出发日期,格式YYYY-MM-DD。如果用户说'明天''下周一'等相对日期,请根据当前日期推算为具体日期,不要反问用户"},
                },
                "required": ["origin", "destination", "date"],
            },
        ),
        ToolSpec(
            name="fliggy_search_train",
            description="搜索火车/高铁票",
            category="Web",
            parameters={
                "type": "object",
                "properties": {
                    "origin": {"type": "string", "description": "出发城市"},
                    "destination": {"type": "string", "description": "目的城市"},
                    "date": {"type": "string", "description": "出发日期,格式YYYY-MM-DD。如果用户说'明天''下周一'等相对日期,请根据当前日期推算为具体日期,不要反问用户"},
                },
                "required": ["origin", "destination", "date"],
            },
        ),
        ToolSpec(
            name="fliggy_search_hotel",
            description="搜索酒店",
            category="Web",
            parameters={
                "type": "object",
                "properties": {
                    "destination": {"type": "string", "description": "目的城市"},
                    "check_in": {"type": "string", "description": "入住日期,格式YYYY-MM-DD。如果用户说'明天'等相对日期,请根据当前日期推算为具体日期,不要反问用户"},
                    "check_out": {"type": "string", "description": "退房日期,格式YYYY-MM-DD。根据入住日期和游玩天数推算,不要反问用户"},
                },
                "required": ["destination", "check_in", "check_out"],
            },
        ),
        ToolSpec(
            name="fliggy_keyword_search",
            description="飞猪关键词搜索，支持机票、酒店、景点等",
            category="Web",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                },
                "required": ["query"],
            },
        ),
        ToolSpec(
            name="fliggy_ai_search",
            description="飞猪AI语义搜索，理解复杂旅行意图",
            category="Web",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "自然语言搜索描述"},
                },
                "required": ["query"],
            },
        ),
    ]


def get_fliggy_handlers() -> dict[str, ToolHandler]:
    return {
        "fliggy_search_flight": _search_flight,
        "fliggy_search_train": _search_train,
        "fliggy_search_hotel": _search_hotel,
        "fliggy_keyword_search": _keyword_search,
        "fliggy_ai_search": _ai_search,
    }
