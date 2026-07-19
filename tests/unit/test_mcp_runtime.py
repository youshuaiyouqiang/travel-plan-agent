"""MCP runtime 单元测试 — 工具函数 + 部分 adapter 行为。

通过 monkeypatch ``httpx.AsyncClient`` / ``asyncio.to_thread`` 避免真实网络请求。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from infrastructure.mcp import runtime


# ---------------------------------------------------------------------------
# 纯函数
# ---------------------------------------------------------------------------


class TestNormalizeMaxResults:
    def test_default(self):
        assert runtime._normalize_max_results(None) == 5
        assert runtime._normalize_max_results(0) == 1  # 0 被钳制为 1

    def test_string_input(self):
        assert runtime._normalize_max_results("10") == 10

    def test_invalid_string(self):
        assert runtime._normalize_max_results("abc") == 5

    def test_clamped_to_max(self):
        assert runtime._normalize_max_results(100) == 20

    def test_clamped_to_min(self):
        assert runtime._normalize_max_results(-5) == 1


class TestDecodeDuckduckgoUrl:
    def test_empty(self):
        assert runtime._decode_duckduckgo_url("") == ""

    def test_protocol_relative(self):
        assert runtime._decode_duckduckgo_url("//example.com/x").startswith("https://example.com/x")

    def test_duckduckgo_redirect(self):
        url = "https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage"
        assert runtime._decode_duckduckgo_url(url) == "https://example.com/page"

    def test_non_duckduckgo_passthrough(self):
        assert runtime._decode_duckduckgo_url("https://example.com/x") == "https://example.com/x"


class TestFormatWebResults:
    def test_empty(self):
        assert runtime._format_web_results([]) == "No relevant results found."

    def test_basic_formatting(self):
        results = [
            {"title": "T1", "href": "http://x", "body": "B1"},
            {"title": "T2", "link": "http://y", "snippet": "B2"},
        ]
        out = runtime._format_web_results(results)
        assert "1. T1" in out
        assert "2. T2" in out
        assert "B1" in out and "B2" in out


class TestFormatNewsResults:
    def test_empty(self):
        assert runtime._format_news_results([]) == "No recent news found."

    def test_basic_formatting(self):
        results = [
            {"title": "News1", "url": "http://n1", "body": "Body1", "source": "src", "date": "2026-01-01"},
        ]
        out = runtime._format_news_results(results)
        assert "News1" in out
        assert "src" in out
        assert "2026-01-01" in out


# ---------------------------------------------------------------------------
# _parse_arxiv_atom
# ---------------------------------------------------------------------------


_ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2401.00001v2</id>
    <title>Sample Paper Title</title>
    <author><name>Alice</name></author>
    <author><name>Bob</name></author>
    <summary>This is the abstract.</summary>
    <arxiv:primary_category term="cs.AI"/>
    <category term="cs.CL"/>
    <published>2024-01-15T00:00:00Z</published>
    <link title="pdf" href="http://arxiv.org/pdf/2401.00001v2"/>
  </entry>
</feed>
"""


class TestParseArxivAtom:
    def test_parses_entry(self):
        papers = runtime._parse_arxiv_atom(_ARXIV_XML)
        assert len(papers) == 1
        p = papers[0]
        assert p["id"] == "2401.00001"  # 版本号 v2 已剥离
        assert p["title"] == "Sample Paper Title"
        assert p["authors"] == ["Alice", "Bob"]
        assert p["abstract"] == "This is the abstract."
        assert "cs.AI" in p["categories"]
        assert "cs.CL" in p["categories"]
        assert p["published"].startswith("2024-01-15")
        assert p["url"].endswith("2401.00001v2")

    def test_invalid_xml_returns_empty(self):
        assert runtime._parse_arxiv_atom("not xml") == []

    def test_empty_feed(self):
        xml = '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'
        assert runtime._parse_arxiv_atom(xml) == []


