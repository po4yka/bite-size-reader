from __future__ import annotations

import socket

import pytest

from app.core.urls.validation import _resolve_hostname_to_addrs, dns_cache_scope, validate_url_input


def test_validate_url_input_rejects_localhost() -> None:
    with pytest.raises(ValueError, match="Localhost access not allowed"):
        validate_url_input("http://localhost/admin")


def test_validate_url_input_rejects_suspicious_domain_suffix() -> None:
    with pytest.raises(ValueError, match=r"Suspicious domain pattern: \.internal"):
        validate_url_input("https://service.internal/path")


def test_validate_url_input_rejects_blocked_ip_literal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.security.ssrf.is_ip_blocked", lambda _ip: True)

    with pytest.raises(ValueError, match=r"Blocked IP address: 203\.0\.113\.10"):
        validate_url_input("https://203.0.113.10/path")


def test_dns_cache_scope_reuses_hostname_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}
    fake_response = [("family", "socktype", "proto", "", ("93.184.216.34", 0))]

    def fake_getaddrinfo(*_args, **_kwargs):
        calls["count"] += 1
        return fake_response

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    with dns_cache_scope():
        first = _resolve_hostname_to_addrs("example.com", "example.com")
        second = _resolve_hostname_to_addrs("example.com", "example.com")

    uncached = _resolve_hostname_to_addrs("example.com", "example.com")

    assert first == second == uncached == fake_response
    assert calls["count"] == 2
