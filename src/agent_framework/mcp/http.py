"""Streamable HTTP MCP transport backed by httpx.

The transport speaks MCP JSON-RPC 2.0 over HTTP POST — the successor to the
older HTTP+SSE mode. Legacy SSE support is intentionally omitted; add a
separate transport if a target requires it.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from agent_framework.mcp.errors import (
    MCPConnectionError,
    MCPProtocolError,
    MCPToolError,
)
from agent_framework.mcp.stdio import _extract_text
from agent_framework.mcp.transport import MCPToolInfo

_PROTOCOL_VERSION = "2024-11-05"


class HttpMCPTransport:
    """MCP transport that POSTs JSON-RPC requests to a remote endpoint."""

    def __init__(
        self,
        *,
        url: str,
        headers: dict[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not url:
            raise ValueError("http transport requires a non-empty url")
        self._url = url
        self._headers = dict(headers or {})
        self._client = client
        self._owns_client = client is None
        self._next_id = 0

    async def connect(self, timeout: float) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(timeout))

    async def initialize(self, timeout: float) -> None:
        params = {
            "protocolVersion": _PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "agent-framework", "version": "0.3.0"},
        }
        await self._request("initialize", params, timeout=timeout)

    async def list_tools(self) -> list[MCPToolInfo]:
        payload = await self._request("tools/list", {}, timeout=None)
        raw = payload.get("tools", [])
        if not isinstance(raw, list):
            raise MCPProtocolError("tools/list did not return a list")
        result: list[MCPToolInfo] = []
        for entry in raw:
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
            timeout=timeout,
        )
        if payload.get("isError"):
            raise MCPToolError(_extract_text(payload) or "MCP tool returned error")
        return _extract_text(payload)

    async def close(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
        self._client = None

    async def _request(
        self,
        method: str,
        params: dict[str, Any],
        *,
        timeout: float | None,
    ) -> dict[str, Any]:
        if self._client is None:
            raise MCPConnectionError("HTTP MCP transport not connected")
        self._next_id += 1
        body = {
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": method,
            "params": params,
        }
        try:
            response = await self._client.post(
                self._url,
                json=body,
                headers={"Content-Type": "application/json", **self._headers},
                timeout=timeout if timeout is not None else self._client.timeout,
            )
        except httpx.TimeoutException as exc:
            raise MCPConnectionError(f"MCP HTTP request timed out: {exc}") from exc
        except httpx.HTTPError as exc:
            raise MCPConnectionError(f"MCP HTTP request failed: {exc}") from exc

        if response.status_code >= 400:
            raise MCPConnectionError(
                f"MCP HTTP {response.status_code}: {response.text[:200]}"
            )
        try:
            message = response.json()
        except json.JSONDecodeError as exc:
            raise MCPProtocolError(f"invalid JSON from MCP endpoint: {exc}") from exc

        if not isinstance(message, dict):
            raise MCPProtocolError("MCP response was not a JSON object")
        if "error" in message:
            err = message["error"] or {}
            raise MCPToolError(str(err.get("message", "MCP error")))
        result = message.get("result", {})
        if not isinstance(result, dict):
            raise MCPProtocolError(f"unexpected result type for {method}")
        return result
