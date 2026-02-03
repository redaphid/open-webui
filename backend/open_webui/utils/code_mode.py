"""
Code Mode: MCP Tool Bindings for Code Interpreter

This module generates Python bindings for MCP tools that can be injected into
the code interpreter environment. Instead of calling MCP tools via function calling,
the LLM writes Python code that calls these tools directly.

Based on Cloudflare's Code Mode approach:
https://blog.cloudflare.com/code-mode/
"""

import json
import logging
import textwrap
from typing import Any

log = logging.getLogger(__name__)


def json_schema_to_python_type(schema: dict) -> str:
    """Convert JSON schema type to Python type hint."""
    if not schema:
        return "Any"

    schema_type = schema.get("type", "any")

    if schema_type == "string":
        return "str"
    elif schema_type == "integer":
        return "int"
    elif schema_type == "number":
        return "float"
    elif schema_type == "boolean":
        return "bool"
    elif schema_type == "array":
        items = schema.get("items", {})
        item_type = json_schema_to_python_type(items)
        return f"list[{item_type}]"
    elif schema_type == "object":
        return "dict"
    elif schema_type == "null":
        return "None"
    else:
        return "Any"


def generate_function_signature(tool_spec: dict) -> tuple[str, str]:
    """
    Generate Python function signature and docstring from MCP tool spec.

    Returns:
        tuple: (signature_params, docstring)
    """
    name = tool_spec.get("name", "unknown_tool")
    description = tool_spec.get("description", "No description available.")
    parameters = tool_spec.get("parameters", {})

    # Build parameter list
    params = []
    param_docs = []

    properties = parameters.get("properties", {})
    required = parameters.get("required", [])

    for param_name, param_schema in properties.items():
        param_type = json_schema_to_python_type(param_schema)
        param_desc = param_schema.get("description", "")

        if param_name in required:
            params.append(f"{param_name}: {param_type}")
        else:
            params.append(f"{param_name}: {param_type} = None")

        if param_desc:
            param_docs.append(f"            {param_name}: {param_desc}")

    signature_params = ", ".join(params)

    # Build docstring (with 8 space indent for class method)
    docstring_parts = [f'        """{description}']
    if param_docs:
        docstring_parts.append("")
        docstring_parts.append("        Args:")
        docstring_parts.extend(param_docs)
    docstring_parts.append('        """')
    docstring = "\n".join(docstring_parts)

    return signature_params, docstring


def generate_mcp_bindings(
    mcp_tools: dict[str, dict],
    proxy_url: str,
    session_id: str,
) -> str:
    """
    Generate Python code that provides MCP tool bindings for the code interpreter.

    Args:
        mcp_tools: Dictionary of MCP tools with their specs
        proxy_url: URL of the internal MCP proxy endpoint
        session_id: Session ID for authentication

    Returns:
        Python code string to be prepended to user code
    """
    if not mcp_tools:
        return ""

    # Group tools by server
    servers: dict[str, list[dict]] = {}
    for tool_id, tool_data in mcp_tools.items():
        if tool_data.get("type") != "mcp":
            continue

        spec = tool_data.get("spec", {})
        # Tool names are prefixed with server_id_
        full_name = spec.get("name", tool_id)

        # Extract server_id from the tool name (format: server_id_tool_name)
        parts = full_name.split("_", 1)
        if len(parts) == 2:
            server_id, tool_name = parts
        else:
            server_id = "default"
            tool_name = full_name

        if server_id not in servers:
            servers[server_id] = []

        servers[server_id].append({
            "full_name": full_name,
            "name": tool_name,
            "spec": spec,
        })

    if not servers:
        return ""

    # Generate the binding code
    binding_code = textwrap.dedent(f'''
        # ============================================================
        # MCP Tool Bindings (Code Mode)
        # These functions allow you to call MCP tools directly in code.
        # ============================================================

        import json
        import urllib.request
        import urllib.error

        _MCP_PROXY_URL = "{proxy_url}"
        _MCP_SESSION_ID = "{session_id}"

        def _unwrap_mcp_content(result):
            """Unwrap MCP content items into plain Python data.

            MCP tools return content as a list of items like:
              [{{"type": "text", "text": '{{"key": "value"}}'}}, ...]

            This function extracts and parses the text content so tool
            results are directly usable in code.
            """
            if not isinstance(result, list):
                return result

            texts = []
            for item in result:
                if isinstance(item, dict) and item.get("type") == "text":
                    raw = item.get("text", "")
                    # Try to parse JSON text into Python objects
                    try:
                        texts.append(json.loads(raw))
                    except (json.JSONDecodeError, TypeError):
                        texts.append(raw)
                elif isinstance(item, dict) and item.get("type") == "image":
                    texts.append(item)  # Keep image items as-is
                else:
                    texts.append(item)

            # If there's exactly one text result, return it directly
            if len(texts) == 1:
                return texts[0]
            return texts

        def _call_mcp_tool(tool_name: str, **kwargs):
            """Internal function to call MCP tools via proxy."""
            data = json.dumps({{
                "tool_name": tool_name,
                "arguments": kwargs,
                "session_id": _MCP_SESSION_ID,
            }}).encode("utf-8")

            req = urllib.request.Request(
                _MCP_PROXY_URL,
                data=data,
                headers={{"Content-Type": "application/json"}},
                method="POST",
            )

            try:
                with urllib.request.urlopen(req, timeout=60) as response:
                    result = json.loads(response.read().decode("utf-8"))
                    if result.get("error"):
                        raise Exception(result["error"])
                    return _unwrap_mcp_content(result.get("result", {{}}))
            except urllib.error.HTTPError as e:
                error_body = e.read().decode("utf-8")
                raise Exception(f"MCP tool call failed: {{error_body}}")
            except urllib.error.URLError as e:
                raise Exception(f"MCP proxy connection failed: {{e.reason}}")


        class MCPTools:
            """
            MCP Tools available for this session.

            Available servers and tools:
    ''')

    # Add tool documentation to class docstring
    for server_id, tools in servers.items():
        binding_code += f"        - {server_id}:\n"
        for tool in tools:
            desc = tool["spec"].get("description", "")[:60]
            binding_code += f"            - {tool['name']}: {desc}...\n"

    binding_code += '    """\n\n'

    # Generate methods for each tool
    for server_id, tools in servers.items():
        binding_code += f"    # Tools from server: {server_id}\n"

        for tool in tools:
            spec = tool["spec"]
            full_name = tool["full_name"]
            method_name = tool["name"].replace("-", "_").replace(".", "_")

            signature_params, docstring = generate_function_signature(spec)

            # Build the kwargs dict for the call
            properties = spec.get("parameters", {}).get("properties", {})
            kwargs_items = []
            for param_name in properties.keys():
                safe_param = param_name.replace("-", "_")
                kwargs_items.append(f'"{param_name}": {safe_param}')

            kwargs_str = ", ".join(kwargs_items)

            binding_code += f'''
    @staticmethod
    def {method_name}({signature_params}):
{docstring}
        _kwargs = {{{kwargs_str}}}
        _kwargs = {{k: v for k, v in _kwargs.items() if v is not None}}
        return _call_mcp_tool("{full_name}", **_kwargs)
'''

    binding_code += '''

# Create the tools instance — use `mcp_tools` to avoid shadowing the `mcp` package
mcp_tools = MCPTools()

# ============================================================
# End of MCP Tool Bindings
# ============================================================

'''

    return binding_code


