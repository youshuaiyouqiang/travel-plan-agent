"""Tests for core/mcp_catalog.py — MCPCatalog, MCPToolRef, tool selection"""
import json
from pathlib import Path

import pytest

from infrastructure.mcp.catalog import MCPCatalog, MCPServerInfo, MCPToolInfo, MCPToolRef, _proxy_name, _tokenize


class TestHelperFunctions:
    def test_proxy_name(self):
        result = _proxy_name("web-search", "web_search")
        assert result == "mcp__web_search__web_search"

    def test_proxy_name_special_chars(self):
        result = _proxy_name("Chrome DevTools", "Take Screenshot")
        assert "chrome" in result.lower()
        assert "take" in result.lower()

    def test_tokenize(self):
        tokens = _tokenize("search for AI agent news")
        assert "search" in tokens
        assert "for" in tokens    # "for" is 3 chars, {3,} matches >= 3
        assert "agent" in tokens
        assert "news" in tokens
        # "AI" (lowercase "ai") is 2 chars, too short for {3,}
        assert "ai" not in tokens
        # Single-letter tokens also excluded
        assert "i" not in tokens

    def test_tokenize_chinese(self):
        # Chinese chars don't match [a-z0-9_]{3,}
        tokens = _tokenize("搜索最新新闻")
        assert len(tokens) == 0


class TestMCPCatalog:
    def _create_mock_mcp_dir(self, tmp_path: Path):
        """Create a mock MCP directory structure for testing."""
        server_dir = tmp_path / "test-server"
        server_dir.mkdir()

        metadata = {
            "serverIdentifier": "test-server",
            "serverName": "Test Server",
            "serverDescription": "A mock MCP server for testing",
        }
        (server_dir / "SERVER_METADATA.json").write_text(
            json.dumps(metadata), encoding="utf-8"
        )
        (server_dir / "INSTRUCTIONS.md").write_text(
            "This is a test MCP server.", encoding="utf-8"
        )

        tools_dir = server_dir / "tools"
        tools_dir.mkdir()

        tool1 = {
            "name": "search",
            "description": "Search for information",
            "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}},
        }
        (tools_dir / "search.json").write_text(
            json.dumps(tool1), encoding="utf-8"
        )

        tool2 = {
            "name": "calculate",
            "description": "Calculate mathematical expressions",
            "inputSchema": {"type": "object", "properties": {"expression": {"type": "string"}}},
        }
        (tools_dir / "calculate.json").write_text(
            json.dumps(tool2), encoding="utf-8"
        )

        return tmp_path

    def test_scan_empty_dir(self, tmp_path: Path):
        catalog = MCPCatalog(root_dir=tmp_path)
        servers = catalog.scan()
        assert servers == []

    def test_scan_with_mock_server(self, tmp_path: Path):
        mcp_dir = self._create_mock_mcp_dir(tmp_path)
        catalog = MCPCatalog(root_dir=mcp_dir)
        servers = catalog.scan()
        assert len(servers) == 1
        assert servers[0].identifier == "test-server"
        assert servers[0].name == "Test Server"
        assert len(servers[0].tools) == 2

    def test_list_servers(self, tmp_path: Path):
        mcp_dir = self._create_mock_mcp_dir(tmp_path)
        catalog = MCPCatalog(root_dir=mcp_dir)
        servers = catalog.list_servers()
        assert len(servers) == 1
        # list_servers auto-scans if empty
        assert servers[0].identifier == "test-server"

    def test_list_tool_refs(self, tmp_path: Path):
        mcp_dir = self._create_mock_mcp_dir(tmp_path)
        catalog = MCPCatalog(root_dir=mcp_dir)
        refs = catalog.list_tool_refs()
        assert len(refs) == 2
        proxy_names = [ref.proxy_name for ref in refs]
        assert "mcp__test_server__search" in proxy_names
        assert "mcp__test_server__calculate" in proxy_names

    def test_get_tool_ref(self, tmp_path: Path):
        mcp_dir = self._create_mock_mcp_dir(tmp_path)
        catalog = MCPCatalog(root_dir=mcp_dir)
        ref = catalog.get_tool_ref("mcp__test_server__search")
        assert ref is not None
        assert ref.tool_name == "search"
        assert ref.server_identifier == "test-server"

    def test_get_tool_ref_not_found(self, tmp_path: Path):
        mcp_dir = self._create_mock_mcp_dir(tmp_path)
        catalog = MCPCatalog(root_dir=mcp_dir)
        ref = catalog.get_tool_ref("nonexistent_tool")
        assert ref is None

    def test_select_tool_refs_by_keyword(self, tmp_path: Path):
        mcp_dir = self._create_mock_mcp_dir(tmp_path)
        catalog = MCPCatalog(root_dir=mcp_dir)
        refs = catalog.select_tool_refs("search information", limit=2)
        assert len(refs) >= 1
        # "search" should match the search tool
        matched_names = [ref.tool_name for ref in refs]
        assert "search" in matched_names

    def test_select_tool_refs_empty_query(self, tmp_path: Path):
        mcp_dir = self._create_mock_mcp_dir(tmp_path)
        catalog = MCPCatalog(root_dir=mcp_dir)
        refs = catalog.select_tool_refs("", limit=4)
        assert refs == []

    def test_build_prompt_block(self, tmp_path: Path):
        mcp_dir = self._create_mock_mcp_dir(tmp_path)
        catalog = MCPCatalog(root_dir=mcp_dir)
        block = catalog.build_prompt_block(query="search", limit=2)
        assert "MCP" in block
        assert "mcp__test_server__search" in block

    def test_scan_real_mcps_dir(self):
        """Test scanning the actual project mcps directory."""
        project_root = Path(__file__).resolve().parents[1]
        mcps_dir = project_root / "mcps"
        if not mcps_dir.exists():
            pytest.skip("mcps directory not found")

        catalog = MCPCatalog(root_dir=mcps_dir)
        servers = catalog.list_servers()
        assert len(servers) >= 1  # at least web-search

        # Check web-search server exists
        ws_servers = [s for s in servers if s.identifier == "web-search"]
        assert len(ws_servers) >= 1
        assert len(ws_servers[0].tools) >= 2  # web_search + news_search