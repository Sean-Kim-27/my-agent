"""Stdio subprocess transport speaking MCP JSON-RPC 2.0 over stdin/stdout.

The transport does not depend on the official MCP SDK. It implements the
subset used by the framework: ``initialize``, ``tools/list``, ``tools/call``,
and the ``notifications/initialized`` post-handshake notification. Messages
are newline-delimited JSON objects.

Subprocess environment is built from an explicit ``env_allowlist`` — no host
env leaks into the child unless the operator listed it.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
from typing import Any

from agent_framework.logging.logger import get_logger
from agent_framework.mcp.env import build_child_env
from agent_framework.mcp.errors import (
    MCPConnectionError,
    MCPProtocolError,
    MCPToolError,
)
from agent_framework.mcp.protocol import protocol_version
from agent_framework.mcp.transport import MCPToolInfo

logger = get_logger("agent_framework.mcp.stdio")


class StdioSubprocessTransport:
    """MCP transport that spawns a JSON-RPC server as a subprocess."""

    def __init__(
        self,
        *,
        command: list[str],
        env_allowlist: tuple[str, ...] = (),
        extra_env: dict[str, str] | None = None,
    ) -> None:
        if not command:
            raise ValueError("stdio transport requires a non-empty command")
        self._command = list(command)
        self._env_allowlist = env_allowlist
        self._extra_env = dict(extra_env or {})
        self._process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._next_id = 0
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------ Lifecycle

    async def connect(self, timeout: float) -> None:
        env = build_child_env(
            parent=os.environ,
            allowlist=self._env_allowlist,
            extra_env=self._extra_env,
        )
        try:
            self._process = await asyncio.create_subprocess_exec(
                *self._command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                start_new_session=os.name != "nt",
            )
        except FileNotFoundError as exc:
            raise MCPConnectionError(f"MCP command not found: {self._command[0]}") from exc
        except OSError as exc:
            raise MCPConnectionError(f"failed to spawn MCP subprocess: {exc}") from exc

        self._reader_task = asyncio.create_task(self._read_loop())
        self._stderr_task = asyncio.create_task(self._drain_stderr())

    async def initialize(self, timeout: float) -> None:
        params = {
            "protocolVersion": protocol_version(),
            "capabilities": {},
            "clientInfo": {"name": "agent-framework", "version": "0.3.0"},
        }
        await self._request("initialize", params)
        # notifications/initialized has no id and expects no response.
        await self._notify("notifications/initialized", {})

    async def list_tools(self) -> list[MCPToolInfo]:
        payload = await self._request("tools/list", {})
        raw_tools = payload.get("tools", [])
        if not isinstance(raw_tools, list):
            raise MCPProtocolError("tools/list did not return a list")
        result: list[MCPToolInfo] = []
        for entry in raw_tools:
            if not isinstance(entry, dict):
                continue
            result.append(
                MCPToolInfo(
                    name=str(entry.get("name", "")),
                    description=str(entry.get("description", "")),
                    input_schema=dict(entry.get("inputSchema") or {}),
                )
            )
        return result

    async def call_tool(
        self, name: str, arguments: dict[str, Any], timeout: float
    ) -> str:
        payload = await self._request(
            "tools/call",
            {"name": name, "arguments": arguments},
        )
        if payload.get("isError"):
            raise MCPToolError(_extract_text(payload) or "MCP tool returned error")
        return _extract_text(payload)

    async def close(self) -> None:
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):
                pass
            self._reader_task = None
        if self._stderr_task is not None:
            self._stderr_task.cancel()
            try:
                await self._stderr_task
            except (asyncio.CancelledError, Exception):
                pass
            self._stderr_task = None
        proc = self._process
        self._process = None
        if proc is not None:
            if proc.returncode is None:
                try:
                    if os.name != "nt":
                        os.killpg(proc.pid, signal.SIGTERM)
                    else:
                        proc.terminate()
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5.0)
                except TimeoutError:
                    if os.name != "nt":
                        try:
                            os.killpg(proc.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    else:
                        proc.kill()
                    await proc.wait()
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(MCPConnectionError("MCP subprocess closed"))
        self._pending.clear()

    # ------------------------------------------------------------ JSON-RPC

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if self._process is None or self._process.stdin is None:
            raise MCPConnectionError("MCP transport is not connected")
        async with self._lock:
            self._next_id += 1
            request_id = self._next_id
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        try:
            await self._write(message)
            response = await future
        finally:
            self._pending.pop(request_id, None)
        if "error" in response:
            err = response["error"] or {}
            raise MCPToolError(str(err.get("message", "MCP error")))
        result = response.get("result", {})
        if not isinstance(result, dict):
            raise MCPProtocolError(f"unexpected result type for {method}")
        return result

    async def _notify(self, method: str, params: dict[str, Any]) -> None:
        if self._process is None or self._process.stdin is None:
            raise MCPConnectionError("MCP transport is not connected")
        await self._write({"jsonrpc": "2.0", "method": method, "params": params})

    async def _write(self, message: dict[str, Any]) -> None:
        assert self._process is not None and self._process.stdin is not None
        data = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
        self._process.stdin.write(data)
        await self._process.stdin.drain()

    async def _read_loop(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        stdout = self._process.stdout
        try:
            while True:
                line = await stdout.readline()
                if not line:
                    break
                try:
                    message = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    logger.warning("MCP stdio: dropped malformed JSON frame")
                    continue
                if not isinstance(message, dict):
                    continue
                msg_id = message.get("id")
                if msg_id is None:
                    # server-side notification — ignored for now
                    continue
                fut = self._pending.get(int(msg_id))
                if fut is not None and not fut.done():
                    fut.set_result(message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("MCP stdio read loop exited: %s", exc)
            for fut in list(self._pending.values()):
                if not fut.done():
                    fut.set_exception(MCPConnectionError("MCP subprocess disconnected"))

    async def _drain_stderr(self) -> None:
        """Continuously drain server stderr so a noisy child cannot deadlock."""
        assert self._process is not None and self._process.stderr is not None
        try:
            while True:
                line = await self._process.stderr.readline()
                if not line:
                    return
                logger.debug("MCP server stderr: %s", line.decode("utf-8", errors="replace").rstrip())
        except asyncio.CancelledError:
            raise


def _extract_text(payload: dict[str, Any]) -> str:
    """Coalesce MCP tool ``content`` blocks into a single string."""
    content = payload.get("content")
    if content is None:
        return json.dumps(payload, ensure_ascii=False)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                parts.append(str(block))
                continue
            block_type = block.get("type")
            if block_type == "text":
                parts.append(str(block.get("text", "")))
            else:
                parts.append(json.dumps(block, ensure_ascii=False))
        return "\n".join(parts)
    return str(content)
