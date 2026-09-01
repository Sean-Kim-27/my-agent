"""Phase 5 capability tests for the built-in web fetch tool (SSRF defenses)."""

from __future__ import annotations

import asyncio
import json
import socket
from typing import Any

import httpx
import pytest

from agent_framework.tools.builtin.web import (
    WebFetchError,
    extract_text_from_html,
    register_web_tools,
)
from agent_framework.tools.registry import ToolRegistry


def _registry_with_web() -> ToolRegistry:
    reg = ToolRegistry()
    register_web_tools(reg)
    return reg


# ---------------------------------------------------------------- SSRF checks


def test_http_fetch_rejects_non_http_scheme() -> None:
    reg = _registry_with_web()
    fn = reg.get("builtin.web.http_fetch")
    assert fn is not None
    with pytest.raises(WebFetchError):
        asyncio.run(fn(url="file:///etc/passwd"))


def test_http_fetch_rejects_loopback_ip_literal() -> None:
    reg = _registry_with_web()
    fn = reg.get("builtin.web.http_fetch")
    assert fn is not None
    with pytest.raises(WebFetchError):
        asyncio.run(fn(url="http://127.0.0.1/x"))


def test_http_fetch_rejects_cloud_metadata_endpoint() -> None:
    reg = _registry_with_web()
    fn = reg.get("builtin.web.http_fetch")
    assert fn is not None
    with pytest.raises(WebFetchError):
        asyncio.run(fn(url="http://169.254.169.254/latest/meta-data/"))


def test_http_fetch_rejects_private_ip_literal() -> None:
    reg = _registry_with_web()
    fn = reg.get("builtin.web.http_fetch")
    assert fn is not None
    with pytest.raises(WebFetchError):
        asyncio.run(fn(url="http://10.0.0.1/"))


def test_http_fetch_rejects_hostname_resolving_to_private_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_getaddrinfo(host: str, *_: Any, **__: Any) -> list[tuple[Any, ...]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("192.168.1.10", 0))]

    monkeypatch.setattr(
        "agent_framework.tools.builtin.web.socket.getaddrinfo", fake_getaddrinfo
    )
    reg = _registry_with_web()
    fn = reg.get("builtin.web.http_fetch")
    assert fn is not None
    with pytest.raises(WebFetchError):
        asyncio.run(fn(url="http://internal.example.com/"))


# ---------------------------------------------------------------- Happy path


def _install_public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_getaddrinfo(host: str, *_: Any, **__: Any) -> list[tuple[Any, ...]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(
        "agent_framework.tools.builtin.web.socket.getaddrinfo", fake_getaddrinfo
    )


def test_http_fetch_success_with_stubbed_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_public_dns(monkeypatch)

    body = b"<html><body><p>hello</p></body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body, headers={"content-type": "text/html"})

    transport = httpx.MockTransport(handler)

    def fake_transport(*_: Any, **__: Any) -> httpx.MockTransport:
        return transport

    monkeypatch.setattr(
        "agent_framework.tools.builtin.web.httpx.AsyncHTTPTransport", fake_transport
    )

    reg = _registry_with_web()
    fn = reg.get("builtin.web.http_fetch")
    assert fn is not None
    payload = json.loads(asyncio.run(fn(url="https://example.com/hi")))
    assert payload["status_code"] == 200
    assert "hello" in payload["text"]
    assert payload["truncated"] is False


def test_http_fetch_enforces_max_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_public_dns(monkeypatch)
    body = b"A" * 2048

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body, headers={"content-type": "text/plain"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "agent_framework.tools.builtin.web.httpx.AsyncHTTPTransport",
        lambda *a, **k: transport,
    )

    reg = _registry_with_web()
    fn = reg.get("builtin.web.http_fetch")
    assert fn is not None
    payload = json.loads(asyncio.run(fn(url="https://example.com/big", max_bytes=100)))
    assert payload["truncated"] is True
    assert payload["total_bytes"] == 2048
    assert len(payload["text"]) == 100


def test_http_fetch_follows_public_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_public_dns(monkeypatch)

    hits: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hits.append(str(request.url))
        if len(hits) == 1:
            return httpx.Response(
                302,
                headers={"location": "https://example.com/final"},
            )
        return httpx.Response(200, content=b"OK", headers={"content-type": "text/plain"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "agent_framework.tools.builtin.web.httpx.AsyncHTTPTransport",
        lambda *a, **k: transport,
    )

    reg = _registry_with_web()
    fn = reg.get("builtin.web.http_fetch")
    assert fn is not None
    payload = json.loads(asyncio.run(fn(url="https://example.com/start")))
    assert payload["status_code"] == 200
    assert payload["text"] == "OK"
    assert len(hits) == 2


def test_http_fetch_rejects_redirect_to_private_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = {"n": 0}

    def flipping_dns(host: str, *_: Any, **__: Any) -> list[tuple[Any, ...]]:
        call_count["n"] += 1
        if host == "public.example.com":
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))]
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.5", 0))]

    monkeypatch.setattr(
        "agent_framework.tools.builtin.web.socket.getaddrinfo", flipping_dns
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://internal.corp/secret"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "agent_framework.tools.builtin.web.httpx.AsyncHTTPTransport",
        lambda *a, **k: transport,
    )

    reg = _registry_with_web()
    fn = reg.get("builtin.web.http_fetch")
    assert fn is not None
    with pytest.raises(WebFetchError):
        asyncio.run(fn(url="https://public.example.com/start"))


