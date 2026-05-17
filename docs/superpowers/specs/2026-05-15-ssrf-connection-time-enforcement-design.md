# SSRF Connection-Time Enforcement — Design Spec

**Date:** 2026-05-15 **Status:** Draft

---

## Problem

All outbound HTTP fetchers in the codebase call `is_url_safe()` before making a request. That function resolves the hostname and checks the resulting IPs against `BLOCKED_NETWORKS` — but then hands the original hostname to httpx, which calls httpcore, which calls `anyio.getaddrinfo` again at connect time. A DNS rebinding attack (TTL=0, first lookup → public IP, second → 192.168.x.x) bypasses the preflight entirely. The comment on line 78 of `ssrf.py` acknowledges this:

```python
# DNS-rebind TOCTOU is not mitigated: httpx re-resolves at connect time.
```

Additionally:
- `app/adapters/twitter/article_link_resolver.py` makes outbound requests with `follow_redirects=True` and zero SSRF protection.
- `tests/security/test_ssrf.py` is referenced in a proxy test comment but does not exist.

---

## Goal

1. Eliminate the TOCTOU window for all direct httpx fetchers by pinning the resolved IP at connect time via a custom transport.
2. Ensure every redirect hop goes through the same IP-pinning path.
3. Add SSRF protection to the Twitter article resolver.
4. Add Playwright request interception for browser-based providers (best-effort; limitations documented).
5. Create `tests/security/test_ssrf.py` covering the full payload matrix.

---

## Scope

### In scope

- `app/security/ssrf.py` — add `SafeAsyncTransport`, `SafeSyncTransport`, `make_safe_async_client()`, `make_safe_sync_client()` factory helpers.
- `app/adapters/content/scraper/direct_html_provider.py` — use `make_safe_async_client()`.
- `app/adapters/content/scraper/direct_pdf_provider.py` — use `make_safe_async_client()`.
- `app/adapters/content/scraper/defuddle_provider.py` — use `make_safe_async_client()`.
- `app/api/routers/proxy.py` — use `make_safe_async_client()`.
- `app/adapters/rss/feed_fetcher.py` — use `make_safe_sync_client()`.
- `app/infrastructure/messaging/handlers/webhook_dispatcher.py` — use `make_safe_async_client()`.
- `app/adapters/twitter/article_link_resolver.py` — add preflight `is_url_safe()` + use `make_safe_async_client()`.
- `app/adapters/content/scraper/playwright_provider.py` — add route interception.
- Remove the TOCTOU acknowledgment comment in `ssrf.py`; replace with a note on what the transport guarantees and what it does not.
- `tests/security/test_ssrf.py` — comprehensive SSRF payload tests.

### Out of scope

