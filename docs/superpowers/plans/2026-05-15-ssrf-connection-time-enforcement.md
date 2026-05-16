# SSRF Connection-Time Enforcement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate DNS-rebinding TOCTOU in all direct httpx fetchers by pinning the resolved IP at connect time via a custom transport, and extend SSRF protection to the Twitter article resolver and Playwright provider.

**Architecture:** `SafeAsyncTransport` subclasses `httpx.AsyncHTTPTransport` and overrides `handle_async_request` to resolve DNS, validate every returned IP against `BLOCKED_NETWORKS`, then rewrite the request URL to the raw IP before calling `super()` — httpcore sees an IP address and never re-resolves. A matching `SafeSyncTransport` serves the RSS feed fetcher. Factory helpers `make_safe_async_client()` / `make_safe_sync_client()` are the only callsite change needed in each fetcher.

**Tech Stack:** Python 3.13, httpx, socket (stdlib), pytest-asyncio, unittest.mock

---

## File Map

| Action | Path |
|--------|------|
| Modify | `app/security/ssrf.py` |
| Create | `tests/security/test_ssrf.py` |
| Modify | `app/adapters/content/scraper/direct_html_provider.py` |
| Modify | `app/adapters/content/scraper/direct_pdf_provider.py` |
| Modify | `app/adapters/content/scraper/defuddle_provider.py` |
| Modify | `app/api/routers/proxy.py` |
| Modify | `app/adapters/rss/feed_fetcher.py` |
| Modify | `app/infrastructure/messaging/handlers/webhook_dispatcher.py` |
| Modify | `app/adapters/twitter/article_link_resolver.py` |
| Modify | `app/adapters/content/scraper/playwright_provider.py` |

---

## Task 1: Write payload tests for existing `is_ip_blocked` and `is_url_safe`

These test already-existing functions. They should **pass immediately** and establish the test file.

**Files:**
- Create: `tests/security/test_ssrf.py`

- [ ] **Step 1: Create the test file**

```python
"""Tests for SSRF protection: blocked-IP payloads, transport IP-pinning, DNS-rebinding."""

from __future__ import annotations

import socket
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from app.security.ssrf import is_ip_blocked, is_url_safe


# ---------------------------------------------------------------------------
# is_ip_blocked — individual IP payload checks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "10.0.0.1",
        "10.255.255.255",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.0.1",
        "192.168.255.255",
        "169.254.169.254",  # AWS metadata
        "100.64.0.1",  # carrier-grade NAT
        "224.0.0.1",  # multicast
        "255.255.255.255",  # broadcast
        "::1",  # IPv6 loopback
        "fe80::1",  # IPv6 link-local
        "fc00::1",  # IPv6 private
        "::ffff:127.0.0.1",  # IPv4-mapped loopback
        "::ffff:192.168.1.1",  # IPv4-mapped private
        "64:ff9b::1",  # NAT64 prefix
        "2002:c0a8:0101::",  # 6to4 wrapping 192.168.1.1
    ],
)
def test_is_ip_blocked_returns_true_for_private_addresses(ip: str) -> None:
    assert is_ip_blocked(ip) is True


def test_is_ip_blocked_returns_false_for_public_ipv4() -> None:
    assert is_ip_blocked("93.184.216.34") is False


def test_is_ip_blocked_returns_false_for_public_ipv6() -> None:
    assert is_ip_blocked("2001:db8:85a3::8a2e:370:7334") is False


def test_is_ip_blocked_returns_true_for_unparseable_input() -> None:
    # Unparseable → treated as blocked for safety
    assert is_ip_blocked("not-an-ip") is True


# ---------------------------------------------------------------------------
# is_url_safe — URL-level checks
# ---------------------------------------------------------------------------


def test_is_url_safe_blocks_localhost_name() -> None:
    safe, reason = is_url_safe("http://localhost/")
    assert safe is False
    assert reason is not None


def test_is_url_safe_blocks_ipv4_loopback_literal() -> None:
    safe, reason = is_url_safe("http://127.0.0.1/")
    assert safe is False


def test_is_url_safe_blocks_rfc1918_literal() -> None:
    safe, _ = is_url_safe("http://192.168.1.1/")
    assert safe is False


def test_is_url_safe_blocks_ipv6_loopback_literal() -> None:
    safe, _ = is_url_safe("http://[::1]/")
    assert safe is False


def test_is_url_safe_blocks_aws_metadata_ip() -> None:
    safe, _ = is_url_safe("http://169.254.169.254/latest/meta-data/")
    assert safe is False


def test_is_url_safe_blocks_ipv4_mapped_ipv6() -> None:
    safe, _ = is_url_safe("http://[::ffff:7f00:1]/")  # ::ffff:127.0.0.1
    assert safe is False


def test_is_url_safe_returns_false_on_dns_failure() -> None:
    with patch("app.security.ssrf.resolve_host_ips", side_effect=socket.gaierror("NXDOMAIN")):
        safe, reason = is_url_safe("http://does-not-exist.invalid/")
    assert safe is False


def test_is_url_safe_blocks_hostname_that_resolves_to_private(monkeypatch) -> None:
    monkeypatch.setattr("app.security.ssrf.resolve_host_ips", lambda _: ["192.168.1.1"])
    safe, reason = is_url_safe("http://evil.example.com/")
    assert safe is False
    assert "192.168.1.1" in (reason or "")
```

