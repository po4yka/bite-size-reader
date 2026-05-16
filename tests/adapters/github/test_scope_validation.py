"""Unit tests for GitHub token scope validation — HTTP mocked via respx or patched."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from app.adapters.github.exceptions import InsufficientScopeError, InvalidGitHubTokenError
from app.adapters.github.github_api_client import GitHubAPIClient


def test_insufficient_scope_error_is_invalid_token_error() -> None:
    err = InsufficientScopeError(missing_scopes=["repo"])
    assert isinstance(err, InvalidGitHubTokenError)
    assert err.missing_scopes == ["repo"]
    assert "repo" in str(err)
    assert "read:user and repo" in str(err)


_GH_USER = {"id": 1, "login": "alice", "name": "Alice", "email": None, "type": "User"}
_USER_URL = "https://api.github.com/user"
_STARRED_URL = "https://api.github.com/user/starred"


def _client() -> GitHubAPIClient:
    return GitHubAPIClient("ghp_test", backoff_min_sec=0.0, backoff_max_sec=0.0)


@pytest.mark.asyncio
async def test_get_user_with_scopes_classic_pat() -> None:
    """X-GitHub-OAuthScopes header present → parsed scope list."""
    with respx.mock:
        respx.get(_USER_URL).mock(
            return_value=Response(
                200,
                json=_GH_USER,
                headers={"X-GitHub-OAuthScopes": "repo, read:user"},
            )
        )
        async with _client() as gh:
            user, scopes = await gh.get_user_with_scopes()

    assert user.login == "alice"
    assert set(scopes) == {"repo", "read:user"}


@pytest.mark.asyncio
async def test_get_user_with_scopes_fine_grained_pat() -> None:
    """No X-GitHub-OAuthScopes header → empty list (fine-grained PAT signal)."""
    with respx.mock:
        respx.get(_USER_URL).mock(return_value=Response(200, json=_GH_USER))
        async with _client() as gh:
            user, scopes = await gh.get_user_with_scopes()

    assert user.login == "alice"
    assert scopes == []


@pytest.mark.asyncio
async def test_probe_repository_access_true_on_200() -> None:
    with respx.mock:
        respx.get(_STARRED_URL).mock(return_value=Response(200, json=[]))
        async with _client() as gh:
            result = await gh.probe_repository_access()

    assert result is True


@pytest.mark.asyncio
async def test_probe_repository_access_false_on_403() -> None:
    with respx.mock:
        respx.get(_STARRED_URL).mock(return_value=Response(403, json={"message": "Forbidden"}))
        async with _client() as gh:
            result = await gh.probe_repository_access()

    assert result is False
