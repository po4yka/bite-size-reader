"""Centralized SSRF protection.

Single source of truth for blocked-network definitions, hostname resolution,
and URL safety checks used across the codebase (proxy, RSS fetcher, webhooks,
URL validation).
"""

from __future__ import annotations

import socket
from ipaddress import ip_address, ip_network
from urllib.parse import urlparse

from app.core.logging_utils import get_logger

logger = get_logger(__name__)

# Private/internal IP ranges that must be blocked to prevent SSRF.
BLOCKED_NETWORKS = [
    ip_network("10.0.0.0/8"),  # Private Class A
    ip_network("172.16.0.0/12"),  # Private Class B
    ip_network("192.168.0.0/16"),  # Private Class C
    ip_network("127.0.0.0/8"),  # Loopback
    ip_network("169.254.0.0/16"),  # Link-local / AWS metadata
    ip_network("0.0.0.0/8"),  # Current network
    ip_network("100.64.0.0/10"),  # Carrier-grade NAT
    ip_network("192.0.0.0/24"),  # IETF Protocol Assignments
    ip_network("192.0.2.0/24"),  # TEST-NET-1
    ip_network("198.51.100.0/24"),  # TEST-NET-2
    ip_network("203.0.113.0/24"),  # TEST-NET-3
    ip_network("224.0.0.0/4"),  # Multicast
    ip_network("240.0.0.0/4"),  # Reserved
    ip_network("255.255.255.255/32"),  # Broadcast
    ip_network("::1/128"),  # IPv6 loopback
    ip_network("fc00::/7"),  # IPv6 private
    ip_network("fe80::/10"),  # IPv6 link-local
    ip_network("::ffff:0:0/96"),  # IPv4-mapped IPv6 catch-all
    ip_network("::/128"),  # IPv6 unspecified
    ip_network("64:ff9b::/96"),  # NAT64 well-known prefix
    ip_network("2002::/16"),  # 6to4 (wraps RFC1918 and other reserved ranges)
]


def resolve_host_ips(hostname: str) -> list[str]:
    """Resolve *hostname* to IP addresses (IPv4/IPv6) via DNS."""
    addresses: list[str] = []
    for info in socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP):
        addr = str(info[4][0])
        if addr not in addresses:
            addresses.append(addr)
    return addresses


def is_ip_blocked(ip_str: str) -> bool:
    """Return ``True`` if *ip_str* falls within any :data:`BLOCKED_NETWORKS`.

    IPv4-mapped IPv6 addresses (e.g. ``::ffff:127.0.0.1``) are unwrapped to
    their IPv4 form before the check so they cannot bypass IPv4 blocked ranges.
    """
    try:
        ip_obj = ip_address(ip_str)
    except ValueError:
        # Unparseable address -- treat as blocked for safety.
        return True
    # Unwrap IPv4-mapped IPv6 (::ffff:a.b.c.d) so IPv4 blocked ranges apply.
    if ip_obj.version == 6 and ip_obj.ipv4_mapped is not None:
        ip_obj = ip_obj.ipv4_mapped
    return any(ip_obj in network for network in BLOCKED_NETWORKS)


def is_url_safe(url: str) -> tuple[bool, str | None]:
    """Check whether *url* resolves to a public (non-internal) IP.

    Returns ``(True, None)`` when safe, or ``(False, reason)`` when blocked.
    Performs DNS resolution and checks all resolved addresses against
    :data:`BLOCKED_NETWORKS`.

    # DNS-rebind TOCTOU is not mitigated: httpx re-resolves at connect time. Owner-only access model accepts this residual risk; the redirect chain re-checks Location per hop.
    """
    try:
        hostname = urlparse(url).hostname
    except Exception:
        return False, "Malformed URL"

    if not hostname:
        return False, "Hostname is empty"

    hostname_lower = hostname.lower()
    if hostname_lower in ("localhost", "localhost.localdomain"):
        return False, "Localhost is not allowed"

    # Fast path for IP literals -- skip DNS resolution.
    try:
        if is_ip_blocked(hostname):
            return False, f"Private or reserved IP address: {hostname}"
        return True, None
    except Exception:
        pass  # Not an IP literal; fall through to DNS resolution.

    try:
        resolved_ips = resolve_host_ips(hostname)
    except (socket.gaierror, OSError):
        return False, f"DNS resolution failed for {hostname}"

    if not resolved_ips:
        return False, f"No DNS records found for {hostname}"

    for resolved in resolved_ips:
        if is_ip_blocked(resolved):
            return False, f"Hostname resolves to blocked address: {resolved}"

    return True, None
