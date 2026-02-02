# Fork Changes: MCP & Code Interpreter Enhancements

This document describes all changes made in this fork of Open WebUI, covering two major features:

1. **Background Daemon Execution** for the Code Interpreter (Jupyter engine)
2. **MCP Server Configuration UI Improvements** including OAuth 2.1 support

---

## 1. Background Daemon Execution

### What It Does

Adds per-script background execution to the code interpreter. An LLM can mark a code block with `background="true"` to run it as a persistent background process in a Jupyter kernel. Output streams to the chat in real time via Socket.IO, and users can stop the script at any time.

**Use cases:** long-running animations, periodic monitoring, continuous data collection, IoT control loops.

**Requirement:** Only works with the **Jupyter** code execution engine. Pyodide (browser-based) cannot run background daemons.

### How It Works

1. The LLM writes a code block with `background="true"`:
   ```
   <code_interpreter type="code" lang="python" background="true">
   import time
   while True:
       print("heartbeat")
       time.sleep(5)
   </code_interpreter>
   ```

2. The middleware detects `background="true"` and, instead of executing synchronously, calls `daemon_executor.start_daemon()`.

3. A persistent Jupyter kernel is started, the code is injected, and an asyncio background task streams kernel output via Socket.IO `daemon:output` events.

4. The middleware returns immediately so the LLM can finish its response.

5. In the chat, the user sees a "Background Script Running" indicator with a pulsing green dot and a **Stop** button.

6. Output from the script appears in a live output area below the indicator.

7. The script runs until it:
   - Completes naturally
   - Raises an error
   - Hits the max runtime limit (default: 1 hour)
   - Is stopped by the user

### Configuration

| Environment Variable | Default | Description |
|---|---|---|
| `CODE_INTERPRETER_DAEMON_MAX_RUNTIME` | `3600` | Maximum runtime in seconds for background scripts |

This is also configurable via Admin Settings as a PersistentConfig value.

### Safety Limits

- **Per-user limit:** Maximum 3 concurrent background daemons per user
- **Max runtime:** Configurable, defaults to 1 hour
- **Disconnect cleanup:** All daemons for a user are stopped when their last Socket.IO session disconnects
- **Kernel cleanup:** Jupyter kernel is interrupted and deleted on stop
- **MCP session cleanup:** Associated code mode sessions are unregistered on daemon stop

### REST API Endpoints

#### List Active Daemons
```
GET /api/v1/daemons?chat_id=<optional>
Authorization: Bearer <token>
```
Returns a list of active daemons for the authenticated user. Admins see all daemons.

#### Stop a Daemon
```
POST /api/v1/daemons/<daemon_id>/stop
Authorization: Bearer <token>
```
Stops a specific daemon. Users can only stop their own daemons; admins can stop any.

#### Stop All Daemons in a Chat
```
POST /api/v1/daemons/chat/<chat_id>/stop
Authorization: Bearer <token>
```
Stops all running daemons associated with a chat.

### Socket.IO Events

| Event | Direction | Payload | Description |
|---|---|---|---|
| `daemon:output` | Server -> Client | `{ daemon_id, chat_id, message_id, stream, content, timestamp }` | Streaming stdout/stderr output from the daemon |
| `daemon:status` | Server -> Client | `{ daemon_id, chat_id, message_id, status, reason }` | Status changes: `running`, `stopped`, `completed`, `error` |
| `daemon:stop` | Client -> Server | `{ daemon_id }` | User requests to stop a daemon |

### LLM Prompt Integration

When the Jupyter engine is configured, the code interpreter system prompt automatically includes instructions for background execution:

> For long-running scripts (animations, monitoring, periodic tasks), use `<code_interpreter background="true">`. Output streams to the chat in real time and the user can stop the script anytime. Only use `background="true"` for scripts with intentional long-running behavior (loops with sleep, continuous monitoring). Regular scripts should NOT use it.

### Files Changed

