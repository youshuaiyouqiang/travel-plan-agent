from __future__ import annotations

import json
import logging
import os
import re
import subprocess

from infrastructure.tools.base import ToolHandler, ToolSpec, bind_tool
from config import settings

logger = logging.getLogger(__name__)

QWEATHER_KEY = os.environ.get("WEATHER_API_KEY", "")
_SCRIPT = str(settings.skills_dir / "q-weather" / "scripts" / "qweather_tool.py")

# 输入校验：城市名只允许中文/英文/数字/连字符，防止命令注入
_LOCATION_RE = re.compile(r"^[\u4e00-\u9fa5a-zA-Z0-9\-]+$")


def _validate_location(location: str) -> str | None:
    """校验城市名输入，返回错误信息或 None（通过）"""
    if not location:
        return "missing location"
    if len(location) > 50:
        return "location too long (max 50 chars)"
    if not _LOCATION_RE.match(location):
        return "location contains invalid characters"
    return None


def _check_qweather_key() -> str | None:
    """KEY 校验（启动时 & 调用时均可调用）"""
    if not QWEATHER_KEY:
        return "WEATHER_API_KEY 环境变量未设置，和风天气工具不可用"
    return None


def _run_qweather(args: list[str]) -> dict:
    # 调用时再次校验 KEY
    key_err = _check_qweather_key()
    if key_err:
        return {"is_error": True, "content": key_err}

    cmd = ["python", _SCRIPT] + args
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, env={**os.environ, "WEATHER_API_KEY": QWEATHER_KEY}
        )
        if result.returncode != 0:
            return {"is_error": True, "content": f"和风天气调用失败: {result.stderr[:500]}"}
        try:
            data = json.loads(result.stdout)
            return {"is_error": False, "content": json.dumps(data, ensure_ascii=False, indent=2)}
        except json.JSONDecodeError:
            return {"is_error": False, "content": result.stdout[:3000]}
    except subprocess.TimeoutExpired:
        return {"is_error": True, "content": "和风天气请求超时"}
    except Exception as e:
        return {"is_error": True, "content": f"和风天气调用异常: {e}"}


async def _qweather_city_lookup(arguments: dict) -> dict:
    location = str(arguments.get("location", "")).strip()
    err = _validate_location(location)
    if err:
        return {"is_error": True, "content": err}
    return _run_qweather(["lookup", location])


async def _qweather_now(arguments: dict) -> dict:
    location = str(arguments.get("location", "")).strip()
    err = _validate_location(location)
    if err:
        return {"is_error": True, "content": err}
    return _run_qweather(["now", location])


async def _qweather_forecast(arguments: dict) -> dict:
    """逐日天气预报（核心工具）"""
    location = str(arguments.get("location", "")).strip()
    err = _validate_location(location)
    if err:
        return {"is_error": True, "content": err}
    days = int(arguments.get("days", 7))
    if days not in [3, 7, 10, 15, 30]:
        days = 7
    return _run_qweather(["daily", location, "--days", str(days)])


async def _qweather_hourly(arguments: dict) -> dict:
    location = str(arguments.get("location", "")).strip()
    err = _validate_location(location)
    if err:
        return {"is_error": True, "content": err}
    hours = int(arguments.get("hours", 24))
    if hours not in [24, 72, 168]:
        hours = 24
    return _run_qweather(["hourly", location, "--hours", str(hours)])


def get_qweather_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="qweather_forecast",
            description="查询目的地未来多日天气预报（温度、天气现象、风力、降水概率），用于行程规划中的天气评估",
            category="Web",
            parameters={
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "城市名称或地点ID，如'北京'"},
                    "days": {"type": "integer", "description": "预报天数: 3/7/10/15/30, 默认7"},
                },
                "required": ["location"],
            },
        ),
        ToolSpec(
            name="qweather_now",
            description="查询城市实时天气",
            category="Web",
            parameters={
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "城市名称"},
                },
                "required": ["location"],
            },
        ),
    ]


def get_qweather_handlers() -> dict[str, ToolHandler]:
    return {
        "qweather_forecast": _qweather_forecast,
        "qweather_now": _qweather_now,
    }
