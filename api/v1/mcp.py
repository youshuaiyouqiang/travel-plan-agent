from __future__ import annotations

from fastapi import APIRouter, Request

from application.exceptions import NotFoundException, UnauthorizedException

router = APIRouter(tags=["mcp"])


def _build_tool_dict(tool, runtime) -> dict:
    """构建工具信息字典。"""
    proxy_name = tool.proxy_name
    return {
        "name": tool.name,
        "description": tool.description,
        "proxy_name": proxy_name,
        "input_schema": tool.input_schema,
        "adapter_available": runtime.adapter_available(proxy_name) if runtime else False,
    }


def _build_server_dict(server, runtime) -> dict:
    """构建服务器信息字典。"""
    return {
        "identifier": server.identifier,
        "name": server.name,
        "description": server.description,
        "instructions": server.instructions,
        "tools": [_build_tool_dict(t, runtime) for t in server.tools],
    }


def _find_server(catalog, server_id: str):
    """从 catalog 中查找指定 server_id 的服务器。"""
    for server in catalog.list_servers():
        if server.identifier == server_id:
            return server
    return None


@router.get("")
async def list_mcp_servers(request: Request) -> dict:
    """列出所有 MCP server（含 tools 和 adapter_available 状态）。"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()
    catalog = request.app.state.mcp_catalog
    runtime = request.app.state.mcp_runtime
    servers = [_build_server_dict(s, runtime) for s in catalog.list_servers()]
    return {"servers": servers}


@router.get("/{server_id}")
async def get_mcp_server_detail(server_id: str, request: Request) -> dict:
    """获取单个 MCP server 详情。"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()
    catalog = request.app.state.mcp_catalog
    runtime = request.app.state.mcp_runtime
    server = _find_server(catalog, server_id)
    if not server:
        raise NotFoundException("MCP Server", server_id)
    return _build_server_dict(server, runtime)


@router.get("/{server_id}/tools")
async def get_mcp_server_tools(server_id: str, request: Request) -> dict:
    """获取某 MCP server 的工具列表。"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()
    catalog = request.app.state.mcp_catalog
    runtime = request.app.state.mcp_runtime
    server = _find_server(catalog, server_id)
    if not server:
        raise NotFoundException("MCP Server", server_id)
    return {"server_id": server_id, "tools": [_build_tool_dict(t, runtime) for t in server.tools]}