- [ ] **Step 2: Run tests to verify they all pass**

```bash
source .venv/bin/activate
pytest tests/security/test_ssrf.py -v --tb=short
```

Expected: all tests **PASS** (exercising existing code).

- [ ] **Step 3: Commit**

```bash
git add tests/security/test_ssrf.py
git commit -m "test(security): add SSRF payload test baseline for is_ip_blocked and is_url_safe"
```

---

## Task 2: Write failing transport tests

These test `SafeAsyncTransport` / `SafeSyncTransport` which do not exist yet. They must **FAIL**.

**Files:**
- Modify: `tests/security/test_ssrf.py`

- [ ] **Step 1: Append transport tests to `tests/security/test_ssrf.py`**

Add after the last line:

```python
# ---------------------------------------------------------------------------
# SafeAsyncTransport — IP-pinning and DNS-rebinding prevention
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_safe_async_transport_blocks_private_ip_literal() -> None:
    """Transport raises ConnectError for an IP-literal URL in a blocked range."""
    from app.security.ssrf import SafeAsyncTransport

    transport = SafeAsyncTransport()
    request = httpx.Request("GET", "http://192.168.1.1/")
    with pytest.raises(httpx.ConnectError, match="SSRF blocked"):
        await transport.handle_async_request(request)


@pytest.mark.asyncio
async def test_safe_async_transport_blocks_ipv6_loopback() -> None:
    from app.security.ssrf import SafeAsyncTransport

    transport = SafeAsyncTransport()
    request = httpx.Request("GET", "http://[::1]/")
    with pytest.raises(httpx.ConnectError, match="SSRF blocked"):
        await transport.handle_async_request(request)


@pytest.mark.asyncio
async def test_safe_async_transport_blocks_aws_metadata() -> None:
    from app.security.ssrf import SafeAsyncTransport

    transport = SafeAsyncTransport()
    request = httpx.Request("GET", "http://169.254.169.254/latest/meta-data/")
    with pytest.raises(httpx.ConnectError, match="SSRF blocked"):
        await transport.handle_async_request(request)


@pytest.mark.asyncio
async def test_safe_async_transport_blocks_non_http_scheme() -> None:
    from app.security.ssrf import SafeAsyncTransport

    transport = SafeAsyncTransport()
    request = httpx.Request("GET", "ftp://example.com/")
    with pytest.raises(httpx.ConnectError, match="Blocked scheme"):
        await transport.handle_async_request(request)


@pytest.mark.asyncio
async def test_safe_async_transport_blocks_if_any_resolved_ip_is_private() -> None:
    """All resolved IPs are checked — one private IP poisons the whole response."""
    from app.security.ssrf import SafeAsyncTransport

    transport = SafeAsyncTransport()
    request = httpx.Request("GET", "http://example.com/")

    def fake_getaddrinfo(host: str, port: Any, **_: Any) -> list[Any]:
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("8.8.8.8", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("192.168.1.1", port)),
        ]

    with patch("app.security.ssrf.socket.getaddrinfo", side_effect=fake_getaddrinfo):
        with pytest.raises(httpx.ConnectError, match="SSRF blocked"):
            await transport.handle_async_request(request)


@pytest.mark.asyncio
async def test_safe_async_transport_dns_rebinding_blocked() -> None:
    """Simulates DNS rebinding: transport resolves private IP at connect time and blocks it.

    Before this transport existed, a preflight check would pass (public IP on first
    lookup) and httpcore would re-resolve to a private IP at connect time.  The
    transport closes that window by being the resolver.
    """
    from app.security.ssrf import SafeAsyncTransport

    call_count = 0

    def rebinding_getaddrinfo(host: str, port: Any, **_: Any) -> list[Any]:
        nonlocal call_count
        call_count += 1
        # Simulate rebinding: always returns the private IP when the transport calls it
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.1", port))]

    transport = SafeAsyncTransport()
    request = httpx.Request("GET", "http://rebind.example.com/")

    with patch("app.security.ssrf.socket.getaddrinfo", side_effect=rebinding_getaddrinfo):
        with pytest.raises(httpx.ConnectError, match="SSRF blocked"):
            await transport.handle_async_request(request)


@pytest.mark.asyncio
async def test_safe_async_transport_pins_ip_in_forwarded_request() -> None:
    """Transport rewrites URL host to the resolved IP before calling super()."""
    from app.security.ssrf import SafeAsyncTransport

    captured: dict[str, Any] = {}

    async def fake_super(request: httpx.Request) -> httpx.Response:
        captured["url_host"] = request.url.host
        captured["host_header"] = request.headers.get("host")
        return httpx.Response(200, content=b"ok")

    def fake_getaddrinfo(host: str, port: Any, **_: Any) -> list[Any]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", port))]

    transport = SafeAsyncTransport()
    request = httpx.Request("GET", "http://example.com/")

    with patch("app.security.ssrf.socket.getaddrinfo", side_effect=fake_getaddrinfo):
        with patch.object(
            httpx.AsyncHTTPTransport,
            "handle_async_request",
            new=fake_super,
        ):
            await transport.handle_async_request(request)

    assert captured["url_host"] == "93.184.216.34", "URL must use pinned IP, not hostname"
    assert captured["host_header"] == "example.com", "Host header must be original hostname"


@pytest.mark.asyncio
async def test_safe_async_transport_sets_sni_for_https() -> None:
    """For HTTPS requests, transport adds sni_hostname so cert validation still works."""
    from app.security.ssrf import SafeAsyncTransport

    captured: dict[str, Any] = {}

    async def fake_super(request: httpx.Request) -> httpx.Response:
        captured["extensions"] = dict(request.extensions)
        return httpx.Response(200, content=b"ok")

    def fake_getaddrinfo(host: str, port: Any, **_: Any) -> list[Any]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", port))]

    transport = SafeAsyncTransport()
    request = httpx.Request("GET", "https://example.com/")

    with patch("app.security.ssrf.socket.getaddrinfo", side_effect=fake_getaddrinfo):
        with patch.object(
            httpx.AsyncHTTPTransport,
            "handle_async_request",
            new=fake_super,
        ):
            await transport.handle_async_request(request)

    assert captured["extensions"].get("sni_hostname") == b"example.com"


@pytest.mark.asyncio
async def test_safe_async_transport_raises_on_dns_failure() -> None:
    from app.security.ssrf import SafeAsyncTransport

    transport = SafeAsyncTransport()
    request = httpx.Request("GET", "http://nxdomain.example.invalid/")

    with patch(
        "app.security.ssrf.socket.getaddrinfo",
        side_effect=socket.gaierror("NXDOMAIN"),
    ):
        with pytest.raises(httpx.ConnectError, match="DNS resolution failed"):
            await transport.handle_async_request(request)


# SafeSyncTransport


def test_safe_sync_transport_blocks_private_ip_literal() -> None:
    from app.security.ssrf import SafeSyncTransport

    transport = SafeSyncTransport()
    request = httpx.Request("GET", "http://10.0.0.1/")
    with pytest.raises(httpx.ConnectError, match="SSRF blocked"):
        transport.handle_request(request)


@pytest.mark.asyncio
async def test_safe_async_transport_blocks_redirect_to_private() -> None:
    """Second call to the transport (redirect hop) is blocked when target is private."""
    from app.security.ssrf import SafeAsyncTransport

    call_count = 0

    def fake_getaddrinfo(host: str, port: Any, **_: Any) -> list[Any]:
        nonlocal call_count
        call_count += 1
        if host == "example.com":
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", port))]
        # redirect target resolves to private
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("192.168.1.1", port))]

    transport = SafeAsyncTransport()
    # Simulate the redirect hop: caller already followed the redirect and
    # now calls the transport with the Location URL directly.
    redirect_request = httpx.Request("GET", "http://internal.corp/secret")

    with patch("app.security.ssrf.socket.getaddrinfo", side_effect=fake_getaddrinfo):
        with pytest.raises(httpx.ConnectError, match="SSRF blocked"):
            await transport.handle_async_request(redirect_request)


def test_safe_sync_transport_blocks_dns_rebinding() -> None:
    from app.security.ssrf import SafeSyncTransport

    def fake_getaddrinfo(host: str, port: Any, **_: Any) -> list[Any]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("172.16.0.1", port))]

    transport = SafeSyncTransport()
    request = httpx.Request("GET", "http://rebind.example.com/")

    with patch("app.security.ssrf.socket.getaddrinfo", side_effect=fake_getaddrinfo):
        with pytest.raises(httpx.ConnectError, match="SSRF blocked"):
            transport.handle_request(request)
```

