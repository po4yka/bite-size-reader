"""Unit tests for GitHub token scope validation — HTTP mocked via respx or patched."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import respx
from httpx import Response

from app.adapters.github.exceptions import InsufficientScopeError, InvalidGitHubTokenError
from app.adapters.github.github_api_client import GitHubAPIClient
from app.adapters.github.types import AuthenticatedUserDTO
from app.application.use_cases.manage_github_integration import ManageGitHubIntegrationUseCase
from app.db.models.repository import GitHubAuthMethod


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


# ---------------------------------------------------------------------------
# Use case unit tests (DB + GitHub client fully mocked)
# ---------------------------------------------------------------------------

_AUTH_USER = AuthenticatedUserDTO(id=1, login="alice")
_TOKEN = "ghp_fake_token_abc123456"
_UC_USER_ID = 42


def _mock_db() -> MagicMock:
    """Minimal DB mock for validate_and_store unit tests."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.scalar = AsyncMock(return_value=None)  # no existing row
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()

    db = MagicMock()
    db.transaction = MagicMock(return_value=session)
    return db


def _mock_gh(*, scopes: list[str], probe_result: bool = True) -> MagicMock:
    gh = AsyncMock()
    gh.__aenter__ = AsyncMock(return_value=gh)
    gh.__aexit__ = AsyncMock(return_value=False)
    gh.get_user_with_scopes = AsyncMock(return_value=(_AUTH_USER, scopes))
    gh.probe_repository_access = AsyncMock(return_value=probe_result)
    return gh


@pytest.mark.asyncio
async def test_classic_pat_sufficient_scopes() -> None:
    """repo + read:user → accepted, no warnings."""
    gh = _mock_gh(scopes=["repo", "read:user"])
    with (
        patch(
            "app.application.use_cases.manage_github_integration.GitHubAPIClient",
            return_value=gh,
        ),
        patch(
            "app.application.use_cases.manage_github_integration.encrypt_token",
            return_value=b"enc",
        ),
    ):
        uc = ManageGitHubIntegrationUseCase(_mock_db())
        _row, warnings = await uc.validate_and_store(
            _TOKEN, GitHubAuthMethod.PAT, _UC_USER_ID, correlation_id="cid"
        )

    assert warnings == []


@pytest.mark.asyncio
async def test_classic_pat_missing_repo_scope() -> None:
    """read:user + public_repo but no repo → InsufficientScopeError(missing=['repo'])."""
    gh = _mock_gh(scopes=["read:user", "public_repo"])
    with (
        patch(
            "app.application.use_cases.manage_github_integration.GitHubAPIClient",
            return_value=gh,
        ),
        patch(
            "app.application.use_cases.manage_github_integration.encrypt_token",
            return_value=b"enc",
        ),
    ):
        uc = ManageGitHubIntegrationUseCase(_mock_db())
        with pytest.raises(InsufficientScopeError) as exc_info:
            await uc.validate_and_store(
                _TOKEN, GitHubAuthMethod.PAT, _UC_USER_ID, correlation_id="cid"
            )

    assert exc_info.value.missing_scopes == ["repo"]


@pytest.mark.asyncio
async def test_classic_pat_missing_read_user() -> None:
    """repo only, no read:user → InsufficientScopeError(missing=['read:user'])."""
    gh = _mock_gh(scopes=["repo"])
    with (
        patch(
            "app.application.use_cases.manage_github_integration.GitHubAPIClient",
            return_value=gh,
        ),
        patch(
            "app.application.use_cases.manage_github_integration.encrypt_token",
            return_value=b"enc",
        ),
    ):
        uc = ManageGitHubIntegrationUseCase(_mock_db())
        with pytest.raises(InsufficientScopeError) as exc_info:
            await uc.validate_and_store(
                _TOKEN, GitHubAuthMethod.PAT, _UC_USER_ID, correlation_id="cid"
            )

    assert exc_info.value.missing_scopes == ["read:user"]


@pytest.mark.asyncio
async def test_classic_pat_overbroad_delete_repo() -> None:
    """repo + read:user + delete_repo → accepted with one warning."""
    gh = _mock_gh(scopes=["repo", "read:user", "delete_repo"])
    with (
        patch(
            "app.application.use_cases.manage_github_integration.GitHubAPIClient",
            return_value=gh,
        ),
        patch(
            "app.application.use_cases.manage_github_integration.encrypt_token",
            return_value=b"enc",
        ),
    ):
        uc = ManageGitHubIntegrationUseCase(_mock_db())
        _row, warnings = await uc.validate_and_store(
            _TOKEN, GitHubAuthMethod.PAT, _UC_USER_ID, correlation_id="cid"
        )

    assert len(warnings) == 1
    assert "delete repositories" in warnings[0]


@pytest.mark.asyncio
async def test_classic_pat_unknown_scope() -> None:
    """repo + read:user + unknown custom:scope → accepted with generic warning."""
    gh = _mock_gh(scopes=["repo", "read:user", "custom:scope"])
    with (
        patch(
            "app.application.use_cases.manage_github_integration.GitHubAPIClient",
            return_value=gh,
        ),
        patch(
            "app.application.use_cases.manage_github_integration.encrypt_token",
            return_value=b"enc",
        ),
    ):
        uc = ManageGitHubIntegrationUseCase(_mock_db())
        _row, warnings = await uc.validate_and_store(
            _TOKEN, GitHubAuthMethod.PAT, _UC_USER_ID, correlation_id="cid"
        )

    assert len(warnings) == 1
    assert "custom:scope" in warnings[0]
    assert "unrecognised" in warnings[0]


@pytest.mark.asyncio
async def test_fine_grained_probe_succeeds() -> None:
    """Empty scope header + probe 200 → accepted, token_scopes='fine-grained'."""
    gh = _mock_gh(scopes=[], probe_result=True)
    db = _mock_db()
    with (
        patch(
            "app.application.use_cases.manage_github_integration.GitHubAPIClient",
            return_value=gh,
        ),
        patch(
            "app.application.use_cases.manage_github_integration.encrypt_token",
            return_value=b"enc",
        ),
    ):
        uc = ManageGitHubIntegrationUseCase(db)
        _row, warnings = await uc.validate_and_store(
            _TOKEN, GitHubAuthMethod.PAT, _UC_USER_ID, correlation_id="cid"
        )

    gh.probe_repository_access.assert_awaited_once()
    session = db.transaction.return_value
    added_row = session.add.call_args[0][0]
    assert added_row.token_scopes == "fine-grained"
    assert warnings == []


@pytest.mark.asyncio
async def test_fine_grained_probe_fails() -> None:
    """Empty scope header + probe 403 → InsufficientScopeError."""
    gh = _mock_gh(scopes=[], probe_result=False)
    with (
        patch(
            "app.application.use_cases.manage_github_integration.GitHubAPIClient",
            return_value=gh,
        ),
        patch(
            "app.application.use_cases.manage_github_integration.encrypt_token",
            return_value=b"enc",
        ),
    ):
        uc = ManageGitHubIntegrationUseCase(_mock_db())
        with pytest.raises(InsufficientScopeError):
            await uc.validate_and_store(
                _TOKEN, GitHubAuthMethod.PAT, _UC_USER_ID, correlation_id="cid"
            )

    gh.probe_repository_access.assert_awaited_once()
