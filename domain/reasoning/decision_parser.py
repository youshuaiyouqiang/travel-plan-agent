"""决策解析器 — 从 LLM 输出中解析出 Decision（工具调用或最终答案）。

P6.1 从 ``engine.py`` 拆出：处理 JSON、XML、正则、松散文本等多种格式的
工具调用解析，以及 ``LLMResponse`` 到 ``Decision`` 的转换。依赖
``tool_registry`` 和 ``tool_executor`` 进行工具名验证，但不执行任何 I/O。
"""

from __future__ import annotations

import json
import re
import uuid

from domain.shared.llm.ports import LLMResponse
from domain.shared.tools.executor import ToolExecutor
from domain.shared.tools.registry import ToolRegistry
from domain.shared.types import Decision, DecisionType, ToolCall
from domain.reasoning.json_extract import (
    extract_json_by_brackets,
    extract_json_object,
    try_fix_json,
)
from domain.reasoning.text_cleaning import clean_final_answer, strip_tool_calls_from_text


def make_signature(call: ToolCall) -> str:
    """生成工具调用的去重签名（name + 排序后的 arguments JSON）。

    用于检测重复的工具调用模式：同一 name + 同一 arguments 视为重复。
    """
    try:
        args = json.dumps(call.arguments, sort_keys=True, ensure_ascii=False)
    except Exception:
        args = str(call.arguments)
    return f"{call.name}:{args}"


def parse_kwargs(args_str: str) -> dict[str, str]:
    """从函数调用参数字符串中解析 key=value 对。

    支持双引号和单引号两种格式；同名 key 以先匹配的双引号形式为准。
    """
    result: dict[str, str] = {}
    for match in re.finditer(r'(\w+)\s*=\s*"([^"]*)"', args_str):
        result[match.group(1)] = match.group(2)
    for match in re.finditer(r"(\w+)\s*=\s*'([^']*)'", args_str):
        if match.group(1) not in result:
            result[match.group(1)] = match.group(2)
    return result


# 正则：匹配 {"name": "...", "arguments": {...}} 形式的工具调用项
_TOOL_CALL_ITEM_RE = re.compile(
    r'\{\s*"name"\s*:\s*"([^"]+)"\s*,\s*"(?:arguments|args)"\s*:\s*(\{[^}]*\})\s*\}',
    re.DOTALL,
)

# 正则：匹配 <tool_call>...</tool_call> 形式的 XML 工具调用
_XML_TOOL_RE = re.compile(
    r"<tool_call[^>]*>\s*\n?(.*?)(?:</tool_call|(?=<tool_call)|$)",
    re.DOTALL | re.IGNORECASE,
)


