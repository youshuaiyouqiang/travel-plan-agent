"""JSON 序列化辅助函数。

从 ``database.py`` 拆分（P1），供仓储层序列化/反序列化 JSON 列使用。
"""

from __future__ import annotations

import json


def _json_dumps(obj) -> str:
    """序列化为 JSON 字符串，保证非 ASCII 字符原样输出。"""
    return json.dumps(obj, ensure_ascii=False)


def _json_loads(text: str, default=None):
    """反序列化 JSON 字符串；空串或解析失败时返回 ``default``。"""
    if not text:
        return default if default is not None else {}
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return default if default is not None else {}