| File | Change |
|---|---|
| `backend/open_webui/utils/daemon_executor.py` | **New.** Core daemon lifecycle: `start_daemon()`, `stop_daemon()`, `list_daemons()`, `cleanup_user_daemons()`, kernel management, output streaming |
| `backend/open_webui/config.py` | Added `CODE_INTERPRETER_DAEMON_MAX_RUNTIME` config variable |
| `backend/open_webui/utils/middleware.py` | Detect `background="true"`, branch to daemon execution, serialize background blocks, inject prompt |
| `backend/open_webui/main.py` | REST endpoints for listing/stopping daemons |
| `backend/open_webui/socket/main.py` | `daemon:stop` event handler, disconnect cleanup |
| `src/lib/stores/index.ts` | `daemonOutputs` writable store for streaming output |
| `src/lib/components/common/Collapsible.svelte` | Background script UI: pulsing indicator, Stop button, live output area |
| `src/lib/components/chat/Chat.svelte` | Socket.IO handlers for `daemon:output` and `daemon:status` events |

### Tests

48 integration tests in `backend/open_webui/test/utils/test_daemon_executor.py` covering:
- Daemon lifecycle (start, stop, cleanup)
- Output streaming (stdout, stderr, errors)
- Max runtime enforcement
- MCP session cleanup
- REST API endpoints (list, stop, authorization)
- Configuration

Run tests:
```bash
python -m pytest backend/open_webui/test/utils/test_daemon_executor.py -v
```

---

## 2. MCP Server Configuration UI Improvements

### What Changed

The MCP tool server configuration UI was improved for clarity and ease of use, particularly around the OAuth 2.1 setup flow.

### Type Selection Cards

**Before:** A tiny text button that toggled between "OpenAPI" and "MCP Streamable HTTP" - easy to miss.

**After:** Two clear, clickable cards in a 2-column grid. Each card shows:
- The protocol name (**OpenAPI** or **MCP**)
- A short description ("REST API with spec" / "Streamable HTTP")
- A visible border highlight on the selected card

This makes it immediately clear that two protocol types are available.

### OAuth 2.1 Registration Flow

**Before:** A small underlined "Register Client" text link and tiny "Not Registered"/"Registered" badges inline with the Auth dropdown. A toast warning about saving was easy to miss.

**After:** A dedicated bordered section appears below the auth dropdown when OAuth 2.1 is selected:
- Clear heading: "OAuth 2.1 Client Registration"
- Descriptive text explaining what registration does
- A prominent button styled consistently with the rest of the UI
- Button label changes to "Re-register Client" after initial registration
- Green confirmation text: "Client registered successfully. Save the connection to persist."
- Status badge remains in the Auth header row for quick reference

### Connection Verification Results

**Before:** Clicking "Verify Connection" showed only a success/failure toast notification.

**After:** On successful verification, a results panel appears below the URL field showing:
- "Connection verified" in green
- For MCP servers: the number of available tools and a list of the first 5 tool names
- For OpenAPI servers: the spec title and version
- Results clear automatically when URL, type, or auth method changes

### Connection List Badges

**Before:** Each connection in the list showed only a wrench icon and the server name or URL.

**After:** Each connection row now shows:
- A colored **type badge**: purple "MCP" or blue "OpenAPI"
- The server name/URL (unchanged)
- An **auth type indicator** (Bearer, Session, OAuth, OAuth 2.1) when authentication is configured

### OAuth Lock Icon in Chat

**Before:** MCP tools requiring OAuth authorization were shown with a darkened overlay and no explanation - users had no idea why the tool appeared disabled or what to do.

**After:** Unauthenticated OAuth tools show:
- A **lock icon** on the right side of the tool row
- A **tooltip** "Click to authorize with OAuth" on hover
- Clicking still initiates the OAuth authorization flow (unchanged behavior)

### MCP-Aware Tool Server Modal

**Before:** The "Available Tools" modal referenced only OpenAPI properties (`toolServer.openapi.info.title`, etc.), so MCP servers would show blank entries.

**After:**
- Server display uses a fallback chain: `openapi.info.title -> info.name -> url`
- Description uses: `openapi.info.description -> info.description -> ""`
- Version number only shows when available (no "undefined")
- MCP servers get a purple "MCP" badge next to the title
- Help text updated: "Open WebUI can use tools provided by OpenAPI and MCP servers"
- Link text updated: "Learn more about tool servers"

### Updated Description Text

Both the Admin Settings and User Chat Settings tool pages now say:
- Admin: "Connect to OpenAPI or MCP (Model Context Protocol) tool servers."
- User: "Connect to OpenAPI or MCP tool servers."

(Previously both said "Connect to your own OpenAPI compatible external tool servers.")

### Files Changed

