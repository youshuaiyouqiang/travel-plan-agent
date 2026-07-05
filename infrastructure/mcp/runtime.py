from __future__ import annotations


import asyncio
import traceback
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import parse_qs, unquote, urlencode, urlparse

import httpx
from bs4 import BeautifulSoup

from infrastructure.mcp.catalog import MCPCatalog
from infrastructure.tools.base import ToolHandler, ToolSpec, bind_tool

MCPAdapter = Callable[[dict], Awaitable[dict]]
_SEARCH_HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}


def _missing_dependency_message(package: str) -> str:
    return f"missing dependency: {package}. Install it with `pip install {package}` and restart Claw."


def _normalize_max_results(value: Any, default: int = 5) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return min(max(1, parsed), 20)


def _decode_duckduckgo_url(url: str) -> str:
    if not url:
        return ""
    if url.startswith("//"):
        url = f"https:{url}"
    parsed = urlparse(url)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [])
        if target:
            return unquote(target[0])
    return url


def _format_web_results(results: list[dict[str, Any]]) -> str:
    if not results:
        return "No relevant results found."

    output: list[str] = []
    for idx, item in enumerate(results, start=1):
        title = str(item.get("title", "Untitled"))
        url = str(item.get("href", item.get("link", "")))
        body = str(item.get("body", item.get("snippet", "")))
        output.append(f"**{idx}. {title}**\n{url}\n{body}\n")
    return "\n".join(output)


def _format_news_results(results: list[dict[str, Any]]) -> str:
    if not results:
        return "No recent news found."

    output: list[str] = []
    for idx, item in enumerate(results, start=1):
        title = str(item.get("title", "Untitled"))
        url = str(item.get("url", item.get("link", "")))
        body = str(item.get("body", item.get("excerpt", "")))
        source = str(item.get("source", ""))
        date = str(item.get("date", ""))
        header = f"**{idx}. {title}**"
        if source or date:
            header += f" ({source} {date})"
        output.append(f"{header}\n{url}\n{body}\n")
    return "\n".join(output)


def _sync_web_search_ddgs(
    query: str,
    max_results: int,
    region: str,
    safesearch: str,
) -> list[dict[str, Any]]:
    from ddgs import DDGS

    with DDGS() as ddgs:
        return list(
            ddgs.text(
                query,
                max_results=max_results,
                region=region,
                safesearch=safesearch,
            )
        )


def _sync_news_search_ddgs(
    query: str,
    max_results: int,
    region: str,
    safesearch: str,
    timelimit: str | None,
) -> list[dict[str, Any]]:
    from ddgs import DDGS

    with DDGS() as ddgs:
        return list(
            ddgs.news(
                query,
                max_results=max_results,
                region=region,
                safesearch=safesearch,
                timelimit=timelimit,
            )
        )


async def _http_web_search(
    query: str,
    max_results: int,
    region: str,
    safesearch: str,
) -> list[dict[str, Any]]:
    params = {
        "q": query,
        "kl": region,
        "kp": {"on": "1", "moderate": "-1", "off": "-2"}.get(safesearch, "-1"),
    }
    async with httpx.AsyncClient(
        timeout=20.0,
        follow_redirects=True,
        headers=_SEARCH_HEADERS,
    ) as client:
        response = await client.get("https://html.duckduckgo.com/html/", params=params)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    results: list[dict[str, Any]] = []
    for node in soup.select(".result"):
        link = node.select_one("a.result__a")
        if link is None:
            continue
        title = link.get_text(" ", strip=True)
        href = _decode_duckduckgo_url(link.get("href", ""))
        snippet_node = node.select_one(".result__snippet")
        snippet = snippet_node.get_text(" ", strip=True) if snippet_node else ""
        results.append({"title": title, "href": href, "body": snippet})
        if len(results) >= max_results:
            break
    return results


