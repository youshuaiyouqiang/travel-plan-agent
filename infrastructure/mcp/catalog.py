"""MCP 服务器目录扫描与查询（P4.3 重构）.

纯内存数据类（``MCPToolInfo`` / ``MCPServerInfo`` / ``MCPToolRef``）与辅助
函数（``_slug`` / ``_proxy_name`` / ``_tokenize`` / ``_SERVER_HINTS``）已
迁移至 ``domain/shared/mcp/types.py``。本模块仅保留需要磁盘 I/O 的
``MCPCatalog`` 实现，并从 domain 重新导出数据类以维持 ``app.py``、
``infrastructure/mcp/runtime.py`` 与历史测试的兼容写法。

``MCPCatalog`` 实现 ``domain.shared.mcp.ports.MCPCatalogPort``，但不在
本模块显式声明继承——Protocol 为结构化协议，实现方只需方法签名匹配。
"""

from __future__ import annotations

import json
from pathlib import Path

from domain.shared.mcp.types import (  # noqa: F401  re-export for backward compatibility
    MCPToolInfo,
    MCPServerInfo,
    MCPToolRef,
    _SERVER_HINTS,
    _proxy_name,
    _slug,
    _tokenize,
)


class MCPCatalog:
    """MCP 服务器目录扫描器与查询器。

    ``scan()`` 从 ``root_dir`` 读取 ``SERVER_METADATA.json`` / ``INSTRUCTIONS.md``
    / ``tools/*.json``，填充内存状态后即可被 domain 通过
    ``MCPCatalogPort`` 接口消费。构造时不会自动扫描，调用方需显式触发。
    """

    def __init__(self, root_dir: Path) -> None:
        self._root_dir = Path(root_dir)
        self._servers: list[MCPServerInfo] = []

    def scan(self) -> list[MCPServerInfo]:
        """扫描 root_dir 下所有 MCP 服务器目录，返回服务器信息列表。"""
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
                                str(metadata.get("serverIdentifier") or metadata.get("identifier") or server_dir.name),
                                str(tool_raw.get("name", tool_file.stem)),
                            ),
                        )
                    )

            self._servers.append(
                MCPServerInfo(
                    identifier=str(metadata.get("serverIdentifier") or metadata.get("identifier") or server_dir.name),
                    name=str(metadata.get("serverName") or metadata.get("name") or server_dir.name),
                    description=str(metadata.get("serverDescription", "")),
                    instructions=instructions,
                    tools=tools,
                )
            )
        return list(self._servers)

    def list_servers(self) -> list[MCPServerInfo]:
        """返回所有已发现的服务器；首次调用时自动触发扫描。"""
        if not self._servers:
            self.scan()
        return list(self._servers)

    def list_tool_refs(self) -> list[MCPToolRef]:
        """将所有服务器的工具展平为 MCPToolRef 列表。"""
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
        """按 proxy_name 查找工具引用；未找到返回 None。"""
        for ref in self.list_tool_refs():
            if ref.proxy_name == proxy_name:
                return ref
        return None

    def select_tool_refs(self, query: str, limit: int = 4) -> list[MCPToolRef]:
        """根据查询文本打分选择 top-N 工具引用。"""
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
        """构建注入 system prompt 的 MCP 工具说明块。"""
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
        """对单个工具引用与查询文本的匹配度打分。"""
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