| File | Change |
|---|---|
| `src/lib/components/AddToolServerModal.svelte` | Type selection cards, OAuth 2.1 registration section, verification results display |
| `src/lib/components/chat/Settings/Tools/Connection.svelte` | Type badge, auth indicator |
| `src/lib/components/chat/MessageInput/IntegrationsMenu.svelte` | Lock icon + tooltip for unauthenticated OAuth tools |
| `src/lib/components/chat/ToolServersModal.svelte` | MCP-aware display, type badges, updated help text |
| `src/lib/components/admin/Settings/Tools.svelte` | Updated description text |
| `src/lib/components/chat/Settings/Tools.svelte` | Updated description text |

---

## How to Use

### Setting Up an MCP Server (Admin)

1. Go to **Admin Settings > Tools**
2. Click the **+** button to add a new connection
3. Select the **MCP** card (right card)
4. Enter the server's **URL** (the streamable HTTP endpoint)
5. Click the refresh icon to **verify the connection** - you'll see the list of available tools
6. Set the **Auth** type:
   - **None** for public servers
   - **Bearer** for API key authentication
   - **OAuth 2.1** for OAuth-protected servers (see below)
7. Fill in the **ID** (required for MCP), **Name**, and **Description**
8. Click **Save**

### Setting Up OAuth 2.1 for an MCP Server

1. Follow steps 1-4 above
2. Select **OAuth 2.1** from the Auth dropdown
3. Fill in the **ID** field (required before registration)
4. In the "OAuth 2.1 Client Registration" section that appears, click **Register Client**
5. The system will:
   - Discover the OAuth server's metadata
   - Perform Dynamic Client Registration (RFC 7591)
   - Store the encrypted client credentials
6. You'll see "Client registered successfully. Save the connection to persist."
7. Click **Save** to persist the registration

After saving, users can authorize from the chat:
1. Open the **Integrations** menu in the chat input
2. Go to **Tools**
3. MCP tools requiring OAuth show a lock icon
4. Click the tool to start the OAuth authorization flow
5. After authorizing, the tool becomes available for use

### Using Background Scripts (Jupyter Engine)

1. Ensure the code interpreter is configured with the **Jupyter** engine
2. In a chat, ask the LLM to run a long-running script (e.g., "monitor my server every 10 seconds")
3. The LLM will use `background="true"` to start the script as a daemon
4. You'll see:
   - A "Background Script Running" indicator with a pulsing green dot
   - Live output streaming below the indicator
   - A red **Stop** button to terminate the script
5. The script runs until it completes, errors, hits the time limit, or you stop it

### Managing Background Scripts via API

List your active daemons:
```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/v1/daemons
```

Stop a specific daemon:
```bash
curl -X POST -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/v1/daemons/<daemon_id>/stop
```

Stop all daemons in a chat:
```bash
curl -X POST -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/v1/daemons/chat/<chat_id>/stop
```

---

## Complete File Change Summary

### New Files
| File | Description |
|---|---|
| `backend/open_webui/utils/daemon_executor.py` | Background daemon execution engine |
| `backend/open_webui/test/utils/test_daemon_executor.py` | 48 integration tests for daemon execution |
| `docs/mcp.md` | This documentation file |

### Modified Files
| File | Description |
|---|---|
| `backend/open_webui/config.py` | `CODE_INTERPRETER_DAEMON_MAX_RUNTIME` config |
| `backend/open_webui/main.py` | Daemon REST endpoints |
| `backend/open_webui/socket/main.py` | `daemon:stop` handler, disconnect cleanup |
| `backend/open_webui/utils/middleware.py` | Background execution branching, prompt injection, block serialization |
| `src/lib/stores/index.ts` | `daemonOutputs` store |
| `src/lib/components/common/Collapsible.svelte` | Background script UI |
| `src/lib/components/chat/Chat.svelte` | Daemon Socket.IO event handlers |
| `src/lib/components/AddToolServerModal.svelte` | Type cards, OAuth section, verify results |
| `src/lib/components/chat/Settings/Tools/Connection.svelte` | Type/auth badges |
| `src/lib/components/chat/MessageInput/IntegrationsMenu.svelte` | OAuth lock icon |
| `src/lib/components/chat/ToolServersModal.svelte` | MCP-aware display |
| `src/lib/components/admin/Settings/Tools.svelte` | Description text |
| `src/lib/components/chat/Settings/Tools.svelte` | Description text |