- [ ] **Step 2: Run to verify failures**

```bash
pytest tests/security/test_ssrf.py -v --tb=short -k "transport"
```

Expected: all transport tests **FAIL** with `ImportError: cannot import name 'SafeAsyncTransport'`.

---

## Task 3: Implement `SafeAsyncTransport`, `SafeSyncTransport`, and factory helpers

**Files:**
- Modify: `app/security/ssrf.py`

- [ ] **Step 1: Add imports at the top of `app/security/ssrf.py`**

The file currently starts with:
```python
from __future__ import annotations

import socket
from ipaddress import ip_address, ip_network
from urllib.parse import urlparse

from app.core.logging_utils import get_logger
```

Replace with:
```python
from __future__ import annotations

import asyncio
import socket
from ipaddress import ip_address, ip_network
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.logging_utils import get_logger
```

- [ ] **Step 2: Update the `is_url_safe` docstring — remove TOCTOU acknowledgment**

Find this comment inside the `is_url_safe` docstring (line ~78):
```python
    # DNS-rebind TOCTOU is not mitigated: httpx re-resolves at connect time. Owner-only access model accepts this residual risk; the redirect chain re-checks Location per hop.
```

Remove that line entirely. The docstring should now read:
```python
def is_url_safe(url: str) -> tuple[bool, str | None]:
    """Check whether *url* resolves to a public (non-internal) IP.

    Returns ``(True, None)`` when safe, or ``(False, reason)`` when blocked.
    Performs DNS resolution and checks all resolved addresses against
    :data:`BLOCKED_NETWORKS`.

    Direct httpx fetchers use :class:`SafeAsyncTransport` which re-resolves at
    connect time and pins the connection to the validated IP, eliminating the
    TOCTOU window.  This function remains useful for preflight validation and
    for non-httpx paths (Playwright route interception, webhook URL validation).
    """
```

