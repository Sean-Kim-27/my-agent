"""HTTP fetch built-in tool with fail-closed SSRF defenses.

The tool rejects:
* non-http(s) schemes,
* URLs that resolve to private, loopback, link-local, multicast, or
  reserved addresses (including the cloud metadata endpoint
  169.254.169.254 — link-local),
* responses larger than a configurable byte cap,
* redirects that target a blocked address.

Every redirect target is resolved and checked before use. The current httpx
connection still resolves the hostname independently, so this is a best-effort
boundary rather than DNS pinning against a local TOCTOU attacker.
"""

from __future__ import annotations

import ipaddress
import json
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Final
from urllib.parse import urlsplit

import httpx

from agent_framework.models.tool import ToolRiskLevel
from agent_framework.tools.registry import ToolRegistry

DEFAULT_WEB_TIMEOUT: Final[float] = 15.0
_DEFAULT_MAX_RESPONSE_BYTES: Final[int] = 512 * 1024  # 512 KiB
_MAX_RESPONSE_BYTES_CAP: Final[int] = 4 * 1024 * 1024  # 4 MiB
_MAX_REDIRECTS: Final[int] = 3
_ALLOWED_SCHEMES: Final[frozenset[str]] = frozenset({"http", "https"})


class WebFetchError(Exception):
    """Raised when a web fetch is denied or fails."""


@dataclass(frozen=True)
class WebFetchResult:
    """Structured result from :func:`http_fetch`."""

    status_code: int
    url: str
    content_type: str
    text: str
    truncated: bool
    total_bytes: int


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Fail-closed: block anything that is not a routable public address."""
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _resolve_public_addresses(hostname: str) -> list[str]:
    """Resolve ``hostname`` and require every A/AAAA record to be public."""
    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise WebFetchError(f"DNS resolution failed for host '{hostname}': {exc}") from exc

    addresses: list[str] = []
    for info in infos:
        sockaddr = info[4]
        raw = sockaddr[0]
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError as exc:
            raise WebFetchError(
                f"DNS returned non-IP address '{raw}' for {hostname}."
            ) from exc
        if _is_blocked_ip(ip):
            raise WebFetchError(
                f"Refusing to fetch: '{hostname}' resolves to non-public address {ip}."
            )
        addresses.append(str(ip))

    if not addresses:
        raise WebFetchError(f"No usable addresses returned for host '{hostname}'.")
    # Deduplicate while preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for a in addresses:
        if a not in seen:
            seen.add(a)
            unique.append(a)
    return unique


def _validate_url(url: str) -> tuple[str, str, int]:
    """Return ``(scheme, host, port)`` after enforcing the URL policy."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise WebFetchError(f"Only http/https URLs are allowed, got '{scheme}'.")
    host = parts.hostname
    if not host:
        raise WebFetchError("URL is missing a hostname.")
    # Reject numeric IP literals that fall in blocked ranges up front.
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and _is_blocked_ip(literal):
        raise WebFetchError(f"Refusing to fetch a non-public IP literal: {host}.")

    port = parts.port or (443 if scheme == "https" else 80)
    return scheme, host, port


