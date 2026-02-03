import asyncio
import logging
from typing import Optional
from contextlib import AsyncExitStack

import anyio

from mcp import ClientSession
from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

log = logging.getLogger(__name__)


class MCPClient:
    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.exit_stack: Optional[AsyncExitStack] = None
        self._url: Optional[str] = None
        self._headers: Optional[dict] = None

    async def connect(self, url: str, headers: Optional[dict] = None):
        self._url = url
        self._headers = headers
        async with AsyncExitStack() as exit_stack:
            try:
                self._streams_context = streamablehttp_client(url, headers=headers)

                transport = await exit_stack.enter_async_context(self._streams_context)
                read_stream, write_stream, _ = transport

                self._session_context = ClientSession(
                    read_stream, write_stream
                )  # pylint: disable=W0201

                self.session = await exit_stack.enter_async_context(
                    self._session_context
                )
                with anyio.fail_after(10):
                    await self.session.initialize()
                self.exit_stack = exit_stack.pop_all()
            except Exception as e:
                # Only attempt disconnect if exit_stack was successfully assigned
                if self.exit_stack is not None:
                    await asyncio.shield(self.disconnect())
                raise e

    async def _ensure_connected(self):
        """Reconnect if the session has been lost."""
        if not self.session and self._url:
            log.debug(f"MCP client reconnecting to {self._url}")
            await self.connect(self._url, self._headers)

    async def list_tool_specs(self) -> Optional[dict]:
        await self._ensure_connected()
        if not self.session:
            raise RuntimeError("MCP client is not connected.")

        result = await self.session.list_tools()
        tools = result.tools

        tool_specs = []
        for tool in tools:
            name = tool.name
            description = tool.description

            inputSchema = tool.inputSchema

            # TODO: handle outputSchema if needed
            outputSchema = getattr(tool, "outputSchema", None)

            tool_specs.append(
                {"name": name, "description": description, "parameters": inputSchema}
            )

        return tool_specs

    async def call_tool(
        self, function_name: str, function_args: dict
    ) -> Optional[dict]:
        await self._ensure_connected()
        if not self.session:
            raise RuntimeError("MCP client is not connected.")

        result = await self.session.call_tool(function_name, function_args)
        if not result:
            raise Exception("No result returned from MCP tool call.")

        result_dict = result.model_dump(mode="json")
        result_content = result_dict.get("content", {})

        if result.isError:
            # Extract text from content items if available
            error_msg = result_content
            if isinstance(result_content, list):
                text_items = [
                    item.get("text", "")
                    for item in result_content
                    if isinstance(item, dict) and item.get("type") == "text"
                ]
                if text_items:
                    error_msg = "; ".join(text_items)
            raise Exception(f"MCP tool error: {error_msg}")
        else:
            return result_content

    async def list_resources(self, cursor: Optional[str] = None) -> Optional[dict]:
        await self._ensure_connected()
        if not self.session:
            raise RuntimeError("MCP client is not connected.")

        result = await self.session.list_resources(cursor=cursor)
        if not result:
            raise Exception("No result returned from MCP list_resources call.")

        result_dict = result.model_dump()
        resources = result_dict.get("resources", [])

        return resources

    async def read_resource(self, uri: str) -> Optional[dict]:
        await self._ensure_connected()
        if not self.session:
            raise RuntimeError("MCP client is not connected.")

        result = await self.session.read_resource(uri)
        if not result:
            raise Exception("No result returned from MCP read_resource call.")
        result_dict = result.model_dump()

        return result_dict

    async def disconnect(self):
        """Clean up and close the session."""
        if self.exit_stack is not None:
            try:
                await self.exit_stack.aclose()
            except Exception as e:
                log.debug(f"Error during MCP client disconnect: {e}")
            finally:
                self.exit_stack = None
                self.session = None

    async def __aenter__(self):
        """Async context manager entry - note: connect() must be called separately."""
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        """Async context manager exit - ensures cleanup on exit."""
        await self.disconnect()
