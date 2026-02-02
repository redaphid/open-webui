"""
Unit tests for the code mode module.

Tests the MCP bindings generator and code mode prompt generation,
including execution-level tests that verify generated bindings
actually work correctly against mock MCP responses.
"""

import io
import json

import pytest
from open_webui.utils.code_mode import (
    json_schema_to_python_type,
    generate_function_signature,
    generate_mcp_bindings,
    generate_code_mode_prompt,
)


class TestJsonSchemaToPythonType:
    """Tests for JSON schema to Python type conversion."""

    def test_string_type(self):
        assert json_schema_to_python_type({"type": "string"}) == "str"

    def test_integer_type(self):
        assert json_schema_to_python_type({"type": "integer"}) == "int"

    def test_number_type(self):
        assert json_schema_to_python_type({"type": "number"}) == "float"

    def test_boolean_type(self):
        assert json_schema_to_python_type({"type": "boolean"}) == "bool"

    def test_array_type(self):
        schema = {"type": "array", "items": {"type": "string"}}
        assert json_schema_to_python_type(schema) == "list[str]"

    def test_object_type(self):
        assert json_schema_to_python_type({"type": "object"}) == "dict"

    def test_null_type(self):
        assert json_schema_to_python_type({"type": "null"}) == "None"

    def test_unknown_type(self):
        assert json_schema_to_python_type({"type": "unknown"}) == "Any"

    def test_empty_schema(self):
        assert json_schema_to_python_type({}) == "Any"

    def test_none_schema(self):
        assert json_schema_to_python_type(None) == "Any"


class TestGenerateFunctionSignature:
    """Tests for function signature generation from tool specs."""

    def test_simple_tool_spec(self):
        tool_spec = {
            "name": "get_weather",
            "description": "Get weather for a location",
            "parameters": {
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city name",
                    }
                },
                "required": ["location"],
            },
        }

        signature, docstring = generate_function_signature(tool_spec)
        assert "location: str" in signature
        assert "Get weather for a location" in docstring
        assert "location: The city name" in docstring

    def test_optional_parameters(self):
        tool_spec = {
            "name": "search",
            "description": "Search for items",
            "parameters": {
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["query"],
            },
        }

        signature, docstring = generate_function_signature(tool_spec)
        assert "query: str" in signature
        assert "limit: int = 0" in signature

    def test_no_parameters(self):
        tool_spec = {
            "name": "list_items",
            "description": "List all items",
            "parameters": {},
        }

        signature, docstring = generate_function_signature(tool_spec)
        assert signature == ""
        assert "List all items" in docstring


class TestGenerateMcpBindings:
    """Tests for MCP bindings code generation."""

    def test_empty_tools(self):
        result = generate_mcp_bindings({}, "http://localhost/proxy", "session123")
        assert result == ""

    def test_non_mcp_tools(self):
        tools = {
            "builtin_tool": {
                "type": "builtin",
                "spec": {"name": "builtin_tool"},
            }
        }
        result = generate_mcp_bindings(tools, "http://localhost/proxy", "session123")
        assert result == ""

    def test_single_mcp_tool(self):
        tools = {
            "hue_set_light": {
                "type": "mcp",
                "spec": {
                    "name": "hue_set_light",
                    "description": "Set light state",
                    "parameters": {
                        "properties": {
                            "light_id": {"type": "string"},
                            "on": {"type": "boolean"},
                        },
                        "required": ["light_id", "on"],
                    },
                },
            }
        }

        result = generate_mcp_bindings(tools, "http://localhost/proxy", "session123")

        # Check that bindings code contains expected elements
        assert "class MCPTools:" in result
        assert "mcp_tools = MCPTools()" in result
        assert "_MCP_PROXY_URL" in result
        assert "_MCP_SESSION_ID" in result
        assert "session123" in result
        assert "http://localhost/proxy" in result
        assert "_call_mcp_tool" in result
        assert "def set_light" in result  # Method name derived from tool name

    def test_multiple_mcp_tools(self):
        tools = {
            "server1_tool1": {
                "type": "mcp",
                "spec": {
                    "name": "server1_tool1",
                    "description": "Tool 1 from server 1",
                    "parameters": {"properties": {}},
                },
            },
            "server1_tool2": {
                "type": "mcp",
                "spec": {
                    "name": "server1_tool2",
                    "description": "Tool 2 from server 1",
                    "parameters": {"properties": {}},
                },
            },
            "server2_tool1": {
                "type": "mcp",
                "spec": {
                    "name": "server2_tool1",
                    "description": "Tool 1 from server 2",
                    "parameters": {"properties": {}},
                },
            },
        }

        result = generate_mcp_bindings(tools, "http://localhost/proxy", "session123")

        # Check that all tools are included
        assert "def tool1(" in result
        assert "def tool2(" in result
        assert "Tool 1 from server 1" in result
        assert "Tool 2 from server 1" in result
        assert "Tool 1 from server 2" in result


