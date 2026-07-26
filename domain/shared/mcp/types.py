"""MCP 纯内存数据类型与辅助函数。

P4.3 从 ``infrastructure/mcp/catalog.py`` 迁移：``MCPToolInfo`` /
``MCPServerInfo`` / ``MCPToolRef`` 是不依赖外部 I/O 的纯数据类；
``_SERVER_HINTS`` / ``_slug`` / ``_proxy_name`` / ``_tokenize`` 是纯函数
辅助工具。迁至 domain 后，``infrastructure/mcp/catalog.py`` 继续复用，
``infrastructure/mcp/runtime.py`` 与 domain 消费者均从本模块导入。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class MCPToolInfo:
    """MCP 工具元信息（来自 server 目录下 tools/*.json）。"""

    name: str
    description: str
    input_schema: dict = field(default_factory=dict)
    proxy_name: str = ""


@dataclass
class MCPServerInfo:
    """MCP 服务器元信息（来自 SERVER_METADATA.json + INSTRUCTIONS.md）。"""

    identifier: str
    name: str
    description: str
    instructions: str = ""
    tools: list[MCPToolInfo] = field(default_factory=list)


@dataclass
class MCPToolRef:
    """扁平化的工具引用，供目录查询与 prompt 构建使用。"""

    server_identifier: str
    server_name: str
    tool_name: str
    proxy_name: str
    description: str
    input_schema: dict = field(default_factory=dict)
    instructions: str = ""


# 服务器级提示词，用于 select_tool_refs 的关键词加分
_SERVER_HINTS: dict[str, tuple[str, ...]] = {
    "chrome-devtools": ("browser", "page", "screenshot", "click", "form", "网页", "页面", "截图", "点击", "表单"),
    "web-search": ("search", "news", "lookup", "搜索", "查一下", "新闻", "资料"),
    "wecom-doc": ("wecom", "doc", "todo", "message", "文档", "待办", "消息", "表格"),
    "tencent-docs": ("tencent docs", "docs", "文档", "腾讯文档"),
}


def _slug(value: str) -> str:
    """将任意字符串规范化为 slug（小写字母/数字/下划线）。"""
    return re.sub(r"[^a-z0-9_]+", "_", value.strip().lower()).strip("_")


def _proxy_name(server_identifier: str, tool_name: str) -> str:
    """根据 server identifier 和 tool name 生成稳定的代理工具名。"""
    return f"mcp__{_slug(server_identifier)}__{_slug(tool_name)}"


def _tokenize(text: str) -> list[str]:
    """将文本切分为小写 token（长度 ≥3 的字母数字串），用于打分匹配。"""
    return [token for token in re.findall(r"[a-z0-9_]{3,}", text.lower()) if token]
