"""Tests for correlation ID validation in correlation_id_middleware."""

from __future__ import annotations

import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.middleware import correlation_id_middleware
from app.core.logging_utils import sanitize_correlation_id

_VALID_RE = re.compile(r"[A-Za-z0-9._:\-]{1,128}")


def _make_app() -> FastAPI:
    app = FastAPI()
    app.middleware("http")(correlation_id_middleware)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    return app


class TestSanitizeCorrelationId:
    def test_valid_id_passes_through(self):
        cid, generated = sanitize_correlation_id("req-abc123")
        assert cid == "req-abc123"
        assert generated is False

    def test_valid_id_with_all_allowed_chars(self):
        value = "A.b_c:d-e"
        cid, generated = sanitize_correlation_id(value)
        assert cid == value
        assert generated is False

    def test_valid_id_at_max_length(self):
        value = "a" * 128
        cid, generated = sanitize_correlation_id(value)
        assert cid == value
        assert generated is False

    def test_missing_id_generates_new(self):
        cid, generated = sanitize_correlation_id(None)
        assert generated is True
        assert _VALID_RE.fullmatch(cid)

    def test_empty_string_generates_new(self):
        cid, generated = sanitize_correlation_id("")
        assert generated is True
        assert _VALID_RE.fullmatch(cid)

    def test_too_long_id_generates_new(self):
        cid, generated = sanitize_correlation_id("a" * 129)
        assert generated is True
        assert _VALID_RE.fullmatch(cid)

    def test_newline_injection_generates_new(self):
        cid, generated = sanitize_correlation_id("valid\nX-Injected: evil")
        assert generated is True
        assert "\n" not in cid
        assert _VALID_RE.fullmatch(cid)

    def test_unicode_generates_new(self):
        cid, generated = sanitize_correlation_id("req-中文")
        assert generated is True
        assert _VALID_RE.fullmatch(cid)

    def test_control_chars_generate_new(self):
        cid, generated = sanitize_correlation_id("req-\x00\x01")
        assert generated is True
        assert _VALID_RE.fullmatch(cid)

    def test_space_generates_new(self):
        cid, generated = sanitize_correlation_id("req id")
        assert generated is True
        assert _VALID_RE.fullmatch(cid)

    def test_generated_id_format(self):
        cid, generated = sanitize_correlation_id(None)
        assert cid.startswith("api-")
        assert len(cid) == len("api-") + 16


class TestCorrelationIdMiddleware:
    def test_valid_header_echoed_in_response(self):
        client = TestClient(_make_app())
        resp = client.get("/ping", headers={"X-Correlation-ID": "my-trace-123"})
        assert resp.headers["X-Correlation-ID"] == "my-trace-123"

    def test_missing_header_gets_generated_id(self):
        client = TestClient(_make_app())
        resp = client.get("/ping")
        cid = resp.headers.get("X-Correlation-ID", "")
        assert cid.startswith("api-")
        assert _VALID_RE.fullmatch(cid)

    def test_too_long_header_replaced(self):
        client = TestClient(_make_app())
        bad = "a" * 200
        resp = client.get("/ping", headers={"X-Correlation-ID": bad})
        cid = resp.headers.get("X-Correlation-ID", "")
        assert cid != bad
        assert _VALID_RE.fullmatch(cid)

    def test_newline_injection_replaced(self):
        client = TestClient(_make_app())
        resp = client.get("/ping", headers={"X-Correlation-ID": "id\r\nEvil: header"})
        cid = resp.headers.get("X-Correlation-ID", "")
        assert "\n" not in cid
        assert "\r" not in cid
        assert _VALID_RE.fullmatch(cid)

    def test_response_always_has_safe_id(self):
        """Every response must carry a correlation ID matching the allowed charset."""
        client = TestClient(_make_app())
        for header_value in [None, "", "a" * 200, "bad\x00char", "ok-id"]:
            headers = {} if header_value is None else {"X-Correlation-ID": header_value}
            resp = client.get("/ping", headers=headers)
            cid = resp.headers.get("X-Correlation-ID", "")
            assert cid, f"Missing X-Correlation-ID for input {header_value!r}"
            assert _VALID_RE.fullmatch(cid), f"Unsafe correlation ID {cid!r} for input {header_value!r}"