async def _http_news_search(
    query: str,
    max_results: int,
    region: str,
    timelimit: str | None,
) -> list[dict[str, Any]]:
    locale_map = {
        "cn-zh": ("zh-CN", "CN", "CN:zh-Hans"),
        "us-en": ("en-US", "US", "US:en"),
        "wt-wt": ("en-US", "US", "US:en"),
    }
    hl, gl, ceid = locale_map.get(region, ("en-US", "US", "US:en"))
    query_text = query
    if timelimit == "d":
        query_text = f"{query} when:1d"
    elif timelimit == "w":
        query_text = f"{query} when:7d"
    elif timelimit == "m":
        query_text = f"{query} when:30d"

    params = urlencode({"q": query_text, "hl": hl, "gl": gl, "ceid": ceid})
    async with httpx.AsyncClient(
        timeout=20.0,
        follow_redirects=True,
        headers=_SEARCH_HEADERS,
    ) as client:
        response = await client.get(f"https://news.google.com/rss/search?{params}")
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "xml")
    results: list[dict[str, Any]] = []
    for item in soup.find_all("item"):
        title = item.title.get_text(strip=True) if item.title else "Untitled"
        link = item.link.get_text(strip=True) if item.link else ""
        description_html = item.description.get_text(strip=True) if item.description else ""
        description = BeautifulSoup(description_html, "html.parser").get_text(" ", strip=True)
        source = item.source.get_text(strip=True) if item.source else ""
        date = item.pubDate.get_text(strip=True) if item.pubDate else ""
        results.append(
            {
                "title": title,
                "url": link,
                "body": description,
                "source": source,
                "date": date,
            }
        )
        if len(results) >= max_results:
            break
    return results


async def _run_web_search(arguments: dict) -> dict:
    query = str(arguments.get("query", "")).strip()
    if not query:
        return {"is_error": True, "content": "missing query"}

    max_results = _normalize_max_results(arguments.get("max_results", 5))
    region = str(arguments.get("region", "wt-wt")).strip() or "wt-wt"
    safesearch = str(arguments.get("safesearch", "moderate")).strip() or "moderate"

    try:
        try:
            results = await asyncio.to_thread(
                _sync_web_search_ddgs,
                query,
                max_results,
                region,
                safesearch,
            )
            backend = "ddgs"
        except ImportError:
            results = await _http_web_search(query, max_results, region, safesearch)
            backend = "http-fallback"
    except Exception as exc:
        tb = traceback.format_exc()
        return {
            "is_error": True,
            "content": f"web search failed: {type(exc).__name__}: {exc}",
            "backend": "ddgs/http-fallback",
            "traceback": tb[-4000:],
        }

    return {
        "content": _format_web_results(results),
        "backend": backend,
        "query": query,
        "result_count": len(results),
    }


async def _run_news_search(arguments: dict) -> dict:
    query = str(arguments.get("query", "")).strip()
    if not query:
        return {"is_error": True, "content": "missing query"}

    max_results = _normalize_max_results(arguments.get("max_results", 5))
    region = str(arguments.get("region", "wt-wt")).strip() or "wt-wt"
    safesearch = str(arguments.get("safesearch", "moderate")).strip() or "moderate"
    timelimit = str(arguments.get("timelimit", "")).strip() or None

    try:
        try:
            results = await asyncio.to_thread(
                _sync_news_search_ddgs,
                query,
                max_results,
                region,
                safesearch,
                timelimit,
            )
            backend = "ddgs"
        except ImportError:
            results = await _http_news_search(query, max_results, region, timelimit)
            backend = "http-fallback"
    except Exception as exc:
        tb = traceback.format_exc()
        return {
            "is_error": True,
            "content": f"news search failed: {type(exc).__name__}: {exc}",
            "backend": "ddgs/http-fallback",
            "traceback": tb[-4000:],
        }

    return {
        "content": _format_news_results(results),
        "backend": backend,
        "query": query,
        "result_count": len(results),
    }


# ---------------------------------------------------------------------------
# arXiv 搜索适配器
# ---------------------------------------------------------------------------

_ARXIV_API_URL = "https://export.arxiv.org/api/query"
_ARXIV_S2_URL = "https://api.semanticscholar.org/graph/v1/paper"
_ARXIV_HEADERS = {"User-Agent": "claw7-research/1.0 (arxiv-mcp-adapter; github.com/user/claw7)"}
_ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
_S2_FIELDS = (
    "title,year,authors,externalIds,"
    "citations.paperId,citations.title,citations.year,citations.authors,citations.externalIds,"
    "references.paperId,references.title,references.year,references.authors,references.externalIds"
)

# arXiv 3 秒限流
_arxiv_last_request: float = 0.0
_arxiv_lock = asyncio.Lock()


