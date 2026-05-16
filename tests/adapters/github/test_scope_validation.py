"""Unit tests for GitHub token scope validation — HTTP mocked via respx or patched."""

from __future__ import annotations

import pytest

from app.adapters.github.exceptions import InsufficientScopeError, InvalidGitHubTokenError


def test_insufficient_scope_error_is_invalid_token_error() -> None:
    err = InsufficientScopeError(missing_scopes=["repo"])
    assert isinstance(err, InvalidGitHubTokenError)
    assert err.missing_scopes == ["repo"]
    assert "repo" in str(err)
    assert "read:user and repo" in str(err)
