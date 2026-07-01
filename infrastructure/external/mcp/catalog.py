from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MCPToolInfo:
    name: str
    description: str
    input_schema: dict = field(default_factory=dict)
    proxy_name: str = ""


@dataclass
class MCPServerInfo:
    identifier: str
    name: str
    description: str
    instructions: str = ""
    tools: list[MCPToolInfo] = field(default_factory=list)


@dataclass
class MCPToolRef:
    server_identifier: str
    server_name: str
    tool_name: str
    proxy_name: str
    description: str
    input_schema: dict = field(default_factory=dict)
    instructions: str = ""


_SERVER_HINTS: dict[str, tuple[str, ...]] = {
    "chrome-devtools": ("browser", "page", "screenshot", "click", "form", "网页", "页面", "截图", "点击", "表单"),
    "web-search": ("search", "news", "lookup", "搜索", "查一下", "新闻", "资料"),
    "wecom-doc": ("wecom", "doc", "todo", "message", "文档", "待办", "消息", "表格"),
    "tencent-docs": ("tencent docs", "docs", "文档", "腾讯文档"),
}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", value.strip().lower()).strip("_")


def _proxy_name(server_identifier: str, tool_name: str) -> str:
    return f"mcp__{_slug(server_identifier)}__{_slug(tool_name)}"


def _tokenize(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9_]{3,}", text.lower()) if token]


class MCPCatalog:
    def __init__(self, root_dir: Path) -> None:
        self._root_dir = Path(root_dir)
        self._servers: list[MCPServerInfo] = []

    def scan(self) -> list[MCPServerInfo]:
        self._servers = []
        if not self._root_dir.exists():
            return []

        for server_dir in sorted(self._root_dir.iterdir()):
            if not server_dir.is_dir():
                continue
            metadata_file = server_dir / "SERVER_METADATA.json"
            if not metadata_file.exists():
                continue
            try:
                metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
            except Exception:
                continue

            instructions = ""
            instructions_file = server_dir / "INSTRUCTIONS.md"
            if instructions_file.exists():
                instructions = instructions_file.read_text(encoding="utf-8")

            tools: list[MCPToolInfo] = []
            tools_dir = server_dir / "tools"
            if tools_dir.exists():
                for tool_file in sorted(tools_dir.glob("*.json")):
                    try:
                        tool_raw = json.loads(tool_file.read_text(encoding="utf-8"))
                    except Exception:
                        continue
                    tools.append(
                        MCPToolInfo(
                            name=str(tool_raw.get("name", tool_file.stem)),
                            description=str(tool_raw.get("description", "")),
                            input_schema=dict(tool_raw.get("inputSchema", {})),
                            proxy_name=_proxy_name(
                                str(
                                    metadata.get("serverIdentifier")
                                    or metadata.get("identifier")
                                    or server_dir.name
                                ),
                                str(tool_raw.get("name", tool_file.stem)),
                            ),
                        )
                    )

            self._servers.append(
                MCPServerInfo(
                    identifier=str(
                        metadata.get("serverIdentifier")
                        or metadata.get("identifier")
                        or server_dir.name
                    ),
                    name=str(metadata.get("serverName") or metadata.get("name") or server_dir.name),
                    description=str(metadata.get("serverDescription", "")),
                    instructions=instructions,
                    tools=tools,
                )
            )
        return list(self._servers)

    def list_servers(self) -> list[MCPServerInfo]:
        if not self._servers:
            self.scan()
        return list(self._servers)

    def list_tool_refs(self) -> list[MCPToolRef]:
        refs: list[MCPToolRef] = []
        for server in self.list_servers():
            for tool in server.tools:
                refs.append(
                    MCPToolRef(
                        server_identifier=server.identifier,
                        server_name=server.name,
                        tool_name=tool.name,
                        proxy_name=tool.proxy_name or _proxy_name(server.identifier, tool.name),
                        description=tool.description,
                        input_schema=tool.input_schema,
                        instructions=server.instructions,
                    )
                )
        return refs

    def get_tool_ref(self, proxy_name: str) -> MCPToolRef | None:
        for ref in self.list_tool_refs():
            if ref.proxy_name == proxy_name:
                return ref
        return None

    def select_tool_refs(self, query: str, limit: int = 4) -> list[MCPToolRef]:
        text = query.strip().lower()
        if not text:
            return []

        query_tokens = _tokenize(text)
        scored: list[tuple[int, MCPToolRef]] = []
        for ref in self.list_tool_refs():
            score = self._score_tool_ref(ref, text, query_tokens)
            if score > 0:
                scored.append((score, ref))

        scored.sort(key=lambda item: (-item[0], item[1].proxy_name))
        return [ref for _, ref in scored[:limit]]

    def build_prompt_block(
        self,
        *,
        query: str = "",
        limit: int = 4,
        tool_refs: list[MCPToolRef] | None = None,
    ) -> str:
        refs = (
            list(tool_refs)
            if tool_refs is not None
            else (self.select_tool_refs(query, limit=limit) if query.strip() else self.list_tool_refs())
        )
        if not refs:
            return ""

        lines = [
            "## Available MCP Proxy Tools",
            "",
            "These MCP proxy tools are available in this round and can be called directly.",
            "Call the proxy tool name exactly as shown below.",
            "",
        ]
        for ref in refs:
            lines.append(
                f"- `{ref.proxy_name}` -> `{ref.server_identifier}.{ref.tool_name}`: {ref.description or 'No description'}"
            )
        return "\n".join(lines).strip()

    def _score_tool_ref(self, ref: MCPToolRef, text: str, query_tokens: list[str]) -> int:
        score = 0
        server_key = ref.server_identifier.lower()
        tool_key = ref.tool_name.lower()
        searchable = " ".join(
            [
                ref.server_identifier,
                ref.server_name,
                ref.tool_name,
                ref.description,
                ref.instructions[:400],
            ]
        ).lower()

        if tool_key and tool_key in text:
            score += 8
        if server_key and server_key in text:
            score += 6

        for hint in _SERVER_HINTS.get(ref.server_identifier, ()):
            if hint.lower() in text:
                score += 4

        for token in query_tokens:
            if token in searchable:
                score += 1

        return score