class DecisionParser:
    """从 LLM 输出中解析 ``Decision``。

    持有 ``tool_registry`` 和 ``tool_executor`` 引用用于工具名验证，
    但不执行任何工具调用或 I/O 操作。所有方法为同步纯逻辑。
    """

    def __init__(
        self,
        *,
        tool_registry: ToolRegistry,
        tool_executor: ToolExecutor | None = None,
    ) -> None:
        self._tool_registry = tool_registry
        self._tool_executor = tool_executor

    def _known_tool_names(self) -> set[str]:
        """返回当前已注册的工具名集合；无 executor 时返回空集（跳过验证）。"""
        if self._tool_executor:
            return set(self._tool_executor.list_tool_names())
        return set()

    def try_parse_tool_calls_from_text(self, text: str) -> list[ToolCall] | None:
        """尝试从模型输出的文本中解析出 tool_calls。

        某些模型（如通义千问）在需要调用工具时，不通过 API 的 tool_calls 字段返回，
        而是直接在 content 中输出 tool call JSON，例如：
        ``{"tool_calls": [{"name": "fliggy_search_flight", "args": {...}}]}``

        若已知工具列表不为空且解析出的工具名不在列表中，返回 ``None``。
        """
        stripped = text.strip()
        if not stripped:
            return None
        # 快速判断：如果文本中不包含 tool_calls 关键字，直接跳过
        if '"tool_calls"' not in stripped and "'tool_calls'" not in stripped:
            return None
        try:
            data = extract_json_object(stripped)
        except Exception:
            return None
        raw_calls = data.get("tool_calls")
        if not raw_calls or not isinstance(raw_calls, list):
            return None
        # 验证是否是合法的 tool call 结构
        valid_calls: list[ToolCall] = []
        known_tools = self._known_tool_names()
        for item in raw_calls:
            if not isinstance(item, dict):
                return None
            name = item.get("name") or item.get("function", {}).get("name")
            if not name:
                return None
            # 如果已知工具列表不为空，检查是否是已知工具
            if known_tools and name not in known_tools:
                return None
            args = item.get("arguments") or item.get("args") or item.get("function", {}).get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (json.JSONDecodeError, ValueError):
                    args = {}
            if not isinstance(args, dict):
                return None
            valid_calls.append(ToolCall(name=str(name), arguments=args, call_id=str(item.get("id", uuid.uuid4()))))
        return valid_calls if valid_calls else None

    def llm_response_to_decision(self, llm_resp: LLMResponse) -> Decision:
        """将 ``LLMResponse`` 转换为 ``Decision``。

        优先使用原生 ``tool_calls`` 字段；若为空则尝试从 content 中解析。
        content 既无工具调用也非空时视为最终答案。
        """
        if llm_resp.has_tool_calls and llm_resp.tool_calls:
            tool_calls = [
                ToolCall(
                    name=tc.name,
                    arguments=tc.arguments,
                    call_id=tc.id or str(uuid.uuid4()),
                )
                for tc in llm_resp.tool_calls
            ]
            return Decision(
                decision_type=DecisionType.TOOL_CALLS,
                text=llm_resp.content or "",
                tool_calls=tool_calls,
            )
        content = llm_resp.content or ""
        # 某些模型不通过 tool_calls 字段返回，而是在 content 中直接输出 tool call JSON
        parsed = self.try_parse_tool_calls_from_text(content)
        if parsed:
            return Decision(
                decision_type=DecisionType.TOOL_CALLS,
                text="",
                tool_calls=parsed,
            )
        if content.strip():
            return Decision(
                decision_type=DecisionType.FINAL_ANSWER,
                text=content,
            )
        return Decision(decision_type=DecisionType.FINAL_ANSWER, text="")

    def parse_decision(self, text: str) -> Decision:
        """从文本中解析出 ``Decision``。

        解析顺序：
        1. 尝试 JSON 解析（含 ``tool_calls`` 则为工具调用，否则为最终答案）；
        2. JSON 失败则依次尝试 XML、正则、松散文本解析；
        3. 全部失败则清理文本后作为最终答案。
        """
        stripped = text.strip()
        try:
            data = extract_json_object(stripped)
        except Exception:
            xml_result = self._try_parse_xml_tool_calls(stripped)
            if xml_result:
                return xml_result
            regex_result = self._try_parse_regex_tool_calls(stripped)
            if regex_result:
                return regex_result
            loose_result = self._try_loose_tool_call_parse(stripped)
            if loose_result:
                return loose_result
            safe_text = clean_final_answer(stripped)
            return Decision(decision_type=DecisionType.FINAL_ANSWER, text=safe_text or stripped)

        raw_calls = data.get("tool_calls")
        if not raw_calls:
            plain_text = str(data.get("text", "")).strip()
            xml_result = self._try_parse_xml_tool_calls(plain_text)
            if xml_result:
                return xml_result
            return Decision(
                decision_type=DecisionType.FINAL_ANSWER,
                text=plain_text,
                raw=data,
            )

        tool_calls = [
            ToolCall(
                name=str(item["name"]),
                arguments=dict(item.get("arguments") or item.get("args") or {}),
                call_id=str(item.get("id", uuid.uuid4())),
            )
            for item in raw_calls
        ]
        clean_text = strip_tool_calls_from_text(str(data.get("text", "")))
        return Decision(
            decision_type=DecisionType.TOOL_CALLS,
            text=clean_text,
            tool_calls=tool_calls,
            raw=data,
        )

    def _try_loose_tool_call_parse(self, text: str) -> Decision | None:
        """松散解析：从包含 ``tool_calls`` 关键字的文本中用括号配对提取 JSON。

        若直接解析失败，尝试用 ``try_fix_json`` 修复截断的 JSON。
        """
        if '"tool_calls"' not in text:
            return None
        json_str = extract_json_by_brackets(text)
        if not json_str:
            return None
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            fixed = try_fix_json(json_str)
            if fixed:
                try:
                    data = json.loads(fixed)
                except json.JSONDecodeError:
                    return None
            else:
                return None
        if not isinstance(data, dict):
            return None
        raw_calls = data.get("tool_calls")
        if not raw_calls or not isinstance(raw_calls, list):
            return None
        tool_calls: list[ToolCall] = []
        for item in raw_calls:
            if not isinstance(item, dict) or "name" not in item:
                continue
            tool_calls.append(
                ToolCall(
                    name=str(item["name"]),
                    arguments=dict(item.get("arguments") or item.get("args") or {}),
                    call_id=str(item.get("id", uuid.uuid4())),
                )
            )
        if not tool_calls:
            return None
        clean_text = strip_tool_calls_from_text(str(data.get("text", "")))
        return Decision(
            decision_type=DecisionType.TOOL_CALLS,
            text=clean_text,
            tool_calls=tool_calls,
            raw=data,
        )

    def _try_parse_regex_tool_calls(self, text: str) -> Decision | None:
        """正则解析：从文本中用正则匹配 ``{"name": "...", "arguments": {...}}`` 形式的工具调用。"""
        if '"tool_calls"' not in text and '"name"' not in text:
            return None
        items = list(_TOOL_CALL_ITEM_RE.finditer(text))
        if not items:
            return None
        calls: list[ToolCall] = []
        for match in items:
            name = match.group(1)
            args_str = match.group(2)
            try:
                arguments = json.loads(args_str)
            except (json.JSONDecodeError, ValueError):
                arguments = parse_kwargs(args_str)
            if not isinstance(arguments, dict):
                arguments = {}
            calls.append(ToolCall(name=name, arguments=arguments, call_id=str(uuid.uuid4())))
        if not calls:
            return None
        plain_text = _TOOL_CALL_ITEM_RE.sub("", text)
        plain_text = re.sub(r'["\']tool_calls["\']\s*:\s*\[[\s\S]*?\]', "", plain_text)
        plain_text = re.sub(r'\{[\s\S]*?["\']tool_calls["\'][\s\S]*\}', "", plain_text)
        plain_text = re.sub(r'tool_calls["\']?\s*:\s*\[[\s\S]*?\]', "", plain_text)
        plain_text = re.sub(r"\n{3,}", "\n\n", plain_text).strip()
        return Decision(
            decision_type=DecisionType.TOOL_CALLS,
            text=plain_text,
            tool_calls=calls,
        )

    def _try_parse_xml_tool_calls(self, text: str) -> Decision | None:
        """XML 解析：从 ``<tool_call>func(args)</tool_call>`` 形式中提取工具调用。"""
        calls: list[ToolCall] = []
        for match in _XML_TOOL_RE.finditer(text):
            inner = match.group(1).strip()
            parsed = self._parse_xml_func_call(inner)
            if parsed:
                calls.append(parsed)
        if not calls:
            return None
        plain_text = _XML_TOOL_RE.sub("", text).strip()
        plain_text = re.sub(r"\n{3,}", "\n\n", plain_text)
        return Decision(
            decision_type=DecisionType.TOOL_CALLS,
            text=plain_text,
            tool_calls=calls,
        )

    def _parse_xml_func_call(self, inner: str) -> ToolCall | None:
        """解析单个 XML 工具调用的内部文本 ``func_name(key="value", ...)``。"""
        inner = inner.strip()
        match = re.match(r"\s*([a-zA-Z_][a-zA-Z_0-9]*)\s*\((.*)\)\s*$", inner, re.DOTALL)
        if not match:
            return None
        name = match.group(1)
        args_str = match.group(2)
        args = parse_kwargs(args_str)
        if self._tool_registry.has(name):
            return ToolCall(name=name, arguments=args, call_id=str(uuid.uuid4()))
        if name.startswith(("fliggy_", "amap_", "save_")):
            return ToolCall(name=name, arguments=args, call_id=str(uuid.uuid4()))
        return None