class TestFormatPaperList:
    def test_empty(self):
        assert runtime._format_paper_list([]) == "No papers found."

    def test_short_author_list(self):
        papers = [
            {
                "id": "2401.00001",
                "title": "Paper",
                "authors": ["Alice"],
                "abstract": "Abstract",
                "categories": ["cs.AI"],
                "published": "2024-01-15T00:00:00Z",
                "url": "http://x",
            }
        ]
        out = runtime._format_paper_list(papers)
        assert "1. Paper" in out
        assert "Alice" in out
        assert "2024-01-15" in out

    def test_long_author_list_truncated(self):
        authors = [f"Author{i}" for i in range(10)]
        papers = [
            {
                "id": "x",
                "title": "T",
                "authors": authors,
                "abstract": "A",
                "categories": [],
                "published": "2024-01-01",
                "url": "http://x",
            }
        ]
        out = runtime._format_paper_list(papers)
        assert "et al." in out


# ---------------------------------------------------------------------------
# _run_arxiv_search / _run_arxiv_abstract / _run_arxiv_batch / _run_citation_graph
# ---------------------------------------------------------------------------


class _FakeAsyncClient:
    def __init__(self, *, response_text: str = "", json_data: Any = None, exc: Exception | None = None):
        self._response_text = response_text
        self._json_data = json_data
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, **kwargs):
        if self._exc:
            raise self._exc
        response = MagicMock()
        response.text = self._response_text
        response.json = lambda: self._json_data
        response.raise_for_status = lambda: None
        return response


