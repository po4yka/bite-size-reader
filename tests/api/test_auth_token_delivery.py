"""Tests for refresh-token delivery policy: web cookie vs mobile/CLI body."""
from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    ("client_id", "expected"),
    [
        ("webapp", True),
        ("web-frontend", True),
        ("mobile-ios", False),
        ("mobile-android", False),
        ("cli-1", False),
        ("mcp-server", False),
        ("automation-script", False),
        ("foobar", False),
        (None, False),
    ],
)
def test_is_web_client(client_id, expected):
    from app.api.routers.auth.tokens import is_web_client

    assert is_web_client(client_id) is expected
