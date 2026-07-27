"""纯 JSON 提取与修复工具。

P6.1 从 ``engine.py`` 拆出：这些函数不依赖任何运行时状态、端口或基础设施，
仅处理字符串到 JSON 的解析、容错提取和括号修复。保持纯函数性质便于单测。
"""

from __future__ import annotations

import json
import re
from typing import Any


def strip_code_fences(text: str) -> str:
    """移除 Markdown 代码围栏（```json ... ``` 或 ``` ... ```）。

    非破坏性：若无围栏则原样返回（仅做 strip）。
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def extract_json_by_brackets(text: str) -> str | None:
    """通过括号配对从文本中提取第一个完整 JSON 对象。

    遍历字符流，跟踪字符串上下文和转义状态，正确处理嵌套 ``{}``。
    找不到完整对象时返回 ``None``。
    """
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == "\\" and in_string:
            escape = True
            continue
        if c == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def extract_json_object(text: str) -> dict[str, Any]:
    """从文本中提取 JSON 对象，容错处理代码围栏和嵌入文本。

    解析顺序：
    1. 去除代码围栏后直接 ``json.loads``；
    2. 失败则用括号配对提取子串再解析；
    3. 仍然失败则抛出原异常。

    若解析结果不是 ``dict``，抛出 ``ValueError``。
    """
    cleaned = strip_code_fences(text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        extracted = extract_json_by_brackets(cleaned)
        if not extracted:
            raise
        data = json.loads(extracted)
    if not isinstance(data, dict):
        raise ValueError("reasoning output was not a JSON object")
    return data


def try_fix_json(text: str) -> str | None:
    """尝试修复被截断的 JSON 字符串。

    修复策略：
    - 若末尾不是 ``}``，统计未闭合的 ``{`` 数量并补齐；
    - 若字符串处于未闭合的引号内，补一个 ``"``。

    输入为空时返回 ``None``；否则返回修复后的字符串（可能未做任何改动）。
    """
    if not text:
        return None
    fixed = text.rstrip()
    if not fixed.endswith("}"):
        depth = 0
        in_string = False
        escape = False
        for c in fixed:
            if escape:
                escape = False
                continue
            if c == "\\" and in_string:
                escape = True
                continue
            if c == '"' and not escape:
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
        if in_string:
            fixed += '"'
        for _ in range(max(0, depth)):
            fixed += "}"
    return fixed