# ---------------------------------------------------------------- HTML extract


# ---------------------------------------------------------------- IP pinning


def test_http_fetch_rewrites_host_to_validated_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The connection must be pinned to the DNS-validated public IP.

    Simulates a TOCTOU: our DNS check returns a public IP, but if the client
    were to re-resolve at connect time it could hit a private IP. The pinned
    transport prevents that by rewriting the URL host to the validated IP
    while preserving the ``Host`` header and TLS SNI hostname.
    """

    _install_public_dns(monkeypatch)

    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url_host"] = request.url.host
        captured["host_header"] = request.headers.get("host")
        captured["sni"] = request.extensions.get("sni_hostname")
        return httpx.Response(200, content=b"pinned", headers={"content-type": "text/plain"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "agent_framework.tools.builtin.web.httpx.AsyncHTTPTransport",
        lambda *a, **k: transport,
    )

    reg = _registry_with_web()
    fn = reg.get("builtin.web.http_fetch")
    assert fn is not None
    payload = json.loads(asyncio.run(fn(url="https://example.com/pin")))
    assert payload["status_code"] == 200
    assert captured["url_host"] == "93.184.216.34"
    assert captured["host_header"] == "example.com"
    assert captured["sni"] == "example.com"


def test_http_fetch_pinning_does_not_rewrite_public_ip_literal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An http(s) URL that already uses a public IP literal must not be rewritten."""

    _install_public_dns(monkeypatch)

    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url_host"] = request.url.host
        return httpx.Response(200, content=b"ok", headers={"content-type": "text/plain"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "agent_framework.tools.builtin.web.httpx.AsyncHTTPTransport",
        lambda *a, **k: transport,
    )

    reg = _registry_with_web()
    fn = reg.get("builtin.web.http_fetch")
    assert fn is not None
    payload = json.loads(asyncio.run(fn(url="https://93.184.216.34/")))
    assert payload["status_code"] == 200
    assert captured["url_host"] == "93.184.216.34"


# ---------------------------------------------------------------- HTML extract


def test_extract_text_from_html_drops_scripts_and_styles() -> None:
    html = """
    <html><head><style>.x{color:red}</style></head>
    <body><script>alert(1)</script>
    <h1>Title</h1><p>Body text</p></body></html>
    """
    text = extract_text_from_html(html)
    assert "Title" in text
    assert "Body text" in text
    assert "alert" not in text
    assert "color:red" not in text
