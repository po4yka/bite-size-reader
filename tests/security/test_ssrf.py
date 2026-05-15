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


def test_is_url_safe_blocks_hostname_that_resolves_to_private(monkeypatch: pytest.MonkeyPatch) -> None:
    # Patch resolve_host_ips to return a private IP; is_url_safe must block the request.
    # The reason string may reference the resolved IP or the hostname depending on
    # whether is_ip_blocked short-circuits before DNS resolution.
    monkeypatch.setattr("app.security.ssrf.resolve_host_ips", lambda _: ["192.168.1.1"])
    safe, reason = is_url_safe("http://evil.example.com/")
    assert safe is False
    assert reason is not None
