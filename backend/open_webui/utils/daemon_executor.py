"""
Daemon Executor: Background execution for long-running code interpreter scripts.

Starts a persistent Jupyter kernel and streams output to the chat in real time
via Socket.IO events. Only works with the Jupyter engine.
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

import aiohttp
import websockets

from open_webui.routers.code_mode import unregister_code_mode_session

log = logging.getLogger(__name__)

MAX_DAEMONS_PER_USER = 3


@dataclass
class DaemonInfo:
    daemon_id: str
    task: asyncio.Task
    kernel_id: str
    user_id: str
    chat_id: str
    message_id: str
    code_mode_session_id: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    status: str = "running"  # "running" | "stopped" | "error" | "completed"


_active_daemons: dict[str, DaemonInfo] = {}


def _get_user_daemon_count(user_id: str) -> int:
    return sum(
        1
        for d in _active_daemons.values()
        if d.user_id == user_id and d.status == "running"
    )


async def _create_jupyter_session(
    base_url: str,
    token: Optional[str] = None,
    password: Optional[str] = None,
) -> tuple[aiohttp.ClientSession, dict, str]:
    """Create an authenticated aiohttp session and start a Jupyter kernel.

    Returns (session, params, kernel_id).
    """
    if not base_url.endswith("/"):
        base_url += "/"

    session = aiohttp.ClientSession(trust_env=True, base_url=base_url)
    params: dict = {}

    # password authentication
    if password and not token:
        async with session.get("login") as response:
            response.raise_for_status()
            xsrf_token = response.cookies["_xsrf"].value
            if not xsrf_token:
                raise ValueError("_xsrf token not found")
            session.cookie_jar.update_cookies(response.cookies)
            session.headers.update({"X-XSRFToken": xsrf_token})
        async with session.post(
            "login",
            data={"_xsrf": xsrf_token, "password": password},
            allow_redirects=False,
        ) as response:
            response.raise_for_status()
            session.cookie_jar.update_cookies(response.cookies)

    # token authentication
    if token:
        params["token"] = token

    # start kernel
    async with session.post(url="api/kernels", params=params) as response:
        response.raise_for_status()
        kernel_data = await response.json()
        kernel_id = kernel_data["id"]

    return session, params, kernel_id


def _build_ws_url(
    base_url: str,
    kernel_id: str,
    params: dict,
    session: aiohttp.ClientSession,
    password: Optional[str] = None,
    token: Optional[str] = None,
) -> tuple[str, dict]:
    """Build WebSocket URL and headers for connecting to a Jupyter kernel."""
    if not base_url.endswith("/"):
        base_url += "/"
    ws_base = base_url.replace("http", "ws", 1)
    ws_params = (
        "?" + "&".join(f"{k}={v}" for k, v in params.items()) if params else ""
    )
    websocket_url = f"{ws_base}api/kernels/{kernel_id}/channels{ws_params}"
    ws_headers: dict = {}
    if password and not token:
        ws_headers = {
            "Cookie": "; ".join(
                f"{cookie.key}={cookie.value}"
                for cookie in session.cookie_jar
            ),
            **session.headers,
        }
    return websocket_url, ws_headers


async def start_daemon(
    base_url: str,
    code: str,
    token: Optional[str],
    password: Optional[str],
    user_id: str,
    chat_id: str,
    message_id: str,
    event_emitter,
    code_mode_session_id: Optional[str] = None,
    max_runtime: int = 3600,
) -> str:
    """Start a background daemon that executes code in a persistent Jupyter kernel.

    Returns the daemon_id.
    """
    if _get_user_daemon_count(user_id) >= MAX_DAEMONS_PER_USER:
        raise RuntimeError(
            f"Maximum concurrent background scripts ({MAX_DAEMONS_PER_USER}) reached. "
            "Stop an existing one before starting another."
        )

    daemon_id = str(uuid.uuid4())

    session, params, kernel_id = await _create_jupyter_session(
        base_url, token, password
    )

    websocket_url, ws_headers = _build_ws_url(
        base_url, kernel_id, params, session, password, token
    )

    task = asyncio.create_task(
        _run_daemon(
            daemon_id=daemon_id,
            session=session,
            params=params,
            kernel_id=kernel_id,
            websocket_url=websocket_url,
            ws_headers=ws_headers,
            code=code,
            event_emitter=event_emitter,
            max_runtime=max_runtime,
        )
    )

    info = DaemonInfo(
        daemon_id=daemon_id,
        task=task,
        kernel_id=kernel_id,
        user_id=user_id,
        chat_id=chat_id,
        message_id=message_id,
        code_mode_session_id=code_mode_session_id,
    )
    _active_daemons[daemon_id] = info

    log.info(
        f"Started daemon {daemon_id} for user {user_id} "
        f"in chat {chat_id} (kernel={kernel_id})"
    )

    return daemon_id


async def _run_daemon(
    daemon_id: str,
    session: aiohttp.ClientSession,
    params: dict,
    kernel_id: str,
    websocket_url: str,
    ws_headers: dict,
    code: str,
    event_emitter,
    max_runtime: int,
) -> None:
    """Background coroutine: execute code and stream output until done or stopped."""
    info = _active_daemons.get(daemon_id)
    try:
        async with websockets.connect(
            websocket_url, additional_headers=ws_headers
        ) as ws:
            # Send execute request
            msg_id = uuid.uuid4().hex
            await ws.send(
                json.dumps(
                    {
                        "header": {
                            "msg_id": msg_id,
                            "msg_type": "execute_request",
                            "username": "user",
                            "session": uuid.uuid4().hex,
                            "date": "",
                            "version": "5.3",
                        },
                        "parent_header": {},
                        "metadata": {},
                        "content": {
                            "code": code,
                            "silent": False,
                            "store_history": True,
                            "user_expressions": {},
                            "allow_stdin": False,
                            "stop_on_error": True,
                        },
                        "channel": "shell",
                    }
                )
            )

            # Emit running status
            await _emit_status(event_emitter, daemon_id, info, "running")

            # Stream output
            deadline = time.time() + max_runtime
            while True:
                remaining = deadline - time.time()
                if remaining <= 0:
                    await _emit_output(
                        event_emitter,
                        daemon_id,
                        info,
                        "stderr",
                        f"\nBackground script exceeded max runtime ({max_runtime}s). Stopping.",
                    )
                    break

                try:
                    message = await asyncio.wait_for(
                        ws.recv(), timeout=min(remaining, 30.0)
                    )
                except asyncio.TimeoutError:
                    # No output for 30s, just loop to check deadline
                    continue

                message_data = json.loads(message)
                if (
                    message_data.get("parent_header", {}).get("msg_id")
                    != msg_id
                ):
                    continue

                msg_type = message_data.get("msg_type")
                content = message_data.get("content", {})

                if msg_type == "stream":
                    stream_name = content.get("name", "stdout")
                    text = content.get("text", "")
                    if text:
                        await _emit_output(
                            event_emitter, daemon_id, info, stream_name, text
                        )

                elif msg_type in ("execute_result", "display_data"):
                    data = content.get("data", {})
                    if "text/plain" in data:
                        await _emit_output(
                            event_emitter,
                            daemon_id,
                            info,
                            "stdout",
                            data["text/plain"],
                        )

                elif msg_type == "error":
                    traceback_text = "\n".join(
                        content.get("traceback", [])
                    )
                    await _emit_output(
                        event_emitter,
                        daemon_id,
                        info,
                        "stderr",
                        traceback_text,
                    )
                    if info:
                        info.status = "error"
                    await _emit_status(event_emitter, daemon_id, info, "error", "Script raised an error")
                    break

                elif msg_type == "status":
                    if (
                        content.get("execution_state")
                        == "idle"
                    ):
                        # Script finished naturally
                        if info:
                            info.status = "completed"
                        await _emit_status(
                            event_emitter,
                            daemon_id,
                            info,
                            "completed",
                            "Script finished",
                        )
                        break

    except asyncio.CancelledError:
        log.info(f"Daemon {daemon_id} cancelled")
        if info:
            info.status = "stopped"
        await _emit_status(event_emitter, daemon_id, info, "stopped", "Stopped by user")
    except Exception as e:
        log.exception(f"Daemon {daemon_id} error: {e}")
        if info:
            info.status = "error"
        await _emit_status(event_emitter, daemon_id, info, "error", str(e))
    finally:
        # Clean up kernel
        try:
            async with session.delete(
                f"api/kernels/{kernel_id}", params=params
            ) as response:
                response.raise_for_status()
        except Exception as err:
            log.warning(f"Failed to delete kernel {kernel_id}: {err}")
        await session.close()

        # Clean up MCP session
        if info and info.code_mode_session_id:
            try:
                unregister_code_mode_session(info.code_mode_session_id)
            except Exception:
                pass

        # Remove from active daemons
        _active_daemons.pop(daemon_id, None)
        log.info(f"Daemon {daemon_id} cleaned up")


async def _emit_output(
    event_emitter,
    daemon_id: str,
    info: Optional[DaemonInfo],
    stream: str,
    content: str,
) -> None:
    """Emit a daemon:output event to the user's Socket.IO room."""
    if event_emitter is None:
        return
    try:
        await event_emitter(
            {
                "type": "daemon:output",
                "data": {
                    "daemon_id": daemon_id,
                    "chat_id": info.chat_id if info else "",
                    "message_id": info.message_id if info else "",
                    "stream": stream,
                    "content": content,
                    "timestamp": time.time(),
                },
            }
        )
    except Exception as e:
        log.debug(f"Failed to emit daemon output: {e}")