async def _arxiv_rate_limit() -> None:
    global _arxiv_last_request
    async with _arxiv_lock:
        import time

        elapsed = time.monotonic() - _arxiv_last_request
        if elapsed < 3.0:
            await asyncio.sleep(3.0 - elapsed)
        _arxiv_last_request = time.monotonic()


def _parse_arxiv_atom(xml_text: str) -> list[dict]:
    """解析 arXiv Atom XML 为论文列表。"""
    import xml.etree.ElementTree as ET

    results: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return results

    for entry in root.findall("atom:entry", _ARXIV_NS):
        id_elem = entry.find("atom:id", _ARXIV_NS)
        if id_elem is None or id_elem.text is None:
            continue
        paper_id = id_elem.text.split("/abs/")[-1]
        short_id = paper_id.split("v")[0] if "v" in paper_id else paper_id

        title_elem = entry.find("atom:title", _ARXIV_NS)
        title = title_elem.text.strip().replace("\n", " ") if title_elem is not None and title_elem.text else ""

        authors = []
        for author in entry.findall("atom:author", _ARXIV_NS):
            name_elem = author.find("atom:name", _ARXIV_NS)
            if name_elem is not None and name_elem.text:
                authors.append(name_elem.text)

        summary_elem = entry.find("atom:summary", _ARXIV_NS)
        abstract = (
            summary_elem.text.strip().replace("\n", " ") if summary_elem is not None and summary_elem.text else ""
        )

        categories = []
        for cat in entry.findall("arxiv:primary_category", _ARXIV_NS):
            term = cat.get("term")
            if term:
                categories.append(term)
        for cat in entry.findall("atom:category", _ARXIV_NS):
            term = cat.get("term")
            if term and term not in categories:
                categories.append(term)

        published_elem = entry.find("atom:published", _ARXIV_NS)
        published = published_elem.text if published_elem is not None and published_elem.text else ""

        link_elem = entry.find('atom:link[@title="pdf"]', _ARXIV_NS)
        pdf_url = link_elem.get("href") if link_elem is not None else f"http://arxiv.org/pdf/{paper_id}"

        results.append(
            {
                "id": short_id,
                "title": title,
                "authors": authors,
                "abstract": abstract,
                "categories": categories,
                "published": published,
                "url": pdf_url,
            }
        )
    return results


def _format_paper_list(papers: list[dict]) -> str:
    if not papers:
        return "No papers found."
    output: list[str] = []
    for idx, p in enumerate(papers, 1):
        authors_str = ", ".join(p["authors"][:5])
        if len(p["authors"]) > 5:
            authors_str += " et al."
        output.append(
            f"**{idx}. {p['title']}**\n"
            f"📅 {p['published'][:10]}  |  📂 {', '.join(p['categories'][:3])}\n"
            f"👤 {authors_str}\n"
            f"ID: `{p['id']}`\n"
            f"{p['abstract'][:300]}...\n"
        )
    return "\n".join(output)


async def _run_arxiv_search(arguments: dict) -> dict:
    query = str(arguments.get("query", "")).strip()
    if not query:
        return {"is_error": True, "content": "missing query"}

    max_results = str(min(int(arguments.get("max_results", 10)), 50))
    sort_by = str(arguments.get("sort_by", "relevance")).strip() or "relevance"
    date_from = str(arguments.get("date_from", "")).strip()
    date_to = str(arguments.get("date_to", "")).strip()
    categories = arguments.get("categories") or []

    # 构建搜索词
    parts = [f"({query})"]
    if categories:
        cat_filter = " OR ".join(f"cat:{c}" for c in categories)
        parts.append(f"({cat_filter})")
    if date_from or date_to:
        import time as tmod

        start = tmod.strftime("%Y%m%d0000", tmod.strptime(date_from, "%Y-%m-%d")) if date_from else "199107010000"
        end = (
            tmod.strftime("%Y%m%d2359", tmod.strptime(date_to, "%Y-%m-%d")) if date_to else tmod.strftime("%Y%m%d2359")
        )
        parts.append(f"submittedDate:[{start}+TO+{end}]")

    search_query = " AND ".join(parts)
    sort_map = {"relevance": "relevance", "date": "submittedDate"}
    sort_order = "descending"
    url = f"{_ARXIV_API_URL}?search_query={search_query}&max_results={max_results}&sortBy={sort_map.get(sort_by, 'relevance')}&sortOrder={sort_order}"

    try:
        await _arxiv_rate_limit()
        async with httpx.AsyncClient(timeout=30.0, headers=_ARXIV_HEADERS) as client:
            response = await client.get(url)
            response.raise_for_status()
        papers = _parse_arxiv_atom(response.text)
        return {"content": _format_paper_list(papers), "paper_count": len(papers), "papers": papers}
    except Exception as exc:
        return {"is_error": True, "content": f"arxiv search failed: {type(exc).__name__}: {exc}"}


