# GitHub Token Scope Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate PAT and OAuth tokens have minimum required scopes (`read:user` + `repo`) before storing, reject insufficient tokens with HTTP 422, warn on overbroad tokens, and surface `scope_warnings` in API responses.

**Architecture:** Three layers: `GitHubAPIClient` gains `get_user_with_scopes()` (reads `X-GitHub-OAuthScopes` header) and `probe_repository_access()` (probes fine-grained PATs); `ManageGitHubIntegrationUseCase.validate_and_store()` runs scope checks and returns `(row, scope_warnings)`; API layer adds `scope_warnings` to response models, emits 422 for `InsufficientScopeError`, and updates device flow requested scopes.

**Tech Stack:** Python 3.13+, httpx, respx, FastAPI, SQLAlchemy 2.0 async, pydantic, pytest, pytest-asyncio.

---

### Task 1: Add `InsufficientScopeError` exception

**Files:**
- Modify: `app/adapters/github/exceptions.py`
- Create: `tests/adapters/github/test_scope_validation.py`

- [ ] **Step 1: Write the failing test**

Create `tests/adapters/github/test_scope_validation.py`:

```python
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
```

- [ ] **Step 2: Run to verify it fails**

```
pytest tests/adapters/github/test_scope_validation.py::test_insufficient_scope_error_is_invalid_token_error -v
```

Expected: `ImportError: cannot import name 'InsufficientScopeError'`

- [ ] **Step 3: Implement `InsufficientScopeError`**

Add to `app/adapters/github/exceptions.py` after `InvalidGitHubTokenError`:

```python
class InsufficientScopeError(InvalidGitHubTokenError):
    def __init__(self, missing_scopes: list[str]) -> None:
        self.missing_scopes = missing_scopes
        scopes_str = ", ".join(missing_scopes)
        super().__init__(
            f"Token is missing required scopes: {scopes_str}. "
            "Ratatoskr requires read:user and repo."
        )
```

- [ ] **Step 4: Run to verify it passes**

```
pytest tests/adapters/github/test_scope_validation.py::test_insufficient_scope_error_is_invalid_token_error -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/adapters/github/exceptions.py tests/adapters/github/test_scope_validation.py
git commit -m "feat(github): add InsufficientScopeError for missing required scopes"
```

---

### Task 2: Add `get_user_with_scopes()` and `probe_repository_access()` to `GitHubAPIClient`

**Files:**
- Modify: `app/adapters/github/github_api_client.py`
- Modify: `tests/adapters/github/test_scope_validation.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/adapters/github/test_scope_validation.py` (add these imports at the top of the file, before the existing import block):

```python
import respx
from httpx import Response

from app.adapters.github.github_api_client import GitHubAPIClient
```

Then append these test functions at the bottom:

```python
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
```

- [ ] **Step 2: Run to verify they fail**

```
pytest tests/adapters/github/test_scope_validation.py -k "get_user_with_scopes or probe_repository" -v
```

Expected: `AttributeError: 'GitHubAPIClient' object has no attribute 'get_user_with_scopes'`

- [ ] **Step 3: Implement both methods**

In `app/adapters/github/github_api_client.py`, add after `get_authenticated_user()`:

```python
async def get_user_with_scopes(self) -> tuple[AuthenticatedUserDTO, list[str]]:
    """GET /user and return (user, scopes).

    Reads X-GitHub-OAuthScopes response header. GitHub omits this header for
    fine-grained PATs, so an empty list signals a fine-grained PAT.
    """
    response = await self._request("GET", "/user")
    user = AuthenticatedUserDTO.model_validate(response.json())
    raw = response.headers.get("X-GitHub-OAuthScopes", "").strip()
    if not raw:
        return user, []
    scopes = [s.strip() for s in raw.split(",") if s.strip()]
    return user, scopes

async def probe_repository_access(self) -> bool:
    """GET /user/starred?per_page=1 to test repository-read capability.

    Returns True on 200, False on 403. Used for fine-grained PAT validation
    because scope names are opaque for those tokens.
    """
    try:
        await self._request("GET", "/user/starred", params={"per_page": "1"})
        return True
    except GitHubAuthError:
        return False
```

`GitHubAuthError` is already imported at the top of the file.

- [ ] **Step 4: Run to verify they pass**

