"""
Integration tests for the daemon executor module.

Tests the full lifecycle of background code execution: daemon creation,
output streaming, stopping, cleanup, concurrency limits, and REST API
endpoints. Uses mocked Jupyter kernel and WebSocket connections.
"""

import asyncio
import json
import time

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from fastapi.testclient import TestClient

from open_webui.utils.daemon_executor import (
    DaemonInfo,
    _active_daemons,
    _get_user_daemon_count,
    _create_jupyter_session,
    _build_ws_url,
    start_daemon,
    stop_daemon,
    list_daemons,
    cleanup_user_daemons,
    MAX_DAEMONS_PER_USER,
    _run_daemon,
    _emit_output,
    _emit_status,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_jupyter_msg(msg_type, content, msg_id="test-msg-id"):
    """Build a minimal Jupyter wire-protocol message."""
    return json.dumps(
        {
            "parent_header": {"msg_id": msg_id},
            "msg_type": msg_type,
            "content": content,
        }
    )


def _make_status_idle(msg_id="test-msg-id"):
    return _make_jupyter_msg("status", {"execution_state": "idle"}, msg_id)


def _make_stream(text, name="stdout", msg_id="test-msg-id"):
    return _make_jupyter_msg("stream", {"name": name, "text": text}, msg_id)


def _make_error(traceback, msg_id="test-msg-id"):
    return _make_jupyter_msg("error", {"traceback": traceback}, msg_id)


def _make_execute_result(data, msg_id="test-msg-id"):
    return _make_jupyter_msg("execute_result", {"data": data}, msg_id)


class FakeWebSocket:
    """A fake WebSocket that yields pre-loaded messages, then idles."""

    def __init__(self, messages):
        self._messages = list(messages)
        self._sent = []
        self._closed = False

    async def send(self, data):
        self._sent.append(json.loads(data))

    async def recv(self):
        if self._messages:
            return self._messages.pop(0)
        # Block until cancelled (simulates idle kernel)
        await asyncio.sleep(3600)

    async def close(self):
        self._closed = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self._closed = True


class FakeResponse:
    """Minimal aiohttp response mock."""

    def __init__(self, json_data=None, status=200):
        self._json_data = json_data or {}
        self.status = status

    async def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status >= 400:
            raise Exception(f"HTTP {self.status}")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class FakeSession:
    """Minimal aiohttp.ClientSession mock."""

    def __init__(self, kernel_id="fake-kernel-123"):
        self._kernel_id = kernel_id
        self._closed = False
        self._deleted_kernels = []
        self.cookie_jar = []
        self.headers = {}

    def post(self, url="", **kwargs):
        return FakeResponse(json_data={"id": self._kernel_id})

    def delete(self, url="", **kwargs):
        self._deleted_kernels.append(url)
        return FakeResponse()

    def get(self, url="", **kwargs):
        return FakeResponse()

    async def close(self):
        self._closed = True


# ---------------------------------------------------------------------------
# Unit tests for internal helpers
# ---------------------------------------------------------------------------


class TestDaemonInfo:
    """Tests for the DaemonInfo dataclass."""

    def test_defaults(self):
        task = MagicMock()
        info = DaemonInfo(
            daemon_id="d1",
            task=task,
            kernel_id="k1",
            user_id="u1",
            chat_id="c1",
            message_id="m1",
        )
        assert info.status == "running"
        assert info.code_mode_session_id is None
        assert info.started_at > 0

    def test_custom_values(self):
        task = MagicMock()
        info = DaemonInfo(
            daemon_id="d1",
            task=task,
            kernel_id="k1",
            user_id="u1",
            chat_id="c1",
            message_id="m1",
            code_mode_session_id="s1",
            status="stopped",
        )
        assert info.code_mode_session_id == "s1"
        assert info.status == "stopped"


class TestGetUserDaemonCount:
    """Tests for the per-user daemon counter."""

    def setup_method(self):
        _active_daemons.clear()

    def test_zero_when_empty(self):
        assert _get_user_daemon_count("u1") == 0

    def test_counts_only_running(self):
        _active_daemons["d1"] = DaemonInfo(
            daemon_id="d1", task=MagicMock(), kernel_id="k1",
            user_id="u1", chat_id="c1", message_id="m1", status="running",
        )
        _active_daemons["d2"] = DaemonInfo(
            daemon_id="d2", task=MagicMock(), kernel_id="k2",
            user_id="u1", chat_id="c1", message_id="m2", status="stopped",
        )
        _active_daemons["d3"] = DaemonInfo(
            daemon_id="d3", task=MagicMock(), kernel_id="k3",
            user_id="u2", chat_id="c2", message_id="m3", status="running",
        )
        assert _get_user_daemon_count("u1") == 1
        assert _get_user_daemon_count("u2") == 1
        assert _get_user_daemon_count("u99") == 0


class TestBuildWsUrl:
    """Tests for WebSocket URL construction."""

    def test_token_auth(self):
        session = FakeSession()
        url, headers = _build_ws_url(
            "http://localhost:8888/",
            "kernel-123",
            {"token": "mytoken"},
            session,
            password=None,
            token="mytoken",
        )
        assert url == "ws://localhost:8888/api/kernels/kernel-123/channels?token=mytoken"
        assert headers == {}

    def test_password_auth(self):
        session = FakeSession()
        session.cookie_jar = [MagicMock(key="session", value="abc")]
        session.headers = {"X-XSRFToken": "xsrf123"}
        url, headers = _build_ws_url(
            "http://localhost:8888",
            "kernel-123",
            {},
            session,
            password="pass",
            token=None,
        )
        assert "ws://localhost:8888/" in url
        assert "Cookie" in headers

    def test_no_auth(self):
        session = FakeSession()
        url, headers = _build_ws_url(
            "http://localhost:8888",
            "kernel-123",
            {},
            session,
        )
        assert "channels" in url
        assert headers == {}

    def test_adds_trailing_slash(self):
        session = FakeSession()
        url, _ = _build_ws_url("http://host:8888", "k1", {}, session)
        assert url.startswith("ws://host:8888/")


# ---------------------------------------------------------------------------
# Tests for daemon lifecycle
# ---------------------------------------------------------------------------


class TestListDaemons:
    """Tests for the list_daemons function."""

    def setup_method(self):
        _active_daemons.clear()

    def test_empty(self):
        assert list_daemons() == []

    def test_list_all(self):
        _active_daemons["d1"] = DaemonInfo(
            daemon_id="d1", task=MagicMock(), kernel_id="k1",
            user_id="u1", chat_id="c1", message_id="m1",
        )
        _active_daemons["d2"] = DaemonInfo(
            daemon_id="d2", task=MagicMock(), kernel_id="k2",
            user_id="u2", chat_id="c2", message_id="m2",
        )
        result = list_daemons()
        assert len(result) == 2

    def test_filter_by_user(self):
        _active_daemons["d1"] = DaemonInfo(
            daemon_id="d1", task=MagicMock(), kernel_id="k1",
            user_id="u1", chat_id="c1", message_id="m1",
        )
        _active_daemons["d2"] = DaemonInfo(
            daemon_id="d2", task=MagicMock(), kernel_id="k2",
            user_id="u2", chat_id="c2", message_id="m2",
        )
        result = list_daemons(user_id="u1")
        assert len(result) == 1
        assert result[0]["daemon_id"] == "d1"

    def test_filter_by_chat(self):
        _active_daemons["d1"] = DaemonInfo(
            daemon_id="d1", task=MagicMock(), kernel_id="k1",
            user_id="u1", chat_id="chat-a", message_id="m1",
        )
        _active_daemons["d2"] = DaemonInfo(
            daemon_id="d2", task=MagicMock(), kernel_id="k2",
            user_id="u1", chat_id="chat-b", message_id="m2",
        )
        result = list_daemons(chat_id="chat-a")
        assert len(result) == 1
        assert result[0]["chat_id"] == "chat-a"

    def test_filter_by_user_and_chat(self):
        _active_daemons["d1"] = DaemonInfo(
            daemon_id="d1", task=MagicMock(), kernel_id="k1",
            user_id="u1", chat_id="chat-a", message_id="m1",
        )
        _active_daemons["d2"] = DaemonInfo(
            daemon_id="d2", task=MagicMock(), kernel_id="k2",
            user_id="u2", chat_id="chat-a", message_id="m2",
        )
        result = list_daemons(user_id="u1", chat_id="chat-a")
        assert len(result) == 1
        assert result[0]["user_id"] == "u1"

    def test_returned_dict_shape(self):
        _active_daemons["d1"] = DaemonInfo(
            daemon_id="d1", task=MagicMock(), kernel_id="k1",
            user_id="u1", chat_id="c1", message_id="m1",
        )
        result = list_daemons()
        d = result[0]
        expected_keys = {
            "daemon_id", "kernel_id", "user_id", "chat_id",
            "message_id", "started_at", "status",
        }
        assert set(d.keys()) == expected_keys


@pytest.mark.asyncio
class TestStopDaemon:
    """Tests for the stop_daemon function."""

    def setup_method(self):
        _active_daemons.clear()

    async def test_stop_nonexistent(self):
        result = await stop_daemon("nonexistent")
        assert result is False

    async def test_stop_running_daemon(self):
        task = AsyncMock()
        task.cancel = MagicMock()
        _active_daemons["d1"] = DaemonInfo(
            daemon_id="d1", task=task, kernel_id="k1",
            user_id="u1", chat_id="c1", message_id="m1", status="running",
        )
        result = await stop_daemon("d1")
        assert result is True
        assert _active_daemons["d1"].status == "stopped"
        task.cancel.assert_called_once()

    async def test_stop_already_stopped(self):
        task = AsyncMock()
        task.cancel = MagicMock()
        _active_daemons["d1"] = DaemonInfo(
            daemon_id="d1", task=task, kernel_id="k1",
            user_id="u1", chat_id="c1", message_id="m1", status="stopped",
        )
        result = await stop_daemon("d1")
        assert result is True
        task.cancel.assert_not_called()


@pytest.mark.asyncio
class TestCleanupUserDaemons:
    """Tests for the cleanup_user_daemons function."""

    def setup_method(self):
        _active_daemons.clear()

    async def test_cleanup_no_daemons(self):
        count = await cleanup_user_daemons("u1")
        assert count == 0

    async def test_cleanup_stops_only_user_running_daemons(self):
        task1 = AsyncMock()
        task1.cancel = MagicMock()
        task2 = AsyncMock()
        task2.cancel = MagicMock()
        task3 = AsyncMock()
        task3.cancel = MagicMock()

        _active_daemons["d1"] = DaemonInfo(
            daemon_id="d1", task=task1, kernel_id="k1",
            user_id="u1", chat_id="c1", message_id="m1", status="running",
        )
        _active_daemons["d2"] = DaemonInfo(
            daemon_id="d2", task=task2, kernel_id="k2",
            user_id="u1", chat_id="c2", message_id="m2", status="stopped",
        )
        _active_daemons["d3"] = DaemonInfo(
            daemon_id="d3", task=task3, kernel_id="k3",
            user_id="u2", chat_id="c3", message_id="m3", status="running",
        )

        count = await cleanup_user_daemons("u1")
        assert count == 1
        task1.cancel.assert_called_once()
        task2.cancel.assert_not_called()
        task3.cancel.assert_not_called()


# ---------------------------------------------------------------------------
# Tests for _emit_output and _emit_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestEmitFunctions:
    """Tests for the Socket.IO emission helpers."""

    async def test_emit_output(self):
        emitter = AsyncMock()
        info = DaemonInfo(
            daemon_id="d1", task=MagicMock(), kernel_id="k1",
            user_id="u1", chat_id="c1", message_id="m1",
        )
        await _emit_output(emitter, "d1", info, "stdout", "hello world")

        emitter.assert_called_once()
        call_data = emitter.call_args[0][0]
        assert call_data["type"] == "daemon:output"
        assert call_data["data"]["daemon_id"] == "d1"
        assert call_data["data"]["stream"] == "stdout"
        assert call_data["data"]["content"] == "hello world"
        assert call_data["data"]["chat_id"] == "c1"
        assert call_data["data"]["message_id"] == "m1"
        assert "timestamp" in call_data["data"]

    async def test_emit_status(self):
        emitter = AsyncMock()
        info = DaemonInfo(
            daemon_id="d1", task=MagicMock(), kernel_id="k1",
            user_id="u1", chat_id="c1", message_id="m1",
        )
        await _emit_status(emitter, "d1", info, "completed", "Script finished")

        emitter.assert_called_once()
        call_data = emitter.call_args[0][0]
        assert call_data["type"] == "daemon:status"
        assert call_data["data"]["status"] == "completed"
        assert call_data["data"]["reason"] == "Script finished"

    async def test_emit_with_none_emitter(self):
        # Should not raise
        await _emit_output(None, "d1", None, "stdout", "text")
        await _emit_status(None, "d1", None, "running")

    async def test_emit_with_none_info(self):
        emitter = AsyncMock()
        await _emit_output(emitter, "d1", None, "stdout", "text")
        call_data = emitter.call_args[0][0]
        assert call_data["data"]["chat_id"] == ""
        assert call_data["data"]["message_id"] == ""

    async def test_emit_swallows_exceptions(self):
        emitter = AsyncMock(side_effect=Exception("emit failed"))
        # Should not raise
        await _emit_output(emitter, "d1", None, "stdout", "text")
        await _emit_status(emitter, "d1", None, "running")


# ---------------------------------------------------------------------------
# Integration tests for _run_daemon
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRunDaemon:
    """Integration tests that exercise the full daemon loop with fake WS."""

    def setup_method(self):
        _active_daemons.clear()

    async def test_streams_stdout_then_completes(self):
        """Daemon streams stdout, then kernel goes idle, daemon completes."""
        emitter = AsyncMock()
        session = FakeSession()
        daemon_id = "test-daemon"
        msg_id = "will-be-replaced"  # _run_daemon generates its own

        # We need to intercept the msg_id the daemon generates.
        # We'll use a FakeWebSocket that captures the execute_request and
        # uses that msg_id for subsequent messages.
        class AdaptiveWS(FakeWebSocket):
            async def send(self, data):
                parsed = json.loads(data)
                self._sent.append(parsed)
                real_msg_id = parsed["header"]["msg_id"]
                # Replace msg_id in queued messages
                updated = []
                for m in self._messages:
                    d = json.loads(m)
                    d["parent_header"]["msg_id"] = real_msg_id
                    updated.append(json.dumps(d))
                self._messages = updated

        ws = AdaptiveWS([
            _make_stream("Hello from daemon\n"),
            _make_stream("Line 2\n"),
            _make_status_idle(),
        ])

        info = DaemonInfo(
            daemon_id=daemon_id, task=MagicMock(), kernel_id="k1",
            user_id="u1", chat_id="c1", message_id="m1",
        )
        _active_daemons[daemon_id] = info

        with patch("open_webui.utils.daemon_executor.websockets.connect") as mock_connect:
            mock_connect.return_value = ws
            await _run_daemon(
                daemon_id=daemon_id,
                session=session,
                params={},
                kernel_id="k1",
                websocket_url="ws://fake/channels",
                ws_headers={},
                code="print('hello')",
                event_emitter=emitter,
                max_runtime=60,
            )

        # Verify execute_request was sent
        assert len(ws._sent) == 1
        assert ws._sent[0]["header"]["msg_type"] == "execute_request"
        assert ws._sent[0]["content"]["code"] == "print('hello')"

        # Verify emitter was called with output events
        output_calls = [
            c for c in emitter.call_args_list
            if c[0][0].get("type") == "daemon:output"
        ]
        assert len(output_calls) == 2
        assert output_calls[0][0][0]["data"]["content"] == "Hello from daemon\n"
        assert output_calls[1][0][0]["data"]["content"] == "Line 2\n"

        # Verify completion status was emitted
        status_calls = [
            c for c in emitter.call_args_list
            if c[0][0].get("type") == "daemon:status"
        ]
        completed = [c for c in status_calls if c[0][0]["data"]["status"] == "completed"]
        assert len(completed) == 1

        # Verify kernel was deleted and session closed
        assert len(session._deleted_kernels) == 1
        assert session._closed

        # Verify daemon was removed from active list
        assert daemon_id not in _active_daemons

    async def test_error_message_stops_daemon(self):
        """Kernel error message causes daemon to stop with error status."""
        emitter = AsyncMock()
        session = FakeSession()
        daemon_id = "err-daemon"

        class AdaptiveWS(FakeWebSocket):
            async def send(self, data):
                parsed = json.loads(data)
                self._sent.append(parsed)
                real_msg_id = parsed["header"]["msg_id"]
                updated = []
                for m in self._messages:
                    d = json.loads(m)
                    d["parent_header"]["msg_id"] = real_msg_id
                    updated.append(json.dumps(d))
                self._messages = updated

        ws = AdaptiveWS([
            _make_error(["Traceback:", "  ZeroDivisionError: division by zero"]),
        ])

        info = DaemonInfo(
            daemon_id=daemon_id, task=MagicMock(), kernel_id="k1",
            user_id="u1", chat_id="c1", message_id="m1",
        )
        _active_daemons[daemon_id] = info

        with patch("open_webui.utils.daemon_executor.websockets.connect") as mock_connect:
            mock_connect.return_value = ws
            await _run_daemon(
                daemon_id=daemon_id,
                session=session,
                params={},
                kernel_id="k1",
                websocket_url="ws://fake",
                ws_headers={},
                code="1/0",
                event_emitter=emitter,
                max_runtime=60,
            )

        # Verify error was emitted
        output_calls = [
            c for c in emitter.call_args_list
            if c[0][0].get("type") == "daemon:output"
        ]
        assert len(output_calls) >= 1
        error_text = output_calls[0][0][0]["data"]["content"]
        assert "ZeroDivisionError" in error_text

        # Verify error status was emitted
        status_calls = [
            c for c in emitter.call_args_list
            if c[0][0].get("type") == "daemon:status"
        ]
        error_status = [c for c in status_calls if c[0][0]["data"]["status"] == "error"]
        assert len(error_status) == 1

    async def test_cancellation_cleans_up(self):
        """Cancelling a daemon task cleans up kernel and session."""
        emitter = AsyncMock()
        session = FakeSession()
        daemon_id = "cancel-daemon"

        class HangingWS(FakeWebSocket):
            async def send(self, data):
                parsed = json.loads(data)
                self._sent.append(parsed)

            async def recv(self):
                await asyncio.sleep(3600)

        ws = HangingWS([])

        info = DaemonInfo(
            daemon_id=daemon_id, task=MagicMock(), kernel_id="k1",
            user_id="u1", chat_id="c1", message_id="m1",
        )
        _active_daemons[daemon_id] = info

        with patch("open_webui.utils.daemon_executor.websockets.connect") as mock_connect:
            mock_connect.return_value = ws

            task = asyncio.create_task(
                _run_daemon(
                    daemon_id=daemon_id,
                    session=session,
                    params={},
                    kernel_id="k1",
                    websocket_url="ws://fake",
                    ws_headers={},
                    code="import time; time.sleep(9999)",
                    event_emitter=emitter,
                    max_runtime=3600,
                )
            )

            # Let the task start and enter the recv loop
            await asyncio.sleep(0.05)

            # Cancel it
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Verify cleanup happened
        assert session._closed
        assert len(session._deleted_kernels) == 1
        assert daemon_id not in _active_daemons

    async def test_execute_result_emits_stdout(self):
        """execute_result message type is emitted as stdout."""
        emitter = AsyncMock()
        session = FakeSession()
        daemon_id = "result-daemon"

        class AdaptiveWS(FakeWebSocket):
            async def send(self, data):
                parsed = json.loads(data)
                self._sent.append(parsed)
                real_msg_id = parsed["header"]["msg_id"]
                updated = []
                for m in self._messages:
                    d = json.loads(m)
                    d["parent_header"]["msg_id"] = real_msg_id
                    updated.append(json.dumps(d))
                self._messages = updated

        ws = AdaptiveWS([
            _make_execute_result({"text/plain": "42"}),
            _make_status_idle(),
        ])

        info = DaemonInfo(
            daemon_id=daemon_id, task=MagicMock(), kernel_id="k1",
            user_id="u1", chat_id="c1", message_id="m1",
        )
        _active_daemons[daemon_id] = info

        with patch("open_webui.utils.daemon_executor.websockets.connect") as mock_connect:
            mock_connect.return_value = ws
            await _run_daemon(
                daemon_id=daemon_id,
                session=session,
                params={},
                kernel_id="k1",
                websocket_url="ws://fake",
                ws_headers={},
                code="2+2",
                event_emitter=emitter,
                max_runtime=60,
            )

        output_calls = [
            c for c in emitter.call_args_list
            if c[0][0].get("type") == "daemon:output"
        ]
        assert any(c[0][0]["data"]["content"] == "42" for c in output_calls)

    async def test_max_runtime_exceeded(self):
        """Daemon stops when max runtime is exceeded."""
        emitter = AsyncMock()
        session = FakeSession()
        daemon_id = "timeout-daemon"

        class SlowWS(FakeWebSocket):
            async def send(self, data):
                parsed = json.loads(data)
                self._sent.append(parsed)

            async def recv(self):
                # Simulate timeout by raising TimeoutError
                raise asyncio.TimeoutError()

        ws = SlowWS([])

        info = DaemonInfo(
            daemon_id=daemon_id, task=MagicMock(), kernel_id="k1",
            user_id="u1", chat_id="c1", message_id="m1",
        )
        _active_daemons[daemon_id] = info

        with patch("open_webui.utils.daemon_executor.websockets.connect") as mock_connect:
            mock_connect.return_value = ws
            # Use max_runtime=0 to trigger immediate timeout
            await _run_daemon(
                daemon_id=daemon_id,
                session=session,
                params={},
                kernel_id="k1",
                websocket_url="ws://fake",
                ws_headers={},
                code="while True: pass",
                event_emitter=emitter,
                max_runtime=0,
            )

        # Verify timeout message was emitted
        output_calls = [
            c for c in emitter.call_args_list
            if c[0][0].get("type") == "daemon:output"
        ]
        assert any("exceeded max runtime" in c[0][0]["data"]["content"] for c in output_calls)

    async def test_mcp_session_cleanup_on_stop(self):
        """MCP session is unregistered when daemon finishes."""
        emitter = AsyncMock()
        session = FakeSession()
        daemon_id = "mcp-daemon"

        class AdaptiveWS(FakeWebSocket):
            async def send(self, data):
                parsed = json.loads(data)
                self._sent.append(parsed)
                real_msg_id = parsed["header"]["msg_id"]
                updated = []
                for m in self._messages:
                    d = json.loads(m)
                    d["parent_header"]["msg_id"] = real_msg_id
                    updated.append(json.dumps(d))
                self._messages = updated

        ws = AdaptiveWS([_make_status_idle()])

        info = DaemonInfo(
            daemon_id=daemon_id, task=MagicMock(), kernel_id="k1",
            user_id="u1", chat_id="c1", message_id="m1",
            code_mode_session_id="mcp-sess-123",
        )
        _active_daemons[daemon_id] = info

        with patch("open_webui.utils.daemon_executor.websockets.connect") as mock_connect, \
             patch("open_webui.utils.daemon_executor.unregister_code_mode_session") as mock_unreg:
            mock_connect.return_value = ws
            await _run_daemon(
                daemon_id=daemon_id,
                session=session,
                params={},
                kernel_id="k1",
                websocket_url="ws://fake",
                ws_headers={},
                code="pass",
                event_emitter=emitter,
                max_runtime=60,
            )

        mock_unreg.assert_called_once_with("mcp-sess-123")

    async def test_unmatched_msg_ids_are_skipped(self):
        """Messages with non-matching msg_id are ignored."""
        emitter = AsyncMock()
        session = FakeSession()
        daemon_id = "skip-daemon"

        class AdaptiveWS(FakeWebSocket):
            async def send(self, data):
                parsed = json.loads(data)
                self._sent.append(parsed)
                real_msg_id = parsed["header"]["msg_id"]
                # First message has wrong msg_id, second has right one
                self._messages = [
                    _make_stream("should-skip", msg_id="wrong-id"),
                    json.dumps({
                        "parent_header": {"msg_id": real_msg_id},
                        "msg_type": "stream",
                        "content": {"name": "stdout", "text": "visible\n"},
                    }),
                    json.dumps({
                        "parent_header": {"msg_id": real_msg_id},
                        "msg_type": "status",
                        "content": {"execution_state": "idle"},
                    }),
                ]

        ws = AdaptiveWS([])

        info = DaemonInfo(
            daemon_id=daemon_id, task=MagicMock(), kernel_id="k1",
            user_id="u1", chat_id="c1", message_id="m1",
        )
        _active_daemons[daemon_id] = info

        with patch("open_webui.utils.daemon_executor.websockets.connect") as mock_connect:
            mock_connect.return_value = ws
            await _run_daemon(
                daemon_id=daemon_id,
                session=session,
                params={},
                kernel_id="k1",
                websocket_url="ws://fake",
                ws_headers={},
                code="print('visible')",
                event_emitter=emitter,
                max_runtime=60,
            )

        output_calls = [
            c for c in emitter.call_args_list
            if c[0][0].get("type") == "daemon:output"
        ]
        # Only the "visible" message should be emitted, not "should-skip"
        assert len(output_calls) == 1
        assert output_calls[0][0][0]["data"]["content"] == "visible\n"

    async def test_stderr_stream(self):
        """stderr stream messages are emitted with stream='stderr'."""
        emitter = AsyncMock()
        session = FakeSession()
        daemon_id = "stderr-daemon"

        class AdaptiveWS(FakeWebSocket):
            async def send(self, data):
                parsed = json.loads(data)
                self._sent.append(parsed)
                real_msg_id = parsed["header"]["msg_id"]
                updated = []
                for m in self._messages:
                    d = json.loads(m)
                    d["parent_header"]["msg_id"] = real_msg_id
                    updated.append(json.dumps(d))
                self._messages = updated

        ws = AdaptiveWS([
            _make_stream("warning: something\n", name="stderr"),
            _make_status_idle(),
        ])

        info = DaemonInfo(
            daemon_id=daemon_id, task=MagicMock(), kernel_id="k1",
            user_id="u1", chat_id="c1", message_id="m1",
        )
        _active_daemons[daemon_id] = info

        with patch("open_webui.utils.daemon_executor.websockets.connect") as mock_connect:
            mock_connect.return_value = ws
            await _run_daemon(
                daemon_id=daemon_id,
                session=session,
                params={},
                kernel_id="k1",
                websocket_url="ws://fake",
                ws_headers={},
                code="import warnings; warnings.warn('something')",
                event_emitter=emitter,
                max_runtime=60,
            )

        output_calls = [
            c for c in emitter.call_args_list
            if c[0][0].get("type") == "daemon:output"
        ]
        assert any(c[0][0]["data"]["stream"] == "stderr" for c in output_calls)


# ---------------------------------------------------------------------------
# Integration tests for start_daemon (end-to-end with mocked Jupyter)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestStartDaemon:
    """Tests for the start_daemon entry point."""

    def setup_method(self):
        _active_daemons.clear()

    async def test_start_creates_daemon(self):
        """start_daemon returns a daemon_id and registers it."""
        emitter = AsyncMock()

        with patch("open_webui.utils.daemon_executor._create_jupyter_session") as mock_create, \
             patch("open_webui.utils.daemon_executor._build_ws_url") as mock_build, \
             patch("open_webui.utils.daemon_executor._run_daemon") as mock_run:

            mock_session = FakeSession()
            mock_create.return_value = (mock_session, {"token": "t"}, "k1")
            mock_build.return_value = ("ws://fake", {})
            mock_run.return_value = None

            daemon_id = await start_daemon(
                base_url="http://jupyter:8888",
                code="print('bg')",
                token="mytoken",
                password=None,
                user_id="u1",
                chat_id="c1",
                message_id="m1",
                event_emitter=emitter,
            )

        assert daemon_id is not None
        assert len(daemon_id) > 0
        assert daemon_id in _active_daemons
        info = _active_daemons[daemon_id]
        assert info.user_id == "u1"
        assert info.chat_id == "c1"
        assert info.kernel_id == "k1"

    async def test_per_user_limit_enforced(self):
        """Starting more than MAX_DAEMONS_PER_USER raises RuntimeError."""
        # Fill up daemons for user "u1"
        for i in range(MAX_DAEMONS_PER_USER):
            _active_daemons[f"d{i}"] = DaemonInfo(
                daemon_id=f"d{i}", task=MagicMock(), kernel_id=f"k{i}",
                user_id="u1", chat_id="c1", message_id=f"m{i}",
                status="running",
            )

        with pytest.raises(RuntimeError, match="Maximum concurrent"):
            await start_daemon(
                base_url="http://jupyter:8888",
                code="print('too many')",
                token="t",
                password=None,
                user_id="u1",
                chat_id="c1",
                message_id="mx",
                event_emitter=AsyncMock(),
            )

    async def test_different_user_not_limited(self):
        """Different user can start daemons even when u1 is at limit."""
        for i in range(MAX_DAEMONS_PER_USER):
            _active_daemons[f"d{i}"] = DaemonInfo(
                daemon_id=f"d{i}", task=MagicMock(), kernel_id=f"k{i}",
                user_id="u1", chat_id="c1", message_id=f"m{i}",
                status="running",
            )

        with patch("open_webui.utils.daemon_executor._create_jupyter_session") as mock_create, \
             patch("open_webui.utils.daemon_executor._build_ws_url") as mock_build, \
             patch("open_webui.utils.daemon_executor._run_daemon") as mock_run:

            mock_create.return_value = (FakeSession(), {}, "k99")
            mock_build.return_value = ("ws://fake", {})
            mock_run.return_value = None

            daemon_id = await start_daemon(
                base_url="http://jupyter:8888",
                code="pass",
                token="t",
                password=None,
                user_id="u2",
                chat_id="c2",
                message_id="m99",
                event_emitter=AsyncMock(),
            )

        assert daemon_id in _active_daemons

    async def test_code_mode_session_id_stored(self):
        """code_mode_session_id is stored in DaemonInfo."""
        with patch("open_webui.utils.daemon_executor._create_jupyter_session") as mock_create, \
             patch("open_webui.utils.daemon_executor._build_ws_url") as mock_build, \
             patch("open_webui.utils.daemon_executor._run_daemon") as mock_run:

            mock_create.return_value = (FakeSession(), {}, "k1")
            mock_build.return_value = ("ws://fake", {})
            mock_run.return_value = None

            daemon_id = await start_daemon(
                base_url="http://jupyter:8888",
                code="pass",
                token="t",
                password=None,
                user_id="u1",
                chat_id="c1",
                message_id="m1",
                event_emitter=AsyncMock(),
                code_mode_session_id="mcp-sess-456",
            )

        assert _active_daemons[daemon_id].code_mode_session_id == "mcp-sess-456"


# ---------------------------------------------------------------------------
# REST API endpoint tests
# ---------------------------------------------------------------------------


class TestDaemonRESTEndpoints:
    """Integration tests for the daemon REST API endpoints."""

    @pytest.fixture
    def client(self):
        from open_webui.main import app
        return TestClient(app)

    def setup_method(self):
        _active_daemons.clear()

    def test_list_daemons_empty(self, client):
        """GET /api/v1/daemons returns empty list when no daemons."""
        from test.util.mock_user import mock_webui_user

        with mock_webui_user(id="u1"):
            response = client.get("/api/v1/daemons")

        assert response.status_code == 200
        assert response.json() == []

    def test_list_daemons_filters_by_user(self, client):
        """GET /api/v1/daemons only returns current user's daemons."""
        from test.util.mock_user import mock_webui_user

        _active_daemons["d1"] = DaemonInfo(
            daemon_id="d1", task=MagicMock(), kernel_id="k1",
            user_id="u1", chat_id="c1", message_id="m1",
        )
        _active_daemons["d2"] = DaemonInfo(
            daemon_id="d2", task=MagicMock(), kernel_id="k2",
            user_id="u2", chat_id="c2", message_id="m2",
        )

        with mock_webui_user(id="u1"):
            response = client.get("/api/v1/daemons")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["daemon_id"] == "d1"

    def test_list_daemons_with_chat_filter(self, client):
        """GET /api/v1/daemons?chat_id=... filters by chat."""
        from test.util.mock_user import mock_webui_user

        _active_daemons["d1"] = DaemonInfo(
            daemon_id="d1", task=MagicMock(), kernel_id="k1",
            user_id="u1", chat_id="chat-a", message_id="m1",
        )
        _active_daemons["d2"] = DaemonInfo(
            daemon_id="d2", task=MagicMock(), kernel_id="k2",
            user_id="u1", chat_id="chat-b", message_id="m2",
        )

        with mock_webui_user(id="u1"):
            response = client.get("/api/v1/daemons?chat_id=chat-a")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["chat_id"] == "chat-a"

    def test_stop_daemon_success(self, client):
        """POST /api/v1/daemons/{id}/stop stops a running daemon."""
        from test.util.mock_user import mock_webui_user

        task = MagicMock()
        task.cancel = MagicMock()
        task.__await__ = MagicMock(return_value=iter([]))
        _active_daemons["d1"] = DaemonInfo(
            daemon_id="d1", task=task, kernel_id="k1",
            user_id="u1", chat_id="c1", message_id="m1", status="running",
        )

        with mock_webui_user(id="u1"):
            response = client.post("/api/v1/daemons/d1/stop")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "stopped"
        assert data["daemon_id"] == "d1"

    def test_stop_daemon_not_found_non_admin(self, client):
        """POST /api/v1/daemons/{id}/stop returns 403 for nonexistent (non-admin user)."""
        from test.util.mock_user import mock_webui_user

        with mock_webui_user(id="u1", role="user"):
            response = client.post("/api/v1/daemons/nonexistent/stop")

        # Non-admin user doesn't own it, so gets 403 before 404
        assert response.status_code == 403

    def test_stop_daemon_not_found_admin(self, client):
        """POST /api/v1/daemons/{id}/stop returns 404 when admin stops nonexistent."""
        from test.util.mock_user import mock_webui_user

        with mock_webui_user(id="u1", role="admin"):
            response = client.post("/api/v1/daemons/nonexistent/stop")

        assert response.status_code == 404

    def test_stop_daemon_unauthorized(self, client):
        """POST /api/v1/daemons/{id}/stop returns 403 for other user's daemon."""
        from test.util.mock_user import mock_webui_user

        _active_daemons["d1"] = DaemonInfo(
            daemon_id="d1", task=MagicMock(), kernel_id="k1",
            user_id="u2", chat_id="c1", message_id="m1",
        )

        with mock_webui_user(id="u1", role="user"):
            response = client.post("/api/v1/daemons/d1/stop")

        assert response.status_code == 403

    def test_stop_daemon_admin_can_stop_any(self, client):
        """Admin users can stop any daemon."""
        from test.util.mock_user import mock_webui_user

        task = MagicMock()
        task.cancel = MagicMock()
        task.__await__ = MagicMock(return_value=iter([]))
        _active_daemons["d1"] = DaemonInfo(
            daemon_id="d1", task=task, kernel_id="k1",
            user_id="u2", chat_id="c1", message_id="m1", status="running",
        )

        with mock_webui_user(id="u1", role="admin"):
            response = client.post("/api/v1/daemons/d1/stop")

        assert response.status_code == 200

    def test_stop_chat_daemons(self, client):
        """POST /api/v1/daemons/chat/{chat_id}/stop stops all chat daemons."""
        from test.util.mock_user import mock_webui_user

        for i in range(3):
            task = MagicMock()
            task.cancel = MagicMock()
            task.__await__ = MagicMock(return_value=iter([]))
            _active_daemons[f"d{i}"] = DaemonInfo(
                daemon_id=f"d{i}", task=task, kernel_id=f"k{i}",
                user_id="u1", chat_id="target-chat", message_id=f"m{i}",
                status="running",
            )

        # Also add a daemon in a different chat
        _active_daemons["d-other"] = DaemonInfo(
            daemon_id="d-other", task=MagicMock(), kernel_id="k-other",
            user_id="u1", chat_id="other-chat", message_id="m-other",
            status="running",
        )

        with mock_webui_user(id="u1"):
            response = client.post("/api/v1/daemons/chat/target-chat/stop")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 3

    def test_stop_chat_daemons_empty(self, client):
        """POST /api/v1/daemons/chat/{chat_id}/stop returns count=0 when none."""
        from test.util.mock_user import mock_webui_user

        with mock_webui_user(id="u1"):
            response = client.post("/api/v1/daemons/chat/no-such-chat/stop")

        assert response.status_code == 200
        assert response.json()["count"] == 0


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


class TestDaemonConfig:
    """Tests that daemon config is properly registered."""

    def test_config_exists(self):
        from open_webui.config import CODE_INTERPRETER_DAEMON_MAX_RUNTIME

        # Should be a PersistentConfig with default 3600
        assert CODE_INTERPRETER_DAEMON_MAX_RUNTIME is not None

    def test_config_on_app_state(self):
        from open_webui.main import app

        assert hasattr(app.state.config, "CODE_INTERPRETER_DAEMON_MAX_RUNTIME")
