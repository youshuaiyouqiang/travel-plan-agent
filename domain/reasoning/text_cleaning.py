"""最终答案文本规范化工具。

P6.1 从 ``engine.py`` 拆出：这些函数负责从 LLM 输出中清除工具调用残留
JSON、推理过程前缀和代码围栏，产出可直接展示给用户的纯文本。保持纯函数
性质便于单测；不依赖任何运行时状态或端口。
"""

from __future__ import annotations

import json
import re

from domain.reasoning.json_extract import strip_code_fences


def looks_grounded(text: str) -> bool:
    """判断最终答案是否"有实质内容"而非空泛确认。

    规则：
    - 长度 < 12 视为不 grounded；
    - 命中弱模式（done/ok/finished 等）视为不 grounded；
    - 仅含确认问句（如"您对这个行程满意吗"）且无行程内容标记时视为不 grounded。
    """
    clean = text.strip()
    if len(clean) < 12:
        return False
    weak_patterns = (
        "done",
        "finished",
        "completed",
        "ok",
        "tool ok",
        "task complete",
    )
    lowered = clean.lower()
    if lowered in weak_patterns:
        return False
    confirmation_only_patterns = (
        "您对这个行程满意吗",
        "满意的话我将为您生成",
        "不满意可以告诉我",
        "是否满意",
    )
    has_confirmation_only = any(p in clean for p in confirmation_only_patterns)
    if has_confirmation_only:
        content_markers = (
            "第1天",
            "第一天",
            "Day 1",
            "行程安排",
            "每日行程",
            "交通",
            "住宿",
            "景点",
            "预算",
            "推荐",
            "高铁",
            "机票",
            "酒店",
            "元",
        )
        has_real_content = any(m in clean for m in content_markers)
        if not has_real_content:
            return False
    return True


# 推理过程前缀模式：模型有时会在最终答案前输出"现在我有足够信息..."之类的
# 内部独白，需要逐行剔除。
REASONING_PATTERNS: list[str] = [
    r"(?:Now|So)\s+I\s+have\s+enough\s+information.*?(?=\n)",
    r"Let\s+me\s+(?:now\s+)?(?:compile|save|create|generate|summarize|put|write|provide).*?(?=\n)",
    r"Key\s+findings?\s*:\s*",
    r"I\s+will\s+now\s+.*?(?=\n)",
    r"Let(?:\'s| us)\s+(?:now\s+)?(?:proceed|move|start|begin|compile|create|generate|save|put|write).*?(?=\n)",
    r"Based\s+on\s+(?:the\s+)?(?:above|these|tool|search|following)\s+(?:results?|data|information|findings).*?(?=\n)",
    r"With\s+(?:all\s+)?(?:the\s+)?(?:above|these|tool)\s+(?:results?|data|information).*?(?=\n)",
]


def strip_reasoning_prefix(text: str) -> str:
    """逐行移除推理过程前缀（如"Now I have enough information..."）。"""
    lines = text.split("\n")
    result_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        is_reasoning = False
        for pattern in REASONING_PATTERNS:
            if re.match(pattern, stripped, re.IGNORECASE):
                is_reasoning = True
                break
        if not is_reasoning:
            result_lines.append(line)
    cleaned = "\n".join(result_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def clean_final_answer(text: str) -> str:
    """清理最终答案：去除代码围栏、残留 tool_calls JSON、XML 标签和推理前缀。

    处理顺序：
    1. 去围栏；
    2. 尝试整体解析为 JSON，若含 tool_calls/tool_results/text 则只取 text；
    3. 正则提取残留的 "text" 字段值；
    4. 正则移除各种 tool_calls 片段和 XML 标签；
    5. 压缩多余空行并移除推理前缀。
    """
    cleaned = text.strip()
    cleaned = strip_code_fences(cleaned)
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            if "tool_calls" in data or "tool_results" in data or "text" in data:
                text_only = str(data.get("text", "")).strip()
                if text_only:
                    return strip_reasoning_prefix(text_only)
                cleaned = ""
    except (json.JSONDecodeError, ValueError):
        pass
    if '"text"' in cleaned and (
        '"tool_calls"' in cleaned or '"tool_results"' in cleaned or '"arguments"' in cleaned
    ):
        text_match = re.search(r'"text"\s*:\s*"((?:[^"\\]|\\.)*)"', cleaned)
        if text_match:
            extracted = text_match.group(1)
            try:
                extracted = json.loads('"' + extracted + '"')
            except Exception:
                pass
            if extracted.strip():
                return strip_reasoning_prefix(extracted.strip())
    if '"tool_results"' in cleaned:
        text_match = re.search(r'"text"\s*:\s*"((?:[^"\\]|\\.)*)"', cleaned)
        if text_match:
            extracted = text_match.group(1)
            try:
                extracted = json.loads('"' + extracted + '"')
            except Exception:
                pass
            if extracted.strip():
                return strip_reasoning_prefix(extracted.strip())
        cleaned = re.sub(r'\{[^{}]*"tool_results"\s*:\s*\[.*?\][^{}]*\}', "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(
        r'\{[^{}]*"tool_calls"\s*:\s*\[[^\]]*\][^{}]*\}',
        "",
        cleaned,
        flags=re.DOTALL,
    )
    cleaned = re.sub(
        r'["\']tool_calls["\']\s*:\s*\[[^\]]*\]\s*,?',
        "",
        cleaned,
        flags=re.DOTALL,
    )
    cleaned = re.sub(
        r'\{\s*"name"\s*:\s*"[^"]+"\s*,\s*"arguments"\s*:\s*\{[^}]*\}\s*\}',
        "",
        cleaned,
        flags=re.DOTALL,
    )
    cleaned = re.sub(
        r'tool_calls["\']?\s*:\s*\[[^\]]*\]',
        "",
        cleaned,
        flags=re.DOTALL,
    )
    xml_pattern = r"<tool_call[^>]*>.*?</tool_call"
    cleaned = re.sub(xml_pattern + ">", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = strip_reasoning_prefix(cleaned)
    return cleaned.strip()


def strip_tool_calls_from_text(text: str) -> str:
    """从文本中移除所有 tool_calls JSON 片段，保留纯文本部分。"""
    cleaned = clean_final_answer(text)
    cleaned = re.sub(r'\{[\s\S]*?"tool_calls"[\s\S]*?\}', "", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