async def _fetch(
    url: str,
    *,
    timeout: float,
    max_bytes: int,
    max_redirects: int,
) -> WebFetchResult:
    if max_bytes <= 0:
        raise WebFetchError("max_bytes must be positive.")
    if max_bytes > _MAX_RESPONSE_BYTES_CAP:
        raise WebFetchError(
            f"max_bytes {max_bytes} exceeds the built-in cap "
            f"of {_MAX_RESPONSE_BYTES_CAP}."
        )
    if timeout <= 0:
        raise WebFetchError("timeout must be positive.")

    current_url = url
    hops = 0
    while True:
        scheme, host, _port = _validate_url(current_url)
        _resolve_public_addresses(host)  # raise if any resolved address is blocked

        transport = httpx.AsyncHTTPTransport(retries=0)
        try:
            async with httpx.AsyncClient(
                transport=transport,
                timeout=timeout,
                follow_redirects=False,
                headers={"User-Agent": "agent-framework-web-tool/1.0"},
            ) as client:
                response = await client.get(current_url)
        except httpx.HTTPError as exc:
            raise WebFetchError(f"HTTP request failed: {exc}") from exc

        if response.is_redirect:
            hops += 1
            if hops > max_redirects:
                raise WebFetchError(
                    f"Exceeded redirect limit ({max_redirects}) starting from {url}."
                )
            location = response.headers.get("location")
            if not location:
                raise WebFetchError("Redirect response missing Location header.")
            next_url = str(httpx.URL(current_url).join(location))
            current_url = next_url
            continue

        body = response.content or b""
        total_bytes = len(body)
        truncated = False
        if total_bytes > max_bytes:
            body = body[:max_bytes]
            truncated = True

        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
        # Prefer server-declared charset; fall back to utf-8 with replacement.
        encoding = response.encoding or "utf-8"
        try:
            text = body.decode(encoding, errors="replace")
        except LookupError:
            text = body.decode("utf-8", errors="replace")

        # Silence unused var
        _ = scheme

        return WebFetchResult(
            status_code=response.status_code,
            url=str(response.url),
            content_type=content_type,
            text=text,
            truncated=truncated,
            total_bytes=total_bytes,
        )


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._buf: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._buf.append(data)

    def value(self) -> str:
        joined = "".join(self._buf)
        # Collapse whitespace.
        return " ".join(joined.split())


def extract_text_from_html(html: str) -> str:
    """Extract visible text from an HTML document (best-effort, stdlib only)."""
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    return parser.value()


def register_web_tools(
    registry: ToolRegistry,
    *,
    toolset: str = "builtin.web",
    default_timeout: float = DEFAULT_WEB_TIMEOUT,
    default_max_bytes: int = _DEFAULT_MAX_RESPONSE_BYTES,
    max_redirects: int = _MAX_REDIRECTS,
) -> None:
    """Register http_fetch (and its HTML text sibling) on the registry."""

    async def http_fetch(
        url: str,
        max_bytes: int | None = None,
        timeout: float | None = None,
    ) -> str:
        """Fetch an http(s) URL with SSRF protection and size caps.

        Args:
            url: Absolute http or https URL. Private, loopback, link-local,
                multicast, and reserved addresses are rejected.
            max_bytes: Optional response size cap (default 512 KiB, max 4 MiB).
            timeout: Optional per-request timeout in seconds (default 15).
        """
        try:
            result = await _fetch(
                url,
                timeout=timeout if timeout is not None else default_timeout,
                max_bytes=max_bytes if max_bytes is not None else default_max_bytes,
                max_redirects=max_redirects,
            )
        except WebFetchError:
            raise
        return json.dumps(
            {
                "url": result.url,
                "status_code": result.status_code,
                "content_type": result.content_type,
                "truncated": result.truncated,
                "total_bytes": result.total_bytes,
                "text": result.text,
            },
            ensure_ascii=False,
        )

    async def http_fetch_text(
        url: str,
        max_bytes: int | None = None,
        timeout: float | None = None,
    ) -> str:
        """Fetch an http(s) URL and return the visible text of the HTML body.

        Args:
            url: Absolute http or https URL (same SSRF rules as http_fetch).
            max_bytes: Optional response size cap in bytes.
            timeout: Optional per-request timeout in seconds.
        """
        result = await _fetch(
            url,
            timeout=timeout if timeout is not None else default_timeout,
            max_bytes=max_bytes if max_bytes is not None else default_max_bytes,
            max_redirects=max_redirects,
        )
        text = extract_text_from_html(result.text)
        return json.dumps(
            {
                "url": result.url,
                "status_code": result.status_code,
                "content_type": result.content_type,
                "truncated": result.truncated,
                "total_bytes": result.total_bytes,
                "text": text,
            },
            ensure_ascii=False,
        )

    registry.register(
        http_fetch,
        name="builtin.web.http_fetch",
        toolset=toolset,
        risk_level=ToolRiskLevel.LOW,
        idempotent=True,
    )
    registry.register(
        http_fetch_text,
        name="builtin.web.http_fetch_text",
        toolset=toolset,
        risk_level=ToolRiskLevel.LOW,
        idempotent=True,
    )