- [ ] **Step 3: Append transport classes and factories to `app/security/ssrf.py`**

Add after the closing of `is_url_safe`:

```python
class SafeAsyncTransport(httpx.AsyncHTTPTransport):
    """Async httpx transport that pins the resolved IP at connect time.

    Resolves the request hostname, checks every returned IP against
    :data:`BLOCKED_NETWORKS`, then rewrites the request URL to the first safe IP
    before calling ``super().handle_async_request()``.  httpcore receives an IP
    address and connects directly — no further DNS resolution occurs — eliminating
    the TOCTOU window present in preflight-only checks.

    For HTTPS the original hostname is preserved as the ``sni_hostname`` extension
    so TLS certificate validation and HTTP/2 ALPN negotiation continue to work.

    Browser-based providers (Playwright) use URL-level route interception instead;
    that approach is best-effort and does not close the TOCTOU window.
    """

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        scheme = url.scheme

        if scheme not in ("http", "https"):
            raise httpx.ConnectError(f"Blocked scheme: {scheme!r}")

        host = url.host
        port: int = url.port or (443 if scheme == "https" else 80)

        loop = asyncio.get_event_loop()
        try:
            infos: list[Any] = await loop.run_in_executor(
                None,
                lambda: socket.getaddrinfo(host, port, type=socket.SOCK_STREAM),
            )
        except socket.gaierror as exc:
            raise httpx.ConnectError(
                f"DNS resolution failed for {host!r}: {exc}"
            ) from exc

        if not infos:
            raise httpx.ConnectError(f"No addresses resolved for {host!r}")

        for _family, _type, _proto, _canon, sockaddr in infos:
            ip_str: str = sockaddr[0]
            if is_ip_blocked(ip_str):
                raise httpx.ConnectError(
                    f"SSRF blocked: {host!r} resolves to blocked address {ip_str!r}"
                )

        safe_ip: str = infos[0][4][0]
        family: int = infos[0][0]
        url_ip = f"[{safe_ip}]" if family == socket.AF_INET6 else safe_ip

        new_url = url.copy_with(host=url_ip)

        # Preserve original hostname in Host header (httpx would otherwise set it to the IP)
        new_headers = [(k, v) for k, v in request.headers.items() if k.lower() != "host"]
        new_headers.insert(0, ("host", host))

        extensions: dict[str, Any] = dict(request.extensions)
        if scheme == "https":
            extensions["sni_hostname"] = host.encode("ascii")

        pinned = httpx.Request(
            method=request.method,
            url=new_url,
            headers=new_headers,
            stream=request.stream,
            extensions=extensions,
        )
        return await super().handle_async_request(pinned)


class SafeSyncTransport(httpx.HTTPTransport):
    """Sync counterpart of :class:`SafeAsyncTransport`.

    Resolves DNS synchronously (acceptable for sync contexts such as the RSS
    feed fetcher), validates all returned IPs, then pins the URL to the
    resolved IP before calling ``super().handle_request()``.
    """

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        scheme = url.scheme

        if scheme not in ("http", "https"):
            raise httpx.ConnectError(f"Blocked scheme: {scheme!r}")

        host = url.host
        port: int = url.port or (443 if scheme == "https" else 80)

        try:
            infos: list[Any] = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise httpx.ConnectError(
                f"DNS resolution failed for {host!r}: {exc}"
            ) from exc

        if not infos:
            raise httpx.ConnectError(f"No addresses resolved for {host!r}")

        for _family, _type, _proto, _canon, sockaddr in infos:
            ip_str: str = sockaddr[0]
            if is_ip_blocked(ip_str):
                raise httpx.ConnectError(
                    f"SSRF blocked: {host!r} resolves to blocked address {ip_str!r}"
                )

        safe_ip: str = infos[0][4][0]
        family: int = infos[0][0]
        url_ip = f"[{safe_ip}]" if family == socket.AF_INET6 else safe_ip

        new_url = url.copy_with(host=url_ip)

        new_headers = [(k, v) for k, v in request.headers.items() if k.lower() != "host"]
        new_headers.insert(0, ("host", host))

        extensions: dict[str, Any] = dict(request.extensions)
        if scheme == "https":
            extensions["sni_hostname"] = host.encode("ascii")

        pinned = httpx.Request(
            method=request.method,
            url=new_url,
            headers=new_headers,
            stream=request.stream,
            extensions=extensions,
        )
        return super().handle_request(pinned)


def make_safe_async_client(**kwargs: Any) -> httpx.AsyncClient:
    """Return an :class:`httpx.AsyncClient` backed by :class:`SafeAsyncTransport`.

    SSL kwargs ``verify`` and ``cert`` are forwarded to the transport (which
    controls the SSL context); all other kwargs are forwarded to
    :class:`httpx.AsyncClient`.
    """
    verify = kwargs.pop("verify", True)
    cert = kwargs.pop("cert", None)
    transport = SafeAsyncTransport(verify=verify, cert=cert)
    return httpx.AsyncClient(transport=transport, **kwargs)


def make_safe_sync_client(**kwargs: Any) -> httpx.Client:
    """Return an :class:`httpx.Client` backed by :class:`SafeSyncTransport`."""
    verify = kwargs.pop("verify", True)
    cert = kwargs.pop("cert", None)
    transport = SafeSyncTransport(verify=verify, cert=cert)
    return httpx.Client(transport=transport, **kwargs)
```

