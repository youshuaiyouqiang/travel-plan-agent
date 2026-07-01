from __future__ import annotations


import asyncio
import traceback
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import parse_qs, unquote, urlencode, urlparse

import httpx
from bs4 import BeautifulSoup

from core.mcp_catalog import MCPCatalog
from tools.base import ToolHandler, ToolSpec, bind_tool

MCPAdapter = Callable[[dict], Awaitable[dict]]
_SEARCH_HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}


def _missing_dependency_message(package: str) -> str:
    return (
        f"missing dependency: {package}. "
        f"Install it with `pip install {package}` and restart Claw."
    )


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


def build_default_adapters() -> dict[tuple[str, str], MCPAdapter]:
    return {
        ("web-search", "web_search"): _run_web_search,
        ("web-search", "news_search"): _run_news_search,
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
                    "MCP tool is cataloged but no runtime adapter is configured yet: "
                    f"{server_identifier}.{tool_name}"
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
    return [
        bind_tool(specs[name], handler)
        for name, handler in proxy_runtime.build_handlers().items()
    ]