class TestGenerateCodeModePrompt:
    """Tests for code mode prompt generation."""

    def test_empty_tools(self):
        result = generate_code_mode_prompt({})
        assert result == ""

    def test_non_mcp_tools(self):
        tools = {
            "builtin_tool": {
                "type": "builtin",
                "spec": {"name": "builtin_tool"},
            }
        }
        result = generate_code_mode_prompt(tools)
        assert result == ""

    def test_single_mcp_tool(self):
        tools = {
            "hue_set_light": {
                "type": "mcp",
                "spec": {
                    "name": "hue_set_light",
                    "description": "Set the state of a Hue light",
                    "parameters": {
                        "properties": {
                            "light_id": {"type": "string"},
                            "on": {"type": "boolean"},
                        },
                        "required": ["light_id"],
                    },
                },
            }
        }

        result = generate_code_mode_prompt(tools)

        # Check that prompt contains expected information
        assert "MCP Tools" in result
        assert "mcp_tools.set_light" in result
        assert "Set the state of a Hue light" in result
        assert "light_id: str*" in result  # Required parameter marked with *
        assert "on: bool" in result

    def test_prompt_includes_usage_instructions(self):
        tools = {
            "server_tool": {
                "type": "mcp",
                "spec": {
                    "name": "server_tool",
                    "description": "A test tool",
                    "parameters": {"properties": {}},
                },
            }
        }

        result = generate_code_mode_prompt(tools)

        # Check for usage instructions
        assert "How to use MCP tools in code" in result
        assert "mcp_tools" in result
        assert "Example" in result


class TestMcpBindingsSyntax:
    """Tests that verify the generated bindings code is valid Python."""

    def test_bindings_are_valid_python(self):
        tools = {
            "server_get_data": {
                "type": "mcp",
                "spec": {
                    "name": "server_get_data",
                    "description": "Get data from server",
                    "parameters": {
                        "properties": {
                            "id": {"type": "string"},
                            "include_metadata": {"type": "boolean"},
                        },
                        "required": ["id"],
                    },
                },
            }
        }

        code = generate_mcp_bindings(tools, "http://localhost:8080/api", "test-session")

        # Verify the code is syntactically valid Python
        # This will raise SyntaxError if the code is invalid
        compile(code, "<string>", "exec")

    def test_bindings_with_special_characters_in_names(self):
        """Test that tool names with dashes and dots are handled."""
        tools = {
            "server_my-tool.v2": {
                "type": "mcp",
                "spec": {
                    "name": "server_my-tool.v2",
                    "description": "A tool with special characters",
                    "parameters": {"properties": {}},
                },
            }
        }

        code = generate_mcp_bindings(tools, "http://localhost/proxy", "session")

        # Verify valid Python (dashes and dots replaced with underscores)
        compile(code, "<string>", "exec")
        assert "def my_tool_v2(" in code


# ── Helpers for execution tests ──────────────────────────────────────────────