- [ ] **Step 4: Run transport tests to verify they now pass**

```bash
pytest tests/security/test_ssrf.py -v --tb=short
```

Expected: **all tests PASS**.

- [ ] **Step 5: Run type check**

```bash
mypy app/security/ssrf.py --show-error-codes --pretty
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add app/security/ssrf.py tests/security/test_ssrf.py
git commit -m "feat(security): add SafeAsyncTransport and SafeSyncTransport for IP-pinned SSRF enforcement"
```

---

## Task 4: Update `direct_html_provider.py` and `direct_pdf_provider.py`

**Files:**
- Modify: `app/adapters/content/scraper/direct_html_provider.py`
- Modify: `app/adapters/content/scraper/direct_pdf_provider.py`

- [ ] **Step 1: Update `direct_html_provider.py` import**

Find:
```python
from app.security.ssrf import is_url_safe
```

Replace with:
```python
from app.security.ssrf import is_url_safe, make_safe_async_client
```

- [ ] **Step 2: Update the `httpx.AsyncClient` call in `direct_html_provider.py`**

Find (inside `_fetch_html`):
```python
async with httpx.AsyncClient(follow_redirects=False, timeout=self._timeout_sec) as client:
```

Replace with:
```python
async with make_safe_async_client(follow_redirects=False, timeout=self._timeout_sec) as client:
```