```
pytest tests/adapters/github/test_scope_validation.py -k "get_user_with_scopes or probe_repository" -v
```

Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add app/adapters/github/github_api_client.py tests/adapters/github/test_scope_validation.py
git commit -m "feat(github): add get_user_with_scopes and probe_repository_access to GitHubAPIClient"
```

---

### Task 3: Scope validation in `validate_and_store()` + 7 unit tests

**Files:**
- Modify: `app/application/use_cases/manage_github_integration.py`
- Modify: `tests/adapters/github/test_scope_validation.py`
- Modify: `tests/api/test_github_auth_pat.py` (fix existing test broken by return-type change)

- [ ] **Step 1: Write 7 failing unit tests**

Add these imports to the top of `tests/adapters/github/test_scope_validation.py` (merge with existing imports):

```python
from unittest.mock import AsyncMock, MagicMock, patch

from app.adapters.github.exceptions import InsufficientScopeError
from app.adapters.github.types import AuthenticatedUserDTO
from app.application.use_cases.manage_github_integration import ManageGitHubIntegrationUseCase
from app.db.models.repository import GitHubAuthMethod
```

Append these helper functions and tests to `tests/adapters/github/test_scope_validation.py`:

```python
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
```

- [ ] **Step 2: Run to verify they fail**

```
pytest tests/adapters/github/test_scope_validation.py -k "classic_pat or fine_grained" -v
```

Expected: failures (TypeError on return-value unpacking or missing scope checks)

- [ ] **Step 3: Rewrite `app/application/use_cases/manage_github_integration.py`**

Full replacement — scope constants go at module level, `validate_and_store` returns `tuple[UserGitHubIntegration, list[str]]`:

```python
"""Use case: manage a user's GitHub integration (PAT / OAuth Device Flow)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

from sqlalchemy import func, select

from app.adapters.github.exceptions import (
    GitHubAuthError,
    InsufficientScopeError,
    InvalidGitHubTokenError,
)
from app.adapters.github.github_api_client import GitHubAPIClient
from app.core.logging_utils import get_logger
from app.db.models.repository import (
    GitHubAuthMethod,
    GitHubIntegrationStatus as GitHubIntegrationStatusEnum,
    Repository,
    UserGitHubIntegration,
)
from app.security.token_crypto import encrypt_token

if TYPE_CHECKING:
    from app.db.session import Database

logger = get_logger(__name__)

_REQUIRED_SCOPES: frozenset[str] = frozenset({"read:user", "repo"})
_KNOWN_SAFE_SCOPES: frozenset[str] = frozenset(
    {"read:user", "user:email", "repo", "public_repo", "read:org", "gist", "notifications"}
)
_OVERBROAD_SCOPES: dict[str, str] = {
    "admin:org": "token has org admin access — consider a narrower token",
    "admin:repo_hook": "token has webhook admin access — consider a narrower token",
    "delete_repo": "token can delete repositories — consider a narrower token",
    "write:packages": "token can publish packages — consider a narrower token",
    "admin:gpg_key": "token has GPG key admin access — consider a narrower token",
    "admin:public_key": "token has SSH key admin access — consider a narrower token",
}


def _collect_scope_warnings(scopes: list[str]) -> list[str]:
    """Raise InsufficientScopeError if required scopes missing; return overbroad warnings."""
    scope_set = set(scopes)
    missing = sorted(_REQUIRED_SCOPES - scope_set)
    if missing:
        raise InsufficientScopeError(missing_scopes=missing)
    warnings: list[str] = []
    for scope in scopes:
        if scope in _OVERBROAD_SCOPES:
            warnings.append(_OVERBROAD_SCOPES[scope])
        elif scope not in _KNOWN_SAFE_SCOPES:
            warnings.append(f"unrecognised scope '{scope}' — consider using a narrower token")
    return warnings


@dataclass(frozen=True)
class GitHubIntegrationStatus:
    """Read-model DTO returned by get_status."""

    is_connected: bool
    auth_method: GitHubAuthMethod | None
    github_login: str | None
    github_user_id: int | None
    status: GitHubIntegrationStatusEnum | None
    last_synced_at: datetime | None
    repo_count: int


class ManageGitHubIntegrationUseCase:
    """Validate, store, query, and revoke a user's GitHub integration token."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def validate_and_store(
        self,
        token: str,
        auth_method: GitHubAuthMethod,
        user_id: int,
        *,
        correlation_id: str,
    ) -> tuple[UserGitHubIntegration, list[str]]:
        """Validate token scopes, encrypt it, and upsert the integration row.

        Returns (integration_row, scope_warnings).

        Raises:
            InsufficientScopeError: token is missing required scopes.
            InvalidGitHubTokenError: GitHub rejected the token (401/403).
        """
        async with GitHubAPIClient(token) as gh:
            try:
                gh_user, scopes = await gh.get_user_with_scopes()
            except GitHubAuthError as exc:
                raise InvalidGitHubTokenError(f"Token rejected by GitHub: {exc}") from exc

            if not scopes:
                # Fine-grained PAT: scope names are opaque; probe capability instead
                if not await gh.probe_repository_access():
                    raise InsufficientScopeError(missing_scopes=["repository access"])
                token_scopes_value = "fine-grained"
                scope_warnings: list[str] = []
            else:
                scope_warnings = _collect_scope_warnings(scopes)
                token_scopes_value = ", ".join(scopes)

        encrypted = encrypt_token(token)

        async with self._db.transaction() as session:
            existing = await session.scalar(
                select(UserGitHubIntegration).where(UserGitHubIntegration.user_id == user_id)
            )
            if existing is None:
                row = UserGitHubIntegration(
                    user_id=user_id,
                    auth_method=auth_method,
                    encrypted_token=encrypted,
                    token_scopes=token_scopes_value,
                    github_login=gh_user.login,
                    github_user_id=gh_user.id,
                    status=GitHubIntegrationStatusEnum.ACTIVE,
                )
                session.add(row)
            else:
                existing.auth_method = auth_method
                existing.encrypted_token = encrypted
                existing.token_scopes = token_scopes_value
                existing.github_login = gh_user.login
                existing.github_user_id = gh_user.id
                existing.status = GitHubIntegrationStatusEnum.ACTIVE
                row = existing

            await session.flush()
            await session.refresh(row)

        logger.info(
            "github_integration_connected",
            extra={
                "correlation_id": correlation_id,
                "user_id": user_id,
                "auth_method": auth_method.value,
                "github_login": gh_user.login,
            },
        )
        return row, scope_warnings

    async def get_status(self, user_id: int) -> GitHubIntegrationStatus:
        """Return current integration status DTO. is_connected=False when no row exists."""
        async with self._db.session() as session:
            row = await session.scalar(
                select(UserGitHubIntegration).where(UserGitHubIntegration.user_id == user_id)
            )
            if row is None:
                return GitHubIntegrationStatus(
                    is_connected=False,
                    auth_method=None,
                    github_login=None,
                    github_user_id=None,
                    status=None,
                    last_synced_at=None,
                    repo_count=0,
                )

            repo_count: int = (
                await session.scalar(
                    select(func.count())
                    .select_from(Repository)
                    .where(Repository.user_id == user_id)
                )
                or 0
            )

        return GitHubIntegrationStatus(
            is_connected=True,
            auth_method=row.auth_method,
            github_login=row.github_login,
            github_user_id=row.github_user_id,
            status=row.status,
            last_synced_at=row.last_synced_at,
            repo_count=repo_count,
        )

    async def revoke(self, user_id: int) -> None:
        """Delete the integration row (user revokes on github.com themselves)."""
        async with self._db.transaction() as session:
            row = await session.scalar(
                select(UserGitHubIntegration).where(UserGitHubIntegration.user_id == user_id)
            )
            if row is not None:
                await session.delete(row)
