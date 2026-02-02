"""
Integration tests for the code mode router.

Tests the MCP proxy endpoint used by the code interpreter.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from open_webui.routers.code_mode import (
    register_code_mode_session,
    unregister_code_mode_session,
    get_code_mode_session,
    _active_sessions,
)


class TestCodeModeSessionManagement:
    """Tests for code mode session registration and management."""

    def setup_method(self):
        """Clear sessions before each test."""
        _active_sessions.clear()

    def test_register_session(self):
        """Test registering a new code mode session."""
        mock_client = MagicMock()
        mock_tools = {
            "tool1": {
                "type": "mcp",
                "spec": {"name": "tool1"},
                "callable": AsyncMock(),
            }
        }

        register_code_mode_session(
            session_id="test-session-123",
            user_id="user-1",
            mcp_clients={"server1": mock_client},
            mcp_tools=mock_tools,
        )

        session = get_code_mode_session("test-session-123")
        assert session is not None
        assert session["user_id"] == "user-1"
        assert "server1" in session["mcp_clients"]
        assert "tool1" in session["tools"]

    def test_unregister_session(self):
        """Test unregistering a code mode session."""
        register_code_mode_session(
            session_id="test-session",
            user_id="user-1",
            mcp_clients={},
            mcp_tools={},
        )

        assert get_code_mode_session("test-session") is not None

        unregister_code_mode_session("test-session")

        assert get_code_mode_session("test-session") is None

    def test_get_nonexistent_session(self):
        """Test getting a session that doesn't exist."""
        assert get_code_mode_session("nonexistent") is None


class TestCodeModeRouter:
    """Integration tests for the code mode router endpoints."""

    @pytest.fixture
    def client(self):
        """Create a test client for the router."""
        from open_webui.main import app
        return TestClient(app)

    def setup_method(self):
        """Clear sessions before each test."""
        _active_sessions.clear()

    def test_call_tool_session_not_found(self, client):
        """Test calling a tool with invalid session."""
        response = client.post(
            "/api/v1/code-mode/call",
            json={
                "tool_name": "some_tool",
                "arguments": {},
                "session_id": "invalid-session",
            },
        )

        assert response.status_code == 404
        assert "session not found" in response.json()["detail"].lower()

    def test_call_tool_not_found(self, client):
        """Test calling a tool that doesn't exist in session."""
        register_code_mode_session(
            session_id="valid-session",
            user_id="user-1",
            mcp_clients={},
            mcp_tools={},
        )

        response = client.post(
            "/api/v1/code-mode/call",
            json={
                "tool_name": "nonexistent_tool",
                "arguments": {},
                "session_id": "valid-session",
            },
        )

        assert response.status_code == 404
        assert "tool not found" in response.json()["detail"].lower()

    def test_call_tool_success(self, client):
        """Test successfully calling an MCP tool."""
        # Create a mock async callable
        async def mock_tool_callable(**kwargs):
            return {"result": "success", "args": kwargs}

        register_code_mode_session(
            session_id="test-session",
            user_id="user-1",
            mcp_clients={},
            mcp_tools={
                "server_test_tool": {
                    "type": "mcp",
                    "spec": {"name": "server_test_tool"},
                    "callable": mock_tool_callable,
                }
            },
        )

        response = client.post(
            "/api/v1/code-mode/call",
            json={
                "tool_name": "server_test_tool",
                "arguments": {"param1": "value1"},
                "session_id": "test-session",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["result"]["result"] == "success"
        assert data["result"]["args"]["param1"] == "value1"
        assert data["error"] is None

    def test_call_tool_error_handling(self, client):
        """Test that tool errors are properly returned."""
        async def failing_tool(**kwargs):
            raise Exception("Tool execution failed")

        register_code_mode_session(
            session_id="error-session",
            user_id="user-1",
            mcp_clients={},
            mcp_tools={
                "failing_tool": {
                    "type": "mcp",
                    "spec": {"name": "failing_tool"},
                    "callable": failing_tool,
                }
            },
        )

        response = client.post(
            "/api/v1/code-mode/call",
            json={
                "tool_name": "failing_tool",
                "arguments": {},
                "session_id": "error-session",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["error"] is not None
        assert "Tool execution failed" in data["error"]

    def test_list_session_tools(self, client):
        """Test listing tools for a session."""
        register_code_mode_session(
            session_id="list-session",
            user_id="user-1",
            mcp_clients={},
            mcp_tools={
                "tool1": {
                    "type": "mcp",
                    "spec": {
                        "name": "tool1",
                        "description": "First tool",
                        "parameters": {"properties": {}},
                    },
                    "callable": AsyncMock(),
                },
                "tool2": {
                    "type": "mcp",
                    "spec": {
                        "name": "tool2",
                        "description": "Second tool",
                        "parameters": {"properties": {}},
                    },
                    "callable": AsyncMock(),
                },
            },
        )

        response = client.get("/api/v1/code-mode/session/list-session/tools")

        assert response.status_code == 200
        data = response.json()
        assert len(data["tools"]) == 2

        tool_names = [t["name"] for t in data["tools"]]
        assert "tool1" in tool_names
        assert "tool2" in tool_names

    def test_list_session_tools_not_found(self, client):
        """Test listing tools for a nonexistent session."""
        response = client.get("/api/v1/code-mode/session/invalid/tools")

        assert response.status_code == 404
        assert "session not found" in response.json()["detail"].lower()