- Scrapling (in-process, no outbound HTTP calls of its own).
- Crawl4AI and Crawlee providers (send URLs to a self-hosted Docker sidecar; the sidecar URL itself is already checked; the target URL SSRF risk is inside the sidecar's network boundary, not ours).
- OpenRouter / Firecrawl API clients (fixed-endpoint, operator-controlled, not user-supplied URLs).

---

## Design

### 1. `SafeAsyncTransport` and `SafeSyncTransport`

Added to `app/security/ssrf.py`. The key invariant: by the time `super().handle_async_request()` is called, the URL host field contains a raw IP address, not a hostname. httpcore sees an IP and connects directly — no further DNS resolution occurs.

**`SafeAsyncTransport(httpx.AsyncHTTPTransport)`**

`handle_async_request(request)`:

1. Reject non-http/https schemes immediately.
2. Extract `host` and `port` from `request.url`.
3. Run `socket.getaddrinfo(host, port, type=SOCK_STREAM)` in a thread executor (blocking call, must not run on the event loop).
4. Raise `httpx.ConnectError` if DNS fails or returns no results.
5. For **each** resolved IP: call `is_ip_blocked(ip)`. Raise `httpx.ConnectError` on the first blocked address. Checking all addresses prevents an attacker from mixing one public IP with one private IP in a multi-A-record response.
6. Take the first safe resolved IP.
7. Format for URL: wrap IPv6 in brackets (e.g. `[::1]` → kept as-is but would be blocked; `[2001:db8::1]` → safe).
8. Rewrite `request.url` with the IP substituted for the hostname via `url.copy_with(host=ip)`.
9. Override the `host` header back to the original hostname (httpx auto-sets it from the URL, so we must correct it after the rewrite).
10. For HTTPS: add `sni_hostname=hostname.encode("ascii")` to `request.extensions` so httpcore uses the original hostname for TLS SNI and certificate validation still works.
11. Create a new `httpx.Request` with the rewritten URL, corrected headers, SNI extension, and the same `stream` and `method` as the original.
12. Forward to `super().handle_async_request(new_request)`.

`__init__` accepts the same keyword arguments as `httpx.AsyncHTTPTransport` and passes them through, so callers can still configure `verify`, `cert`, `http1`, `http2`, `limits`.

**`SafeSyncTransport(httpx.HTTPTransport)`**

Identical logic in `handle_request`, using `socket.getaddrinfo` directly (blocking path, no executor needed).

**Factory helpers**

```python
def make_safe_async_client(**kwargs) -> httpx.AsyncClient:
    """Return an AsyncClient backed by SafeAsyncTransport."""
    transport = SafeAsyncTransport()
    return httpx.AsyncClient(transport=transport, **kwargs)

def make_safe_sync_client(**kwargs) -> httpx.Client:
    """Return a sync Client backed by SafeSyncTransport."""
    transport = SafeSyncTransport()
    return httpx.Client(transport=transport, **kwargs)
```

### 2. Direct httpx fetchers

Each fetcher currently creates its client as:

```python
async with httpx.AsyncClient(follow_redirects=False, timeout=self._timeout_sec) as client:
```

Replace with:

```python
async with make_safe_async_client(follow_redirects=False, timeout=self._timeout_sec) as client:
```

**Files:** `direct_html_provider.py`, `direct_pdf_provider.py`, `defuddle_provider.py`, `proxy.py`.

The per-hop `is_url_safe()` calls in the redirect loop are **kept** as defense-in-depth. They now serve as a pre-send consistency check (cheap, already validated by the transport, but harmless). The transport's IP pinning is what actually closes the TOCTOU gap; the preflight is belt-and- suspenders.

The existing `is_url_safe` import stays; `make_safe_async_client` is added alongside it.

### 3. RSS feed fetcher (`feed_fetcher.py`)

Currently:

```python
resp = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=False)
```

Replace with:

```python
with make_safe_sync_client(follow_redirects=False) as client:
    resp = client.get(url, headers=headers, timeout=timeout)
```

The preflight `_validate_feed_url(url)` call is kept (defense-in-depth, scheme check).

### 4. Webhook dispatcher (`webhook_dispatcher.py`)

The shared `httpx.AsyncClient` is constructed once per dispatcher instance. Replace the construction site with `make_safe_async_client(...)` using the same timeout/limits parameters currently passed to `httpx.AsyncClient`. The per-delivery `is_url_safe()` preflight is kept.

### 5. Twitter article resolver (`article_link_resolver.py`)

Currently uses `httpx.AsyncClient(follow_redirects=True, ...)` with no SSRF check. The resolver already restricts to `_RESOLVABLE_HOSTS`, but `t.co` redirects can land anywhere.

Changes:
- Add `is_url_safe(url)` preflight before each `client.get()` / `client.head()` call.
- Replace `httpx.AsyncClient(follow_redirects=True)` with `make_safe_async_client(follow_redirects=False)`.
- Implement manual redirect handling (same pattern as `direct_html_provider`) with a 5-hop cap and per-hop `is_url_safe()` check.

### 6. Playwright provider request interception

In `PlaywrightProvider.scrape_markdown` (or the equivalent page-setup method), before page navigation, register a route handler:

```python
async def _block_ssrf_route(route: Route) -> None:
    url = route.request.url
    safe, reason = is_url_safe(url)
    if not safe:
        logger.warning("playwright_ssrf_blocked", url=url, reason=reason)
        await route.abort("accessdenied")
        return
    await route.continue_()

await page.route("**/*", _block_ssrf_route)
```

**Documented limitations:** Playwright route interception fires after DNS resolution by the browser process; it does not prevent DNS rebinding in the browser's internal networking. This is best-effort URL-level filtering, not connection-time enforcement. The same TOCTOU caveat that previously applied to preflight-only checks applies here.

### 7. Remove / replace TOCTOU comment

Remove the comment on `ssrf.py` line 78:
```python
# DNS-rebind TOCTOU is not mitigated: httpx re-resolves at connect time.
```

Replace with a docstring on `SafeAsyncTransport` that explains what the transport guarantees (IP-pinned connection, no re-resolution for direct httpx clients) and what it does not guarantee (browser-based providers use interception only).

### 8. Tests: `tests/security/test_ssrf.py`

New file. All tests target `is_ip_blocked`, `is_url_safe`, and `SafeAsyncTransport` directly using `httpx.MockTransport` / `respx` for transport-level assertions where needed.

| Test | Payload | Expected |
|------|---------|----------|
| `test_localhost_ipv4` | `http://127.0.0.1/` | blocked |
| `test_localhost_name` | `http://localhost/` | blocked |
| `test_rfc1918_10` | `http://10.0.0.1/` | blocked |
| `test_rfc1918_172` | `http://172.16.0.1/` | blocked |
| `test_rfc1918_192` | `http://192.168.1.1/` | blocked |
| `test_ipv6_loopback` | `http://[::1]/` | blocked |
| `test_ipv4_mapped_ipv6` | `::ffff:127.0.0.1` passed to `is_ip_blocked` | blocked |
| `test_ipv4_mapped_ipv6_url` | `http://[::ffff:7f00:1]/` | blocked |
| `test_aws_metadata` | `http://169.254.169.254/` | blocked |
| `test_link_local_ipv6` | `http://[fe80::1]/` | blocked |
| `test_6to4_wrapping_rfc1918` | `2002:c0a8:0101::` (`192.168.1.1` wrapped) | blocked |
| `test_public_ip_allowed` | `http://93.184.216.34/` | allowed |
| `test_redirect_to_private` | transport mock: `http://example.com/` → 302 → `http://192.168.1.1/` | `ConnectError` on redirect target |
| `test_dns_rebinding_simulation` | monkeypatch `socket.getaddrinfo` to return `192.168.1.1` for `example.com`; `SafeAsyncTransport` must raise before connecting | `ConnectError` raised, no TCP connect |
| `test_scheme_blocked_file` | `file:///etc/passwd` | blocked (scheme check) |
| `test_scheme_blocked_ftp` | `ftp://example.com/` | blocked (scheme check) |
| `test_multicast` | `http://224.0.0.1/` | blocked |
| `test_carrier_grade_nat` | `http://100.64.0.1/` | blocked |
| `test_nat64_prefix` | `http://[64:ff9b::1]/` | blocked |
| `test_all_resolved_ips_checked` | monkeypatch `getaddrinfo` to return `[8.8.8.8, 192.168.1.1]`; transport must block even though first IP is public | `ConnectError` raised |

DNS rebinding simulation: monkeypatch `app.security.ssrf.socket.getaddrinfo` (the reference inside `ssrf.py`) to return a private IP for a public-looking hostname. Verify `SafeAsyncTransport.handle_async_request` raises `httpx.ConnectError` without making a TCP connection. Use `httpx.MockTransport` as the `super()` target to assert it is never called.

---

## What does not change

- `BLOCKED_NETWORKS` list in `ssrf.py` — already comprehensive.
- `is_ip_blocked()` — already handles IPv4-mapped IPv6 unwrapping.
- `is_url_safe()` — kept for preflight use and browser-provider interception.
- `validate_webhook_url()` in `webhook_service.py` — kept as the API-layer validator.
- Alembic migrations, database models, Telegram handlers — unaffected.

---

## Risk notes

- **HTTP/2 with IP-based URLs:** httpcore selects HTTP/2 based on ALPN negotiation, which uses SNI. By passing `sni_hostname` in extensions, ALPN negotiation uses the real hostname, so HTTP/2 upgrades continue to work.
- **Certificate pinning / custom `verify`:** Callers pass `verify` to `make_safe_async_client()` as before; it propagates to `SafeAsyncTransport.__init__` unchanged.
- **IPv6 URL formatting:** `socket.getaddrinfo` returns bare IPv6 strings (e.g. `2001:db8::1`). The transport wraps them in brackets for the URL (e.g. `[2001:db8::1]`) as required by RFC 2732.
- **Existing per-hop `is_url_safe()` calls:** Kept. The transport makes them redundant for TOCTOU purposes, but they provide a cheap early rejection before even building the request.