```

- [ ] **Step 4: Fix the broken existing test in `tests/api/test_github_auth_pat.py`**

`test_use_case_validate_and_store_idempotent` calls `validate_and_store` directly and assigns the result to `row1`, `row2`. That now unpacks as a tuple. Also add the scope header so the call succeeds. Replace the entire test (lines 235–258):

```python
async def test_use_case_validate_and_store_idempotent(db: Database, gh_user: Any) -> None:
    use_case = ManageGitHubIntegrationUseCase(db)
    token = "ghp_idempotent_token_abc123"

    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://api.github.com/user").mock(
            return_value=Response(
                200,
                json=_GH_USER_PAYLOAD,
                headers={"X-GitHub-OAuthScopes": "repo, read:user"},
            )
        )
        row1, _ = await use_case.validate_and_store(
            token, GitHubAuthMethod.PAT, _USER_ID, correlation_id="cid-1"
        )
        row2, _ = await use_case.validate_and_store(
            token, GitHubAuthMethod.PAT, _USER_ID, correlation_id="cid-2"
        )

    async with db.session() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(UserGitHubIntegration)
            .where(UserGitHubIntegration.user_id == _USER_ID)
        )

    assert count == 1
    assert row1.github_login == row2.github_login == "gh-test-user"
```

- [ ] **Step 5: Run the 7 new unit tests**

```
pytest tests/adapters/github/test_scope_validation.py -k "classic_pat or fine_grained" -v
```

Expected: 7 PASS

- [ ] **Step 6: Run the full scope-validation test file**

```
pytest tests/adapters/github/test_scope_validation.py -v
```

Expected: 12 PASS (1 exception + 4 client methods + 7 use-case)

- [ ] **Step 7: Commit**

```bash
git add app/application/use_cases/manage_github_integration.py \
        tests/adapters/github/test_scope_validation.py \
        tests/api/test_github_auth_pat.py