- [ ] **Step 3: Remove the `import httpx` top-level import if it is now unused**

Check whether `httpx` is referenced anywhere else in the file (e.g. exception types). If `httpx.ConnectError` or similar is caught, keep the import. If the only usage was `httpx.AsyncClient`, remove `import httpx`.

Run:
```bash
grep -n "httpx\." app/adapters/content/scraper/direct_html_provider.py
```

Remove `import httpx` only if the grep shows no remaining `httpx.` references.

- [ ] **Step 4: Apply the same two changes to `direct_pdf_provider.py`**

Find:
```python
from app.security.ssrf import is_url_safe
```
Replace with:
```python
from app.security.ssrf import is_url_safe, make_safe_async_client
```

Find (inside `_fetch_pdf`):
```python
async with httpx.AsyncClient(follow_redirects=False, timeout=self._timeout_sec) as client:
```
Replace with:
```python
async with make_safe_async_client(follow_redirects=False, timeout=self._timeout_sec) as client:
```

Same `import httpx` cleanup check as Step 3.

- [ ] **Step 5: Verify tests still pass**

```bash
pytest tests/security/test_ssrf.py tests/adapters/ -v --tb=short -q
```

Expected: no regressions.

- [ ] **Step 6: Commit**

```bash
git add app/adapters/content/scraper/direct_html_provider.py \
        app/adapters/content/scraper/direct_pdf_provider.py
git commit -m "feat(security): use SafeAsyncTransport in direct_html and direct_pdf providers"
```

---

## Task 5: Update `defuddle_provider.py` and `proxy.py`

**Files:**
- Modify: `app/adapters/content/scraper/defuddle_provider.py`
- Modify: `app/api/routers/proxy.py`

- [ ] **Step 1: Update `defuddle_provider.py`**

Find:
```python
from app.security.ssrf import is_url_safe
```
Replace with:
```python
from app.security.ssrf import is_url_safe, make_safe_async_client
```

Find (inside `_fetch_raw`):
```python
async with httpx.AsyncClient(follow_redirects=False, timeout=self._timeout_sec) as client:
```
Replace with:
```python
async with make_safe_async_client(follow_redirects=False, timeout=self._timeout_sec) as client:
```

- [ ] **Step 2: Update `proxy.py`**

Find:
```python
from app.security.ssrf import is_url_safe
```
Replace with:
```python
from app.security.ssrf import is_url_safe, make_safe_async_client
```

Find (inside `proxy_image`):
```python
async with httpx.AsyncClient(follow_redirects=False, timeout=10.0) as client:
```
Replace with:
```python
async with make_safe_async_client(follow_redirects=False, timeout=10.0) as client:
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/security/test_ssrf.py tests/api/test_proxy.py -v --tb=short -q
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add app/adapters/content/scraper/defuddle_provider.py \
        app/api/routers/proxy.py
git commit -m "feat(security): use SafeAsyncTransport in defuddle provider and image proxy"
```

---

## Task 6: Update RSS feed fetcher (sync)

**Files:**
- Modify: `app/adapters/rss/feed_fetcher.py`

- [ ] **Step 1: Update import in `feed_fetcher.py`**

Find:
```python
from app.security.ssrf import is_url_safe
```
Replace with:
```python
from app.security.ssrf import is_url_safe, make_safe_sync_client
```

- [ ] **Step 2: Replace the `httpx.get(...)` call**

Find (line ~70):
```python
resp = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=False)
```

Replace with:
```python
with make_safe_sync_client(follow_redirects=False) as client:
    resp = client.get(url, headers=headers, timeout=timeout)
```

The `with` block replaces just that one line. The existing `resp` variable is assigned inside it; all subsequent code using `resp` stays unchanged (it is not inside the `with` block).

- [ ] **Step 3: Check whether `import httpx` can be removed from `feed_fetcher.py`**

