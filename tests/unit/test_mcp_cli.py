"""Managed MCP records and Streamable HTTP lifecycle coverage."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import httpx

from agent_framework.cli.app import run
from agent_framework.config.secrets import MemorySecretStore
from agent_framework.config.store import ConfigPaths
from agent_framework.mcp.http import HttpMCPTransport
from agent_framework.mcp.stdio import StdioSubprocessTransport


def _paths(root: Path) -> ConfigPaths:
    return ConfigPaths(
        user_config=root / "user" / "config.toml",
        project_config=root / "project" / "config.toml",
        data_dir=root / "data",
        cache_dir=root / "cache",
    )


def test_mcp_stdio_record_round_trips_argv_without_shell(
    tmp_path: Path, capsys: Any
) -> None:
    paths = _paths(tmp_path)
    secrets = MemorySecretStore()

    assert run(
        ["mcp", "add", "local", "--stdio", "--", "python", "server.py", "--flag"],
        paths=paths,
        secret_store=secrets,
    ) == 0
    assert run(
        ["--json", "mcp", "list"],
        paths=paths,
        secret_store=secrets,
    ) == 0

    lines = [line for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    payload = json.loads(lines[-1])
    record = payload["data"][0]
    assert record["command"] == ["python", "server.py", "--flag"]
    assert record["enabled"] is True


def test_mcp_http_record_stores_secret_reference_not_value(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    secrets = MemorySecretStore()
    secrets.set("mcp/example/token", "actual-secret")

    assert run(
        [
            "mcp",
            "add",
            "remote",
            "--http",
            "https://example.test/mcp",
            "--header-secret",
            "Authorization=mcp/example/token",
        ],
        paths=paths,
        secret_store=secrets,
    ) == 0

    text = paths.user_config.read_text(encoding="utf-8")
    assert "mcp/example/token" in text
    assert "actual-secret" not in text


async def test_http_transport_negotiates_session_and_sends_initialized() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        payload = json.loads(request.content)
        if payload["method"] == "initialize":
            return httpx.Response(
                200,
                headers={"Mcp-Session-Id": "session-123"},
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {"protocolVersion": "2024-11-05"},
                },
            )
        if payload["method"] == "notifications/initialized":
            return httpx.Response(202)
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {"tools": []},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    transport = HttpMCPTransport(url="https://example.test/mcp", client=client)
    await transport.connect(1)
    await transport.initialize(1)
    await transport.list_tools()
    await transport.close()
    await client.aclose()

    assert len(requests) == 3
    assert json.loads(requests[1].content)["method"] == "notifications/initialized"
    assert requests[1].headers["Mcp-Session-Id"] == "session-123"
    assert requests[2].headers["Mcp-Session-Id"] == "session-123"


async def test_http_transport_negotiates_new_version_and_sends_protocol_header() -> None:
    """Post-initialize requests must echo MCP-Protocol-Version when 2025-03-26+."""
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        payload = json.loads(request.content)
        if payload["method"] == "initialize":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {"protocolVersion": "2025-06-18"},
                },
            )
        if payload["method"] == "notifications/initialized":
            return httpx.Response(202)
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {"tools": []},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    transport = HttpMCPTransport(url="https://example.test/mcp", client=client)
    await transport.connect(1)
    await transport.initialize(1)
    await transport.list_tools()
    await transport.close()
    await client.aclose()

    assert transport.negotiated_version == "2025-06-18"
    # initialize predates negotiation, so no header expected there.
    assert "MCP-Protocol-Version" not in requests[0].headers
    # notifications/initialized and tools/list must include the header.
    assert requests[1].headers.get("MCP-Protocol-Version") == "2025-06-18"
    assert requests[2].headers.get("MCP-Protocol-Version") == "2025-06-18"


async def test_http_transport_rejects_unsupported_protocol_version() -> None:
    """A server picking a revision we don't speak must fail closed."""

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {"protocolVersion": "1999-01-01"},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    transport = HttpMCPTransport(url="https://example.test/mcp", client=client)
    await transport.connect(1)
    import pytest as _pytest

    from agent_framework.mcp.errors import MCPProtocolError

    with _pytest.raises(MCPProtocolError):
        await transport.initialize(1)
    await transport.close()
    await client.aclose()


async def test_real_stdio_server_connect_call_and_shutdown(tmp_path: Path) -> None:
    server = tmp_path / "server.py"
    server.write_text(
        """import json
import sys

for line in sys.stdin:
    request = json.loads(line)
    if 'id' not in request:
        continue
    method = request['method']
    if method == 'initialize':
        result = {'protocolVersion': '2024-11-05', 'capabilities': {}}
    elif method == 'tools/list':
        result = {'tools': [{'name': 'echo', 'inputSchema': {'type': 'object'}}]}
    else:
        result = {'content': [{'type': 'text', 'text': 'pong'}]}
    print(json.dumps({'jsonrpc': '2.0', 'id': request['id'], 'result': result}), flush=True)
""",
        encoding="utf-8",
    )
    transport = StdioSubprocessTransport(command=[sys.executable, str(server)])

    await transport.connect(2)
    await transport.initialize(2)
    tools = await transport.list_tools()
    result = await transport.call_tool("echo", {"value": "ping"}, 2)
    process = transport._process
    await transport.close()

    assert [tool.name for tool in tools] == ["echo"]
    assert result == "pong"
    assert process is not None and process.returncode is not None


async def test_real_streamable_http_server_connect_list_and_shutdown() -> None:
    methods: list[str] = []

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        header_bytes = await reader.readuntil(b"\r\n\r\n")
        headers = header_bytes.decode("latin-1").split("\r\n")
        content_length = next(
            int(line.split(":", 1)[1].strip())
            for line in headers
            if line.lower().startswith("content-length:")
        )
        payload = json.loads(await reader.readexactly(content_length))
        methods.append(payload["method"])
        if "id" in payload:
            if payload["method"] == "tools/list":
                result: dict[str, object] = {"tools": []}
            elif payload["method"] == "initialize":
                result = {"protocolVersion": "2024-11-05"}
            else:
                result = {}
            body = json.dumps(
                {"jsonrpc": "2.0", "id": payload["id"], "result": result}
            ).encode()
            status = "200 OK"
        else:
            body = b""
            status = "202 Accepted"
        response = (
            f"HTTP/1.1 {status}\r\nContent-Length: {len(body)}\r\n"
            "Content-Type: application/json\r\nMcp-Session-Id: live-session\r\n"
            "Connection: close\r\n\r\n"
        ).encode() + body
        writer.write(response)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    transport = HttpMCPTransport(url=f"http://127.0.0.1:{port}/mcp")
    try:
        await transport.connect(2)
        await transport.initialize(2)
        assert await transport.list_tools() == []
    finally:
        await transport.close()
        server.close()
        await server.wait_closed()

    assert methods == ["initialize", "notifications/initialized", "tools/list"]