def _make_mock_urlopen(responses: list[dict]):
    """
    Create a mock urllib.request.urlopen that returns predefined responses.

    Args:
        responses: List of response dicts, each with "result" and "error" keys.

    Returns:
        (mock_urlopen_fn, call_log) where call_log records each request body.
    """
    call_log = []
    response_iter = iter(responses)

    def mock_urlopen(req, **kwargs):
        data = json.loads(req.data.decode("utf-8"))
        call_log.append(data)
        response_data = json.dumps(next(response_iter)).encode("utf-8")
        mock_resp = io.BytesIO(response_data)
        mock_resp.status = 200
        mock_resp.read = lambda: response_data
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = lambda s, *a: None
        return mock_resp

    return mock_urlopen, call_log


def _exec_bindings(tools, code_to_run, responses):
    """
    Generate bindings, execute code_to_run against mock responses.

    Returns:
        (exec_globals, call_log)
    """
    import urllib.request

    bindings = generate_mcp_bindings(tools, "http://mock/proxy", "test-session")
    mock_urlopen, call_log = _make_mock_urlopen(responses)
    original = urllib.request.urlopen
    urllib.request.urlopen = mock_urlopen
    try:
        exec_globals = {}
        exec(bindings + "\n" + code_to_run, exec_globals)
    finally:
        urllib.request.urlopen = original
    return exec_globals, call_log


# Simple tool fixtures used across execution tests

_LIGHT_TOOLS = {
    "hue_get_lights": {
        "type": "mcp",
        "spec": {
            "name": "hue_get_lights",
            "description": "Get all lights with their state",
            "parameters": {"properties": {}},
        },
    },
    "hue_set_light": {
        "type": "mcp",
        "spec": {
            "name": "hue_set_light",
            "description": "Set the state of a light",
            "parameters": {
                "properties": {
                    "light_id": {"type": "string", "description": "The light ID"},
                    "on": {"type": "boolean", "description": "On or off"},
                    "brightness": {"type": "integer", "description": "0-254"},
                },
                "required": ["light_id", "on"],
            },
        },
    },
}