```bash
grep -n "httpx\." app/adapters/rss/feed_fetcher.py
```

Remove `import httpx` only if the grep shows no remaining `httpx.` usages.

- [ ] **Step 4: Run feed fetcher tests**

```bash
pytest tests/test_feed_fetcher.py -v --tb=short -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/adapters/rss/feed_fetcher.py
git commit -m "feat(security): use SafeSyncTransport in RSS feed fetcher"
```

---

## Task 7: Update webhook dispatcher

**Files:**
- Modify: `app/infrastructure/messaging/handlers/webhook_dispatcher.py`

- [ ] **Step 1: Update import**

Find:
```python
import httpx
```
This import stays (used for `httpx.AsyncClient` type hints and timeout types). Add `make_safe_async_client` to the ssrf import. Find the existing ssrf import:

```python
from app.domain.services.webhook_service import is_webhook_url_safe
```

Add alongside (or as a new import line):
```python
from app.security.ssrf import make_safe_async_client
```

- [ ] **Step 2: Replace the `httpx.AsyncClient(...)` construction in `_get_client`**

Find (lines ~53-60):
```python
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=_CONNECT_TIMEOUT,
                    read=_READ_TIMEOUT,
                    write=_READ_TIMEOUT,
                    pool=_READ_TIMEOUT,
                ),
            )
            self._owns_client = True
```

Replace with:
```python
        if self._http_client is None:
            self._http_client = make_safe_async_client(
                timeout=httpx.Timeout(
                    connect=_CONNECT_TIMEOUT,
                    read=_READ_TIMEOUT,
                    write=_READ_TIMEOUT,
                    pool=_READ_TIMEOUT,
                ),
            )
            self._owns_client = True
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/ -k "webhook" -v --tb=short -q
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add app/infrastructure/messaging/handlers/webhook_dispatcher.py
git commit -m "feat(security): use SafeAsyncTransport in webhook dispatcher"
```

---

## Task 8: Protect Twitter article resolver

The resolver currently uses `follow_redirects=True` with no SSRF check. `t.co` links can redirect anywhere. Fix: switch to `make_safe_async_client(follow_redirects=False)` with a manual 5-hop redirect loop matching the pattern already used in `direct_html_provider.py`.

**Files:**
- Modify: `app/adapters/twitter/article_link_resolver.py`
- Modify: `tests/security/test_ssrf.py`

- [ ] **Step 1: Add a failing test for the resolver**

Append to `tests/security/test_ssrf.py`:

```python
# ---------------------------------------------------------------------------
# Twitter article resolver SSRF protection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_twitter_resolver_blocks_private_ip_redirect() -> None:
    """Resolver blocks a t.co link that ultimately redirects to a private IP."""
    from app.adapters.twitter.article_link_resolver import ArticleLinkResolver

    resolver = ArticleLinkResolver()

    def fake_getaddrinfo(host: str, port: Any, **_: Any) -> list[Any]:
        # t.co resolves publicly, but the redirect target resolves to a private IP
        if host == "t.co":
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("104.244.42.1", port))]
        # redirect target — private IP
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("192.168.1.100", port))]

    with patch("app.security.ssrf.socket.getaddrinfo", side_effect=fake_getaddrinfo):
        result = await resolver.resolve("https://t.co/privatelink")

    assert result.reason == "resolve_failed"
```

Run to verify it **fails** (method may not exist yet or may not block):
```bash
pytest tests/security/test_ssrf.py::test_twitter_resolver_blocks_private_ip_redirect -v --tb=short
```

- [ ] **Step 2: Update imports in `article_link_resolver.py`**

Add to existing imports:
```python
from typing import Any

from app.security.ssrf import is_url_safe, make_safe_async_client
```

If `from typing import Any` is already present, skip adding it again.

- [ ] **Step 3: Replace `httpx.AsyncClient(follow_redirects=True, ...)` with safe client**

Find the httpx client construction (it will look like `httpx.AsyncClient(follow_redirects=True, ...)` or similar). Replace with `make_safe_async_client(follow_redirects=False, ...)`.

Then locate every `client.get(...)` or `client.head(...)` call that previously relied on automatic redirect following. Wrap each one in a manual redirect loop:

