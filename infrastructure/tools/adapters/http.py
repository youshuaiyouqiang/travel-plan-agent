from __future__ import annotations
import httpx
from config import settings
from tools.base import ToolHandler, ToolSpec, bind_tool

async def _fetch_url(arguments: dict) -> dict:
    if not settings.allow_http:
        return {"is_error": True, "content": "http disabled"}
    url = str(arguments.get("url", "")).strip()
    if not url.startswith(("http://", "https://")):
        return {"is_error": True, "content": "invalid url"}
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        return {"is_error": True, "content": f"http request failed: {type(exc).__name__}: {exc}"}

    body = response.text[:8000]
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = response.json()
            body = httpx.Response(
                status_code=response.status_code,
                json=body,
            ).text[:8000]
        except Exception:
            body = response.text[:8000]
    return {
        "is_error": response.status_code >= 400,
        "content": body,
        "status_code": response.status_code,
        "url": str(response.url),
    }

def get_http_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="fetch_url",
            description="通过 HTTP 获取网页.",
            category="Web",
        )
    ]
def get_http_handlers() -> dict[str, ToolHandler]:
    return {"fetch_url": _fetch_url}


def build_http_tools() -> list:
    specs = {spec.name: spec for spec in get_http_specs()}
    return [bind_tool(specs[name], handler) for name, handler in get_http_handlers().items()]