async def _emit_status(
    event_emitter,
    daemon_id: str,
    info: Optional[DaemonInfo],
    status: str,
    reason: str = "",
) -> None:
    """Emit a daemon:status event to the user's Socket.IO room."""
    if event_emitter is None:
        return
    try:
        await event_emitter(
            {
                "type": "daemon:status",
                "data": {
                    "daemon_id": daemon_id,
                    "chat_id": info.chat_id if info else "",
                    "message_id": info.message_id if info else "",
                    "status": status,
                    "reason": reason,
                },
            }
        )
    except Exception as e:
        log.debug(f"Failed to emit daemon status: {e}")


async def stop_daemon(daemon_id: str) -> bool:
    """Stop a running daemon by ID. Returns True if found and stopped."""
    info = _active_daemons.get(daemon_id)
    if not info:
        return False

    if info.status == "running":
        info.status = "stopped"
        info.task.cancel()
        try:
            await info.task
        except (asyncio.CancelledError, Exception):
            pass

    return True


def list_daemons(
    user_id: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> list[dict]:
    """List active daemons, optionally filtered by user_id or chat_id."""
    results = []
    for info in _active_daemons.values():
        if user_id and info.user_id != user_id:
            continue
        if chat_id and info.chat_id != chat_id:
            continue
        results.append(
            {
                "daemon_id": info.daemon_id,
                "kernel_id": info.kernel_id,
                "user_id": info.user_id,
                "chat_id": info.chat_id,
                "message_id": info.message_id,
                "started_at": info.started_at,
                "status": info.status,
            }
        )
    return results


async def cleanup_user_daemons(user_id: str) -> int:
    """Stop all running daemons for a user. Returns count of daemons stopped."""
    to_stop = [
        daemon_id
        for daemon_id, info in _active_daemons.items()
        if info.user_id == user_id and info.status == "running"
    ]
    for daemon_id in to_stop:
        await stop_daemon(daemon_id)
    return len(to_stop)