class TestArxivAdapters:
    @pytest.mark.asyncio
    async def test_run_arxiv_search_missing_query(self):
        result = await runtime._run_arxiv_search({})
        assert result["is_error"] is True
        assert "missing query" in result["content"]

    @pytest.mark.asyncio
    async def test_run_arxiv_search_success(self, monkeypatch):
        monkeypatch.setattr(
            runtime.httpx,
            "AsyncClient",
            lambda *a, **k: _FakeAsyncClient(response_text=_ARXIV_XML),
        )
        monkeypatch.setattr(runtime, "_arxiv_rate_limit", AsyncMock())
        result = await runtime._run_arxiv_search({"query": "transformer", "max_results": 5})
        assert "content" in result
        assert result["paper_count"] == 1

    @pytest.mark.asyncio
    async def test_run_arxiv_search_exception(self, monkeypatch):
        monkeypatch.setattr(
            runtime.httpx,
            "AsyncClient",
            lambda *a, **k: _FakeAsyncClient(exc=RuntimeError("network down")),
        )
        monkeypatch.setattr(runtime, "_arxiv_rate_limit", AsyncMock())
        result = await runtime._run_arxiv_search({"query": "x"})
        assert result["is_error"] is True
        assert "arxiv search failed" in result["content"]

    @pytest.mark.asyncio
    async def test_run_arxiv_abstract_missing_id(self):
        result = await runtime._run_arxiv_abstract({})
        assert result["is_error"] is True
        assert "missing paper_id" in result["content"]

    @pytest.mark.asyncio
    async def test_run_arxiv_abstract_strips_version(self, monkeypatch):
        monkeypatch.setattr(
            runtime.httpx,
            "AsyncClient",
            lambda *a, **k: _FakeAsyncClient(response_text=_ARXIV_XML),
        )
        monkeypatch.setattr(runtime, "_arxiv_rate_limit", AsyncMock())
        result = await runtime._run_arxiv_abstract({"paper_id": "2401.00001v2"})
        assert "content" in result
        assert "Sample Paper Title" in result["content"]

    @pytest.mark.asyncio
    async def test_run_arxiv_abstract_not_found(self, monkeypatch):
        empty_xml = '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'
        monkeypatch.setattr(
            runtime.httpx,
            "AsyncClient",
            lambda *a, **k: _FakeAsyncClient(response_text=empty_xml),
        )
        monkeypatch.setattr(runtime, "_arxiv_rate_limit", AsyncMock())
        result = await runtime._run_arxiv_abstract({"paper_id": "9999.99999"})
        assert result["is_error"] is True
        assert "not found" in result["content"]

    @pytest.mark.asyncio
    async def test_run_arxiv_batch_missing_ids(self):
        result = await runtime._run_arxiv_batch({})
        assert result["is_error"] is True
        assert "missing paper_ids" in result["content"]

    @pytest.mark.asyncio
    async def test_run_arxiv_batch_empty_list(self):
        result = await runtime._run_arxiv_batch({"paper_ids": []})
        assert result["is_error"] is True
        assert "missing paper_ids" in result["content"]

    @pytest.mark.asyncio
    async def test_run_arxiv_batch_invalid_ids(self):
        result = await runtime._run_arxiv_batch({"paper_ids": ["", "  "]})
        assert result["is_error"] is True
        assert "no valid paper IDs" in result["content"]

    @pytest.mark.asyncio
    async def test_run_arxiv_batch_success(self, monkeypatch):
        monkeypatch.setattr(
            runtime.httpx,
            "AsyncClient",
            lambda *a, **k: _FakeAsyncClient(response_text=_ARXIV_XML),
        )
        monkeypatch.setattr(runtime, "_arxiv_rate_limit", AsyncMock())
        result = await runtime._run_arxiv_batch({"paper_ids": ["2401.00001"]})
        assert result["paper_count"] == 1

    @pytest.mark.asyncio
    async def test_run_citation_graph_missing_id(self):
        result = await runtime._run_citation_graph({})
        assert result["is_error"] is True
        assert "missing paper_id" in result["content"]

    @pytest.mark.asyncio
    async def test_run_citation_graph_success(self, monkeypatch):
        json_data = {
            "title": "Cited Paper",
            "citations": [
                {
                    "paperId": "p1",
                    "title": "Citing 1",
                    "year": 2024,
                    "authors": [{"name": "Alice"}],
                    "externalIds": {"ArXiv": "2402.00001"},
                }
            ],
            "references": [
                {
                    "paperId": "p2",
                    "title": "Reference 1",
                    "year": 2023,
                    "authors": [{"name": "Bob"}],
                    "externalIds": {},
                }
            ],
        }
        monkeypatch.setattr(
            runtime.httpx,
            "AsyncClient",
            lambda *a, **k: _FakeAsyncClient(json_data=json_data),
        )
        result = await runtime._run_citation_graph({"paper_id": "2401.00001v2"})
        assert result["citation_count"] == 1
        assert result["reference_count"] == 1
        assert "Citing 1" in result["content"]
        assert "Reference 1" in result["content"]

    @pytest.mark.asyncio
    async def test_run_citation_graph_exception(self, monkeypatch):
        monkeypatch.setattr(
            runtime.httpx,
            "AsyncClient",
            lambda *a, **k: _FakeAsyncClient(exc=RuntimeError("boom")),
        )
        result = await runtime._run_citation_graph({"paper_id": "2401.00001"})
        assert result["is_error"] is True
        assert "citation graph failed" in result["content"]


# ---------------------------------------------------------------------------
# _run_web_search / _run_news_search
# ---------------------------------------------------------------------------