async def _run_arxiv_abstract(arguments: dict) -> dict:
    paper_id = str(arguments.get("paper_id", "")).strip()
    if not paper_id:
        return {"is_error": True, "content": "missing paper_id"}
    if "v" in paper_id:
        paper_id = paper_id.split("v")[0]

    try:
        await _arxiv_rate_limit()
        url = f"{_ARXIV_API_URL}?id_list={paper_id}"
        async with httpx.AsyncClient(timeout=30.0, headers=_ARXIV_HEADERS) as client:
            response = await client.get(url)
            response.raise_for_status()
        papers = _parse_arxiv_atom(response.text)
        if not papers:
            return {"is_error": True, "content": f"paper {paper_id} not found"}
        p = papers[0]
        content = (
            f"**{p['title']}**\n"
            f"ID: `{p['id']}`\n"
            f"📅 {p['published'][:10]}  |  📂 {', '.join(p['categories'])}\n"
            f"👤 {', '.join(p['authors'])}\n\n"
            f"**Abstract:**\n{p['abstract']}\n\n"
            f"🔗 PDF: {p['url']}"
        )
        return {"content": content, "paper": p}
    except Exception as exc:
        return {"is_error": True, "content": f"get abstract failed: {type(exc).__name__}: {exc}"}


async def _run_arxiv_batch(arguments: dict) -> dict:
    paper_ids = arguments.get("paper_ids") or []
    if not paper_ids or not isinstance(paper_ids, list):
        return {"is_error": True, "content": "missing paper_ids (list)"}

    id_list = []
    for pid in paper_ids:
        pid_str = str(pid).strip()
        if "v" in pid_str:
            pid_str = pid_str.split("v")[0]
        if pid_str:
            id_list.append(pid_str)

    if not id_list:
        return {"is_error": True, "content": "no valid paper IDs"}

    try:
        await _arxiv_rate_limit()
        url = f"{_ARXIV_API_URL}?id_list={','.join(id_list[:50])}"
        async with httpx.AsyncClient(timeout=30.0, headers=_ARXIV_HEADERS) as client:
            response = await client.get(url)
            response.raise_for_status()
        papers = _parse_arxiv_atom(response.text)
        return {"content": _format_paper_list(papers), "paper_count": len(papers), "papers": papers}
    except Exception as exc:
        return {"is_error": True, "content": f"batch abstracts failed: {type(exc).__name__}: {exc}"}


async def _run_citation_graph(arguments: dict) -> dict:
    paper_id = str(arguments.get("paper_id", "")).strip()
    if not paper_id:
        return {"is_error": True, "content": "missing paper_id"}
    if "v" in paper_id:
        paper_id = paper_id.split("v")[0]

    try:
        from urllib.parse import quote

        s2_id = quote(f"ARXIV:{paper_id}")
        url = f"{_ARXIV_S2_URL}/{s2_id}?fields={_S2_FIELDS}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()
        data = response.json()

        def normalize(items: list) -> list[dict]:
            result = []
            for item in items or []:
                ext = item.get("externalIds") or {}
                authors = [a.get("name", "") for a in item.get("authors", [])]
                result.append(
                    {
                        "paper_id": item.get("paperId"),
                        "title": item.get("title", ""),
                        "year": item.get("year"),
                        "authors": authors,
                        "arxiv_id": ext.get("ArXiv"),
                    }
                )
            return result

        citations = normalize(data.get("citations", []))
        references = normalize(data.get("references", []))

        lines = [
            f"**{data.get('title', paper_id)}**",
            f"Citations: {len(citations)}  |  References: {len(references)}",
            "",
        ]
        if citations:
            lines.append("**Citing papers:**")
            for i, c in enumerate(citations[:15], 1):
                authors_str = ", ".join(c["authors"][:3])
                arxiv_info = f" (`{c['arxiv_id']}`)" if c["arxiv_id"] else ""
                lines.append(f"{i}. {c['title']} ({c['year'] or 'N/A'}){arxiv_info} — {authors_str}")
            if len(citations) > 15:
                lines.append(f"... and {len(citations) - 15} more")

        if references:
            lines.append("\n**References:**")
            for i, r in enumerate(references[:15], 1):
                authors_str = ", ".join(r["authors"][:3])
                arxiv_info = f" (`{r['arxiv_id']}`)" if r["arxiv_id"] else ""
                lines.append(f"{i}. {r['title']} ({r['year'] or 'N/A'}){arxiv_info} — {authors_str}")
            if len(references) > 15:
                lines.append(f"... and {len(references) - 15} more")

        return {
            "content": "\n".join(lines),
            "citations": citations,
            "references": references,
            "citation_count": len(citations),
            "reference_count": len(references),
        }
    except Exception as exc:
        return {"is_error": True, "content": f"citation graph failed: {type(exc).__name__}: {exc}"}


