"""
Code Mode Router: Internal MCP Proxy for Code Interpreter

This router provides an internal endpoint that the code interpreter can call
to execute MCP tools. It acts as a proxy between the sandboxed code execution
environment and the MCP servers.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from open_webui.utils.auth import get_current_user
from open_webui.models.users import UserModel

log = logging.getLogger(__name__)

router = APIRouter()


class MCPToolCallRequest(BaseModel):
    """Request body for MCP tool calls from code interpreter."""

    tool_name: str
    arguments: dict
    session_id: str


class MCPToolCallResponse(BaseModel):
    """Response body for MCP tool calls."""

    result: Any = None
    error: Optional[str] = None


# In-memory store for active MCP sessions
# Maps session_id -> {"user_id": str, "mcp_clients": dict, "tools": dict}
_active_sessions: dict[str, dict] = {}

# Per-user store for MCP bindings code, so the direct /code/execute endpoint
# can also inject bindings (not just the middleware path).
# Maps user_id -> {"bindings": str, "session_id": str}
_user_bindings: dict[str, dict] = {}


def register_code_mode_session(
    session_id: str,
    user_id: str,
    mcp_clients: dict,
    mcp_tools: dict,
):
    """
    Register an active code mode session with its MCP clients and tools.

    This is called from the middleware when setting up code interpreter
    with MCP tools enabled.
    """
    _active_sessions[session_id] = {
        "user_id": user_id,
        "mcp_clients": mcp_clients,
        "tools": mcp_tools,
    }
    log.debug(f"Registered code mode session: {session_id} with {len(mcp_tools)} tools")


def unregister_code_mode_session(session_id: str):
    """Remove a code mode session when it's no longer needed."""
    if session_id in _active_sessions:
        del _active_sessions[session_id]
        log.debug(f"Unregistered code mode session: {session_id}")


def get_code_mode_session(session_id: str) -> Optional[dict]:
    """Get an active code mode session by ID."""
    return _active_sessions.get(session_id)


def store_user_bindings(user_id: str, bindings: str, session_id: str):
    """Store MCP bindings for a user so the direct code/execute endpoint can use them."""
    _user_bindings[user_id] = {"bindings": bindings, "session_id": session_id}


def get_user_bindings(user_id: str) -> str:
    """Get stored MCP bindings code for a user. Returns empty string if none."""
    entry = _user_bindings.get(user_id)
    if not entry:
        return ""
    # Only return bindings if the session is still active
    session_id = entry.get("session_id", "")
    if session_id and session_id not in _active_sessions:
        return ""
    return entry.get("bindings", "")


@router.post("/call", response_model=MCPToolCallResponse)
async def call_mcp_tool(
    request: Request,
    body: MCPToolCallRequest,
):
    """
    Execute an MCP tool call from the code interpreter.

    This endpoint is called by code running in the Jupyter sandbox.
    It validates the session and proxies the call to the appropriate MCP client.
    """
    session_id = body.session_id
    tool_name = body.tool_name
    arguments = body.arguments

    # Get the session
    session = get_code_mode_session(session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Code mode session not found: {session_id}",
        )

    # Get the tool
    tools = session.get("tools", {})
    if tool_name not in tools:
        raise HTTPException(
            status_code=404,
            detail=f"Tool not found: {tool_name}. Available tools: {list(tools.keys())}",
        )

    tool_data = tools[tool_name]
    tool_callable = tool_data.get("callable")

    if not tool_callable:
        raise HTTPException(
            status_code=500,
            detail=f"Tool {tool_name} has no callable function",
        )

    try:
        # Call the MCP tool
        log.debug(f"Calling MCP tool: {tool_name} with args: {arguments}")
        result = await tool_callable(**arguments)

        log.debug(f"MCP tool result: {result}")
        return MCPToolCallResponse(result=result)

    except Exception as e:
        log.error(f"MCP tool call failed: {e}")
        return MCPToolCallResponse(error=str(e))


@router.get("/session/{session_id}/tools")
async def list_session_tools(session_id: str):
    """
    List available tools for a code mode session.

    This can be used for debugging or by the code interpreter to discover tools.
    """
    session = get_code_mode_session(session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Code mode session not found: {session_id}",
        )

    tools = session.get("tools", {})
    tool_list = []

    for tool_id, tool_data in tools.items():
        if tool_data.get("type") == "mcp":
            spec = tool_data.get("spec", {})
            tool_list.append({
                "name": spec.get("name", tool_id),
                "description": spec.get("description", ""),
                "parameters": spec.get("parameters", {}),
            })

    return {"tools": tool_list}