class TestBindingsExecution:
    """
    Tests that execute generated bindings against mock HTTP responses.

    These tests verify runtime behavior, not just code generation.
    They would catch issues like missing _unwrap_mcp_content.
    """

    def test_single_text_content_unwrapped_to_dict(self):
        """MCP response with one text item containing JSON dict → returns dict."""
        lights = [{"id": "1", "name": "Living Room", "on": True}]
        response = {
            "result": [{"type": "text", "text": json.dumps(lights)}],
            "error": None,
        }

        g, log = _exec_bindings(
            _LIGHT_TOOLS,
            "result = mcp_tools.get_lights()",
            [response],
        )

        result = g["result"]
        # Should be the parsed list, not the MCP wrapper
        assert isinstance(result, list), f"Expected list, got {type(result)}: {result}"
        assert len(result) == 1
        assert result[0]["id"] == "1"
        assert result[0]["name"] == "Living Room"

    def test_single_text_content_unwrapped_to_nested_dict(self):
        """MCP response with a JSON object text → returns dict directly."""
        payload = {"lights": [{"id": "1"}, {"id": "2"}]}
        response = {
            "result": [{"type": "text", "text": json.dumps(payload)}],
            "error": None,
        }

        g, _ = _exec_bindings(
            _LIGHT_TOOLS,
            "result = mcp_tools.get_lights()",
            [response],
        )

        result = g["result"]
        assert isinstance(result, dict), f"Expected dict, got {type(result)}: {result}"
        assert "lights" in result
        assert len(result["lights"]) == 2

    def test_plain_text_content_returned_as_string(self):
        """MCP response with non-JSON text → returns string."""
        response = {
            "result": [{"type": "text", "text": "Light turned off successfully"}],
            "error": None,
        }

        g, _ = _exec_bindings(
            _LIGHT_TOOLS,
            "result = mcp_tools.get_lights()",
            [response],
        )

        result = g["result"]
        assert isinstance(result, str), f"Expected str, got {type(result)}: {result}"
        assert result == "Light turned off successfully"

    def test_multiple_text_items_returned_as_list(self):
        """MCP response with multiple text items → returns list of parsed items."""
        response = {
            "result": [
                {"type": "text", "text": json.dumps({"id": "1", "success": True})},
                {"type": "text", "text": json.dumps({"id": "2", "success": True})},
            ],
            "error": None,
        }

        g, _ = _exec_bindings(
            _LIGHT_TOOLS,
            "result = mcp_tools.get_lights()",
            [response],
        )

        result = g["result"]
        assert isinstance(result, list), f"Expected list, got {type(result)}: {result}"
        assert len(result) == 2
        assert result[0]["id"] == "1"
        assert result[1]["id"] == "2"

    def test_tool_params_passed_to_proxy(self):
        """Tool parameters are correctly forwarded to the proxy."""
        response = {
            "result": [{"type": "text", "text": json.dumps({"success": True})}],
            "error": None,
        }

        g, log = _exec_bindings(
            _LIGHT_TOOLS,
            'result = mcp_tools.set_light(light_id="1", on=False, brightness=100)',
            [response],
        )

        assert len(log) == 1
        call = log[0]
        assert call["tool_name"] == "hue_set_light"
        assert call["session_id"] == "test-session"
        assert call["arguments"]["light_id"] == "1"
        assert call["arguments"]["on"] is False
        assert call["arguments"]["brightness"] == 100

    def test_error_response_raises_exception(self):
        """When the proxy returns an error, the binding raises an exception."""
        response = {
            "result": None,
            "error": "Tool execution failed: connection refused",
        }

        with pytest.raises(Exception, match="Tool execution failed"):
            _exec_bindings(
                _LIGHT_TOOLS,
                "result = mcp_tools.get_lights()",
                [response],
            )

    def test_loop_over_unwrapped_results(self):
        """
        Simulate LLM pattern: get items, loop over them, call tool for each.

        This is the key test that would have caught the missing
        _unwrap_mcp_content issue. Without unwrapping, the LLM code
        would get MCP wrapper dicts instead of plain data and fail
        when trying to access fields like item['id'].
        """
        lights = [
            {"id": "1", "name": "Living Room", "on": True},
            {"id": "2", "name": "Bedroom", "on": True},
            {"id": "3", "name": "Kitchen", "on": True},
        ]

        # First response: get_lights returns list of lights
        get_response = {
            "result": [{"type": "text", "text": json.dumps(lights)}],
            "error": None,
        }
        # Three set_light responses
        set_responses = [
            {"result": [{"type": "text", "text": json.dumps({"success": True, "id": str(i)})}], "error": None}
            for i in range(1, 4)
        ]

        user_code = """
results = []
lights = mcp_tools.get_lights()
for light in lights:
    r = mcp_tools.set_light(light_id=light['id'], on=False)
    results.append(r)
"""

        g, log = _exec_bindings(
            _LIGHT_TOOLS,
            user_code,
            [get_response] + set_responses,
        )

        # Verify get_lights was called once
        get_calls = [c for c in log if c["tool_name"] == "hue_get_lights"]
        assert len(get_calls) == 1

        # Verify set_light was called 3 times with correct IDs
        set_calls = [c for c in log if c["tool_name"] == "hue_set_light"]
        assert len(set_calls) == 3
        set_ids = [c["arguments"]["light_id"] for c in set_calls]
        assert set_ids == ["1", "2", "3"]

        # Verify each set_light was called with on=False
        for call in set_calls:
            assert call["arguments"]["on"] is False

        # Verify results were collected
        results = g["results"]
        assert len(results) == 3
        assert all(isinstance(r, dict) for r in results)
        assert all(r["success"] is True for r in results)

    def test_conditional_on_unwrapped_data(self):
        """
        Simulate LLM pattern: get items, check field, act conditionally.

        Tests that unwrapped data supports direct field access for conditionals.
        """
        lights = [
            {"id": "1", "name": "Living Room", "on": True},
            {"id": "2", "name": "Bedroom", "on": False},
            {"id": "3", "name": "Kitchen", "on": True},
        ]

        get_response = {
            "result": [{"type": "text", "text": json.dumps(lights)}],
            "error": None,
        }
        # Only 2 set_light responses (lights 1 and 3 are on)
        set_responses = [
            {"result": [{"type": "text", "text": json.dumps({"success": True})}], "error": None}
            for _ in range(2)
        ]

        user_code = """
turned_off = []
lights = mcp_tools.get_lights()
for light in lights:
    if light['on']:
        mcp_tools.set_light(light_id=light['id'], on=False)
        turned_off.append(light['id'])
"""

        g, log = _exec_bindings(
            _LIGHT_TOOLS,
            user_code,
            [get_response] + set_responses,
        )

        set_calls = [c for c in log if c["tool_name"] == "hue_set_light"]
        assert len(set_calls) == 2
        turned_off = g["turned_off"]
        assert turned_off == ["1", "3"]

    def test_chained_tool_calls(self):
        """
        Simulate LLM pattern: use output of first tool as input to second.

        Get lights, find one by name, then set it.
        """
        lights = [
            {"id": "1", "name": "Living Room", "on": False},
            {"id": "2", "name": "Kitchen", "on": False},
        ]

        get_response = {
            "result": [{"type": "text", "text": json.dumps(lights)}],
            "error": None,
        }
        set_response = {
            "result": [{"type": "text", "text": json.dumps({"success": True, "on": True})}],
            "error": None,
        }

        user_code = """
lights = mcp_tools.get_lights()
kitchen = [l for l in lights if l['name'] == 'Kitchen'][0]
result = mcp_tools.set_light(light_id=kitchen['id'], on=True)
"""

        g, log = _exec_bindings(
            _LIGHT_TOOLS,
            user_code,
            [get_response, set_response],
        )

        set_calls = [c for c in log if c["tool_name"] == "hue_set_light"]
        assert len(set_calls) == 1
        assert set_calls[0]["arguments"]["light_id"] == "2"
        assert set_calls[0]["arguments"]["on"] is True

    def test_aggregation_over_unwrapped_data(self):
        """
        Simulate LLM pattern: get data, compute statistics.

        Tests that unwrapped list items support numeric operations.
        """
        sensors = [
            {"id": "t1", "name": "Room 1", "value": 22.5},
            {"id": "t2", "name": "Room 2", "value": 19.8},
            {"id": "t3", "name": "Room 3", "value": 24.1},
        ]

        tools = {
            "ha_get_sensors": {
                "type": "mcp",
                "spec": {
                    "name": "ha_get_sensors",
                    "description": "Get sensor readings",
                    "parameters": {"properties": {}},
                },
            },
        }

        response = {
            "result": [{"type": "text", "text": json.dumps(sensors)}],
            "error": None,
        }

        user_code = """
sensors = mcp_tools.get_sensors()
temps = [s['value'] for s in sensors]
avg_temp = sum(temps) / len(temps)
max_temp = max(temps)
min_temp = min(temps)
"""

        g, log = _exec_bindings(tools, user_code, [response])

        assert len(log) == 1
        assert abs(g["avg_temp"] - 22.133) < 0.01
        assert g["max_temp"] == 24.1
        assert g["min_temp"] == 19.8

    def test_image_content_preserved(self):
        """Image content items are passed through unchanged."""
        response = {
            "result": [
                {"type": "image", "data": "base64data==", "mimeType": "image/png"},
            ],
            "error": None,
        }

        g, _ = _exec_bindings(
            _LIGHT_TOOLS,
            "result = mcp_tools.get_lights()",
            [response],
        )

        result = g["result"]
        assert isinstance(result, dict)
        assert result["type"] == "image"
        assert result["data"] == "base64data=="

    def test_non_list_result_passed_through(self):
        """If MCP result is not a list (unusual), it passes through unchanged."""
        response = {
            "result": {"direct": "value"},
            "error": None,
        }

        g, _ = _exec_bindings(
            _LIGHT_TOOLS,
            "result = mcp_tools.get_lights()",
            [response],
        )

        result = g["result"]
        assert result == {"direct": "value"}