def generate_code_mode_prompt(mcp_tools: dict[str, dict]) -> str:
    """
    Generate additional prompt text describing available MCP tools for code mode.

    Args:
        mcp_tools: Dictionary of MCP tools with their specs

    Returns:
        Prompt text to append to the code interpreter prompt
    """
    if not mcp_tools:
        return ""

    # Filter to only MCP tools
    mcp_tool_list = [
        (tool_id, tool_data)
        for tool_id, tool_data in mcp_tools.items()
        if tool_data.get("type") == "mcp"
    ]

    if not mcp_tool_list:
        return ""

    prompt = textwrap.dedent('''
        2. **MCP Tools (Code Mode)**: In addition to the code interpreter, you have access to MCP (Model Context Protocol) tools that can be called directly from your Python code.

        **Available MCP Tools:**
    ''')

    for tool_id, tool_data in mcp_tool_list:
        spec = tool_data.get("spec", {})
        name = spec.get("name", tool_id)
        description = spec.get("description", "No description")

        # Convert tool name to method name
        parts = name.split("_", 1)
        if len(parts) == 2:
            method_name = parts[1].replace("-", "_").replace(".", "_")
        else:
            method_name = name.replace("-", "_").replace(".", "_")

        # Get parameters
        parameters = spec.get("parameters", {})
        properties = parameters.get("properties", {})
        required = parameters.get("required", [])

        param_strs = []
        for param_name, param_schema in properties.items():
            param_type = json_schema_to_python_type(param_schema)
            is_required = param_name in required
            param_strs.append(f"{param_name}: {param_type}{'*' if is_required else ''}")

        params_display = ", ".join(param_strs) if param_strs else "no parameters"

        prompt += f"        - `mcp_tools.{method_name}({params_display})`: {description}\n"

    prompt += textwrap.dedent('''
        **CRITICAL — How to use MCP tools in code:**
        - `mcp_tools` is a pre-configured global object already available in your code environment. Use it directly.
        - NEVER write `import mcp_tools` or `from mcp_tools import ...` — this will cause an error. The object is already defined for you.
        - Call tools like this: `result = mcp_tools.tool_name(param1=value1, param2=value2)`
        - All calls are synchronous and return plain Python data (dicts, lists, strings).
        - Print results to show the user: `print(result)`

        **Example:**
        ```python
        # mcp_tools is already available — do NOT import it
        items = mcp_tools.list_items()
        for item in items:
            print(item["name"])
        ```

        **Important:** When you have MCP tools available, prefer writing code that calls multiple tools in sequence rather than making individual tool calls. This is more efficient and allows you to process data between calls.
    ''')

    return prompt