git commit -m "feat(github): scope validation in validate_and_store; return scope_warnings"
```

---

### Task 4: API layer — response models, 422 handler, device flow scope, 3 integration tests

**Files:**
- Modify: `app/api/routers/auth/github.py`
- Modify: `tests/api/test_github_auth_pat.py`

- [ ] **Step 1: Write 3 failing integration tests**

Append to `tests/api/test_github_auth_pat.py`:

```python
# ---------------------------------------------------------------------------
# 9. token_scopes column populated after PAT submit
# ---------------------------------------------------------------------------


async def test_pat_stores_token_scopes(
    client: Any, db: Database, gh_user: Any
) -> None:
    """Successful PAT → UserGitHubIntegration.token_scopes populated."""
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://api.github.com/user").mock(
            return_value=Response(
                200,
                json=_GH_USER_PAYLOAD,
                headers={"X-GitHub-OAuthScopes": "repo, read:user"},
            )
        )
        resp = client.post(
            "/v1/auth/github/pat",
            json={"token": "ghp_scope_test_token_abcdef"},
            headers=_auth_headers(),
        )

    assert resp.status_code == 200

    async with db.session() as session:
        row = await session.scalar(
            select(UserGitHubIntegration).where(UserGitHubIntegration.user_id == _USER_ID)
        )
    assert row is not None
    assert row.token_scopes is not None
    assert "repo" in row.token_scopes


# ---------------------------------------------------------------------------
# 10. scope_warnings returned in response for overbroad token
# ---------------------------------------------------------------------------


async def test_pat_scope_warnings_in_response(
    client: Any, db: Database, gh_user: Any
) -> None:
    """Overbroad token → 200 with scope_warnings list."""
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://api.github.com/user").mock(
            return_value=Response(
                200,
                json=_GH_USER_PAYLOAD,
                headers={"X-GitHub-OAuthScopes": "repo, read:user, delete_repo"},
            )
        )
        resp = client.post(
            "/v1/auth/github/pat",
            json={"token": "ghp_overbroad_token_abcdef"},
            headers=_auth_headers(),
        )

    assert resp.status_code == 200
    body = resp.json()
    assert "scope_warnings" in body
    assert isinstance(body["scope_warnings"], list)
    assert len(body["scope_warnings"]) == 1
    assert "delete repositories" in body["scope_warnings"][0]


# ---------------------------------------------------------------------------
# 11. Insufficient scope → 422
# ---------------------------------------------------------------------------


async def test_pat_insufficient_scope_returns_422(
    client: Any, db: Database, gh_user: Any
) -> None:
    """Token with public_repo but not repo → 422 Unprocessable Entity."""
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://api.github.com/user").mock(
            return_value=Response(
                200,
                json=_GH_USER_PAYLOAD,
                headers={"X-GitHub-OAuthScopes": "read:user, public_repo"},
            )
        )
        resp = client.post(
            "/v1/auth/github/pat",
            json={"token": "ghp_narrow_token_abcdef"},
            headers=_auth_headers(),
        )

    assert resp.status_code == 422
    assert "repo" in resp.json()["detail"]
```

- [ ] **Step 2: Run to verify they fail**

```
pytest tests/api/test_github_auth_pat.py -k "test_pat_stores_token_scopes or test_pat_scope_warnings or test_pat_insufficient" -v
```

Expected: failures (`scope_warnings` not in response; 422 not returned)

- [ ] **Step 3: Update `app/api/routers/auth/github.py`**

**a) Update the import line for exceptions:**

Replace:
```python
from app.adapters.github.exceptions import InvalidGitHubTokenError
```
With:
```python
from app.adapters.github.exceptions import InsufficientScopeError, InvalidGitHubTokenError
```

**b) Add `scope_warnings` field to `PATSubmitResponse`:**

Replace:
```python
class PATSubmitResponse(BaseModel):
    login: str
    github_user_id: int
    auth_method: str
    status: str
```
With:
```python
class PATSubmitResponse(BaseModel):
    login: str
    github_user_id: int
    auth_method: str
    status: str
    scope_warnings: list[str] | None = None