class TestWebNewsSearch:
    @pytest.mark.asyncio
    async def test_web_search_missing_query(self):
        result = await runtime._run_web_search({})
        assert result["is_error"] is True
        assert "missing query" in result["content"]

    @pytest.mark.asyncio
    async def test_news_search_missing_query(self):
        result = await runtime._run_news_search({})
        assert result["is_error"] is True
        assert "missing query" in result["content"]

    @pytest.mark.asyncio
    async def test_web_search_ddgs_success(self, monkeypatch):
        async def fake_to_thread(func, *args, **kwargs):
            return [{"title": "T", "href": "http://x", "body": "B"}]

        monkeypatch.setattr(runtime.asyncio, "to_thread", fake_to_thread)
        result = await runtime._run_web_search({"query": "test"})
        assert result["backend"] == "ddgs"
        assert result["result_count"] == 1
        assert "T" in result["content"]

    @pytest.mark.asyncio
    async def test_web_search_http_fallback(self, monkeypatch):
        # ddgs 抛 ImportError → 走 http fallback
        async def fake_to_thread(func, *args, **kwargs):
            raise ImportError("no ddgs")

        monkeypatch.setattr(runtime.asyncio, "to_thread", fake_to_thread)

        # 模拟 httpx 返回 HTML
        html = '<html><div class="result"><a class="result__a" href="//example.com/x">Title</a><div class="result__snippet">Snippet</div></div></html>'

        monkeypatch.setattr(
            runtime.httpx,
            "AsyncClient",
            lambda *a, **k: _FakeAsyncClient(response_text=html),
        )
        result = await runtime._run_web_search({"query": "test"})
        assert result["backend"] == "http-fallback"
        assert result["result_count"] == 1

    @pytest.mark.asyncio
    async def test_web_search_failure(self, monkeypatch):
        async def fake_to_thread(func, *args, **kwargs):
            raise RuntimeError("ddgs failed")

        monkeypatch.setattr(
            runtime.httpx,
            "AsyncClient",
            lambda *a, **k: _FakeAsyncClient(exc=RuntimeError("http also failed")),
        )
        monkeypatch.setattr(runtime.asyncio, "to_thread", fake_to_thread)
        result = await runtime._run_web_search({"query": "test"})
        assert result["is_error"] is True
        assert "web search failed" in result["content"]


# ---------------------------------------------------------------------------
# MCPProxyRuntime
# ---------------------------------------------------------------------------


class TestMCPProxyRuntime:
    def test_build_default_adapters_keys(self):
        adapters = runtime.build_default_adapters()
        assert ("web-search", "web_search") in adapters
        assert ("arxiv", "search_papers") in adapters

    def test_runtime_constructor_merges_adapters(self):
        catalog = MagicMock()
        custom_adapter = AsyncMock()
        custom = {("custom", "tool"): custom_adapter}
        rt = runtime.MCPProxyRuntime(catalog=catalog, adapters=custom)
        assert ("custom", "tool") in rt._adapters
        # 默认 adapters 也保留
        assert ("web-search", "web_search") in rt._adapters

    @pytest.mark.asyncio
    async def test_call_tool_no_adapter(self):
        catalog = MagicMock()
        rt = runtime.MCPProxyRuntime(catalog=catalog)
        result = await rt.call_tool("unknown-server", "unknown-tool", {})
        assert result["is_error"] is True
        assert result["adapter_available"] is False

    @pytest.mark.asyncio
    async def test_call_tool_with_adapter(self):
        catalog = MagicMock()

        async def fake_adapter(args):
            return {"content": "ok"}

        rt = runtime.MCPProxyRuntime(catalog=catalog, adapters={("s", "t"): fake_adapter})
        result = await rt.call_tool("s", "t", {"x": 1})
        assert result["content"] == "ok"
        assert result["adapter_available"] is True

    def test_adapter_available_no_ref(self):
        catalog = MagicMock()
        catalog.get_tool_ref.return_value = None
        rt = runtime.MCPProxyRuntime(catalog=catalog)
        assert rt.adapter_available("nonexistent") is False

    def test_adapter_available_present(self):
        ref = MagicMock()
        ref.server_identifier = "s"
        ref.tool_name = "t"
        catalog = MagicMock()
        catalog.get_tool_ref.return_value = ref
        rt = runtime.MCPProxyRuntime(catalog=catalog, adapters={("s", "t"): AsyncMock()})
        assert rt.adapter_available("proxy-name") is True