def build_default_adapters() -> dict[tuple[str, str], MCPAdapter]:
    return {
        ("web-search", "web_search"): _run_web_search,
        ("web-search", "news_search"): _run_news_search,
        ("arxiv", "search_papers"): _run_arxiv_search,
        ("arxiv", "get_abstract"): _run_arxiv_abstract,
        ("arxiv", "batch_abstracts"): _run_arxiv_batch,
        ("arxiv", "citation_graph"): _run_citation_graph,
    }


class MCPProxyRuntime:
    def __init__(
        self,
        *,
        catalog: MCPCatalog,
        adapters: dict[tuple[str, str], MCPAdapter] | None = None,
    ) -> None:
        self._catalog = catalog
        self._adapters = build_default_adapters()
        if adapters:
            self._adapters.update(adapters)

    # ===== P1-16：暴露公共属性，替代外部对 _catalog 的私有访问 =====

    @property
    def catalog(self) -> MCPCatalog:
        """MCP 工具目录（只读视图）。"""
        return self._catalog

    def build_specs(self) -> list[ToolSpec]:
        specs: list[ToolSpec] = []
        for ref in self._catalog.list_tool_refs():
            specs.append(
                ToolSpec(
                    name=ref.proxy_name,
                    description=f"[MCP:{ref.server_identifier}] {ref.description or ref.tool_name}",
                    category="MCP",
                )
            )
        return specs

    def build_handlers(self) -> dict[str, ToolHandler]:
        handlers: dict[str, ToolHandler] = {}
        for ref in self._catalog.list_tool_refs():
            handlers[ref.proxy_name] = self._build_handler(ref.proxy_name)
        return handlers

    def adapter_available(self, proxy_name: str) -> bool:
        ref = self._catalog.get_tool_ref(proxy_name)
        if ref is None:
            return False
        return (ref.server_identifier, ref.tool_name) in self._adapters

    async def call_tool(self, server_identifier: str, tool_name: str, arguments: dict) -> dict:
        adapter = self._adapters.get((server_identifier, tool_name))
        if adapter is None:
            return {
                "is_error": True,
                "content": (
                    f"MCP tool is cataloged but no runtime adapter is configured yet: {server_identifier}.{tool_name}"
                ),
                "adapter_available": False,
            }
        payload = await adapter(arguments)
        payload.setdefault("adapter_available", True)
        return payload

    def _build_handler(self, proxy_name: str) -> ToolHandler:
        async def _handler(arguments: dict) -> dict:
            ref = self._catalog.get_tool_ref(proxy_name)
            if ref is None:
                return {"is_error": True, "content": f"unknown MCP proxy tool: {proxy_name}"}

            payload = await self.call_tool(ref.server_identifier, ref.tool_name, arguments)
            payload.setdefault("mcp_server", ref.server_identifier)
            payload.setdefault("mcp_tool", ref.tool_name)
            payload.setdefault("mcp_proxy", ref.proxy_name)
            return payload

        return _handler


def build_mcp_proxy_tools(catalog: MCPCatalog, runtime: MCPProxyRuntime | None = None) -> list:
    proxy_runtime = runtime or MCPProxyRuntime(catalog=catalog)
    specs = {spec.name: spec for spec in proxy_runtime.build_specs()}
    return [bind_tool(specs[name], handler) for name, handler in proxy_runtime.build_handlers().items()]