```python
async def _safe_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_redirects: int = 5,
    **kwargs: Any,
) -> httpx.Response:
    """Follow redirects manually, checking each target with is_url_safe()."""
    current = url
    for _ in range(max_redirects + 1):
        safe, reason = is_url_safe(current)
        if not safe:
            raise ValueError(f"SSRF blocked redirect target: {reason}")
        resp = await client.get(current, **kwargs)
        if resp.status_code in {301, 302, 303, 307, 308}:
            location = resp.headers.get("location", "")
            if not location:
                break
            from urllib.parse import urljoin
            current = urljoin(current, location)
            continue
        return resp
    raise ValueError("Too many redirects")
```

Add this helper as a module-level function inside `article_link_resolver.py` and replace each `await client.get(url, ...)` call with `await _safe_get(client, url, ...)`.

- [ ] **Step 4: Run the new test**

```bash
pytest tests/security/test_ssrf.py::test_twitter_resolver_blocks_private_ip_redirect -v --tb=short
```

Expected: **PASS**.

- [ ] **Step 5: Run existing Twitter resolver tests**

```bash
pytest tests/ -k "twitter" -v --tb=short -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add app/adapters/twitter/article_link_resolver.py tests/security/test_ssrf.py
git commit -m "feat(security): add SSRF protection and manual redirect handling to Twitter article resolver"
```

---

## Task 9: Add Playwright route interception

**Files:**
- Modify: `app/adapters/content/scraper/playwright_provider.py`

- [ ] **Step 1: Read the provider to find the page-setup location**

```bash
grep -n "page\.\|async def scrape\|route" app/adapters/content/scraper/playwright_provider.py | head -30
```

Identify the method where a `page` object is created/configured before `page.goto()` is called.

- [ ] **Step 2: Add SSRF route interception before `page.goto()`**

In the method that sets up the page, insert this block immediately before the `await page.goto(url)` call:

```python
from app.security.ssrf import is_url_safe

async def _block_ssrf(route: Any) -> None:
    req_url: str = route.request.url
    safe, reason = is_url_safe(req_url)
    if not safe:
        logger.warning(
            "playwright_ssrf_blocked",
            url=req_url,
            reason=reason,
        )
        await route.abort("accessdenied")
        return
    await route.continue_()

await page.route("**/*", _block_ssrf)
```

The `Any` type on `route` refers to `playwright.async_api.Route`. If the file already imports from `playwright.async_api`, use `Route` directly instead of `Any`.

- [ ] **Step 3: Add a docstring comment explaining the limitation**

Directly above the `await page.route(...)` call, add:

```python
# SSRF protection: intercept all Playwright requests and abort those targeting
# private/reserved IPs.  This is URL-level filtering (preflight), not
# connection-time enforcement — it does not close the DNS-rebinding TOCTOU
# window inside the browser process.  Use SafeAsyncTransport for direct httpx
# fetchers where true connection-time pinning is required.
```

- [ ] **Step 4: Run the full test suite to check for regressions**

```bash
pytest tests/ -m "not slow and not integration" --ignore=tests/benchmarks \
  --ignore=tests/api/test_background_processor.py \
  --ignore=tests/test_api_rate_limit_and_sync.py \
  -q --tb=short
```

Expected: no new failures.

- [ ] **Step 5: Commit**

```bash
git add app/adapters/content/scraper/playwright_provider.py
git commit -m "feat(security): add SSRF route interception to Playwright provider (best-effort)"
```

---

## Task 10: Final verification

- [ ] **Step 1: Run the complete SSRF test file**

```bash
pytest tests/security/test_ssrf.py -v --tb=short
```

Expected: all tests pass. Count should be ≥ 20 tests.

- [ ] **Step 2: Run type check across all modified files**

```bash
mypy app/security/ssrf.py \
     app/adapters/content/scraper/direct_html_provider.py \
     app/adapters/content/scraper/direct_pdf_provider.py \
     app/adapters/content/scraper/defuddle_provider.py \
     app/api/routers/proxy.py \
     app/adapters/rss/feed_fetcher.py \
     app/infrastructure/messaging/handlers/webhook_dispatcher.py \
     app/adapters/twitter/article_link_resolver.py \
     app/adapters/content/scraper/playwright_provider.py \
     --show-error-codes --pretty
```

Expected: no errors.

- [ ] **Step 3: Run full unit test suite**

```bash
pytest tests/ -m "not slow and not integration" --ignore=tests/benchmarks \
  --ignore=tests/api/test_background_processor.py \
  --ignore=tests/test_api_rate_limit_and_sync.py \
  -q --tb=short --maxfail=5
```

Expected: all pass, coverage unaffected or improved.