```

**c) Add `scope_warnings` field to `DeviceFlowPollResponse`:**

Replace:
```python
class DeviceFlowPollResponse(BaseModel):
    status: Literal["pending", "slow_down", "expired", "ok", "denied"]
    login: str | None = None
    github_user_id: int | None = None
    auth_method: str | None = None
    integration_status: str | None = None
```
With:
```python
class DeviceFlowPollResponse(BaseModel):
    status: Literal["pending", "slow_down", "expired", "ok", "denied"]
    login: str | None = None
    github_user_id: int | None = None
    auth_method: str | None = None
    integration_status: str | None = None
    scope_warnings: list[str] | None = None
```

**d) Update `submit_pat` handler body** — unpack tuple return, catch `InsufficientScopeError` first:

Replace:
```python
    try:
        integration = await use_case.validate_and_store(
            body.token,
            GitHubAuthMethod.PAT,
            user["user_id"],
            correlation_id=correlation_id,
        )
    except InvalidGitHubTokenError as exc:
        raise HTTPException(status_code=400, detail="Invalid or revoked GitHub token") from exc
    return PATSubmitResponse(
        login=integration.github_login,
        github_user_id=integration.github_user_id,
        auth_method="pat",
        status="active",
    )
```
With:
```python
    try:
        integration, scope_warnings = await use_case.validate_and_store(
            body.token,
            GitHubAuthMethod.PAT,
            user["user_id"],
            correlation_id=correlation_id,
        )
    except InsufficientScopeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except InvalidGitHubTokenError as exc:
        raise HTTPException(status_code=400, detail="Invalid or revoked GitHub token") from exc
    return PATSubmitResponse(
        login=integration.github_login,
        github_user_id=integration.github_user_id,
        auth_method="pat",
        status="active",
        scope_warnings=scope_warnings or None,
    )
```

**e) Update device flow requested scope** in `device_flow_start`:

Replace:
```python
            data={"client_id": client_id, "scope": "read:user public_repo"},
```
With:
```python
            data={"client_id": client_id, "scope": "read:user repo"},
```

**f) Update `device_flow_poll` success block** — unpack tuple, propagate `scope_warnings`:

Replace:
```python
    integration = await use_case.validate_and_store(
        access_token,
        GitHubAuthMethod.OAUTH_DEVICE,
        user["user_id"],
        correlation_id=correlation_id,
    )

    return DeviceFlowPollResponse(
        status="ok",
        login=integration.github_login,
        github_user_id=integration.github_user_id,
        auth_method="oauth_device",
        integration_status="active",
    )
```
With:
```python
    integration, scope_warnings = await use_case.validate_and_store(
        access_token,
        GitHubAuthMethod.OAUTH_DEVICE,
        user["user_id"],
        correlation_id=correlation_id,
    )

    return DeviceFlowPollResponse(
        status="ok",
        login=integration.github_login,
        github_user_id=integration.github_user_id,
        auth_method="oauth_device",
        integration_status="active",
        scope_warnings=scope_warnings or None,
    )
```

- [ ] **Step 4: Fix existing tests that mock `/user` without a scope header**

In `tests/api/test_github_auth_pat.py`, add `headers={"X-GitHub-OAuthScopes": "repo, read:user"}` to the `/user` mock in:

- `test_post_pat_with_valid_token_stores_encrypted` (line ~83)
- `test_token_not_logged` (line ~272)

These two tests mock a successful `/user` response but without a scope header. After the change, the empty scope list triggers a `probe_repository_access()` call to `/user/starred` which has no mock — respx will raise. Adding the scope header makes them classic-PAT path and avoids the probe.

- [ ] **Step 5: Run the 3 new integration tests**

```
pytest tests/api/test_github_auth_pat.py -k "test_pat_stores_token_scopes or test_pat_scope_warnings or test_pat_insufficient" -v
```

Expected: 3 PASS

- [ ] **Step 6: Run the full PAT test file**

```
pytest tests/api/test_github_auth_pat.py -v
```

Expected: 11 PASS

- [ ] **Step 7: Run the full scope-validation test file**

```
pytest tests/adapters/github/test_scope_validation.py -v
```

Expected: 12 PASS

- [ ] **Step 8: Run full test suite to catch regressions**

```
pytest tests/ -x -q 2>&1 | tail -30
```

Expected: no new failures

- [ ] **Step 9: Commit**

```bash
git add app/api/routers/auth/github.py tests/api/test_github_auth_pat.py
git commit -m "feat(github): scope_warnings in API responses, 422 for InsufficientScopeError, update device flow scope"
```
