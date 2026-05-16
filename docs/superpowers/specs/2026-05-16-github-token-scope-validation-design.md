# GitHub Token Scope Validation Design

**Date:** 2026-05-16
**Status:** Approved

## Goal

Validate PAT and OAuth tokens have the minimum required GitHub scopes before encrypting and storing them. Reject insufficient tokens with a clear error. Warn (but accept) overbroad tokens. Populate the existing `token_scopes` column on `UserGitHubIntegration`.

## Acceptance Criteria

- Invalid/insufficient GitHub tokens are rejected before encryption or storage.
- Stored integration records include observed scopes when available.
- API responses include `scope_warnings` when a token has more access than needed.

---

## Architecture

Three layers are touched, each with one clear responsibility:

### 1. `GitHubAPIClient` (`app/adapters/github/github_api_client.py`)

Add two methods:

**`get_user_with_scopes() -> tuple[AuthenticatedUserDTO, list[str]]`**
- Calls `GET /user`
- Reads `X-GitHub-OAuthScopes` response header (comma-space separated)
- Returns `(user_dto, scopes)` where `scopes` is an empty list for fine-grained PATs
- Existing `get_authenticated_user()` is preserved unchanged for backward compatibility

**`probe_repository_access() -> bool`**
- Calls `GET /user/starred?per_page=1`
- Returns `True` on 200, `False` on 403
- Used only for fine-grained PAT validation

### 2. `ManageGitHubIntegrationUseCase` (`app/application/use_cases/manage_github_integration.py`)

`validate_and_store()` is updated — validation runs in this order:

1. Call `get_user_with_scopes()` to get `(gh_user, scopes)`
2. Detect fine-grained PAT: `scopes == []` → call `probe_repository_access()`; reject if probe fails
3. Validate classic PAT scopes against required set; raise `InsufficientScopeError` if missing
4. Collect overbroad-scope warnings for classic PATs
5. Encrypt token, store integration row with `token_scopes` populated
6. Return `(integration_row, scope_warnings)`

### 3. API Layer (`app/api/routers/auth/github.py`)

- `POST /v1/auth/github/pat` response gains `scope_warnings: list[str] | None`
- `POST /v1/auth/github/device/poll` response gains `scope_warnings: list[str] | None`
- Device Flow hardcoded scopes updated from `"read:user public_repo"` → `"read:user repo"`
- `GET /v1/auth/github/status` is unchanged (`token_scopes` is internal only)

---

## Scope Definitions and Validation Rules

### Minimum Required Scopes (Classic PATs)

| Scope | Purpose |
|---|---|
| `read:user` | Call `GET /user` to validate the token |
| `repo` | Read public and private repository data (starred sync, ingestion) |

`repo` subsumes `public_repo`. A token with only `public_repo` is rejected — private repository access requires `repo`.

### Fine-Grained PATs

Detected by an absent or empty `X-GitHub-OAuthScopes` response header (GitHub omits the header entirely for fine-grained PATs). Scope names are opaque; capability is determined by probing:

- `GET /user/starred?per_page=1` returning 200 → accept, store `token_scopes = "fine-grained"`
- `GET /user/starred?per_page=1` returning 403 → reject with `InsufficientScopeError`

### Known-Safe Scope Allowlist

Scopes that do not produce warnings: `read:user`, `user:email`, `repo`, `public_repo`, `read:org`, `gist`, `notifications`.

### Overbroad Scopes (warn, do not reject)

| Scope | Warning message |
|---|---|
| `admin:org` | "token has org admin access — consider a narrower token" |
| `admin:repo_hook` | "token has webhook admin access — consider a narrower token" |
| `delete_repo` | "token can delete repositories — consider a narrower token" |
| `write:packages` | "token can publish packages — consider a narrower token" |
| `admin:gpg_key` | "token has GPG key admin access — consider a narrower token" |
| `admin:public_key` | "token has SSH key admin access — consider a narrower token" |

Any scope not in the known-safe list and not in the overbroad list above produces a generic warning: `"unrecognised scope '<scope>' — consider using a narrower token"`.

### `token_scopes` Storage Format

| Token type | Stored value |
|---|---|
| Classic PAT | Raw header string, e.g. `"repo, read:user"` |
| Fine-grained PAT (probe passes) | `"fine-grained"` |
| OAuth Device Flow | Scopes granted by GitHub, from `X-GitHub-OAuthScopes` header |

Column is `String(500)` — sufficient for any realistic scope list.

---

## New Exception

**`InsufficientScopeError(InvalidGitHubTokenError)`** in `app/adapters/github/exceptions.py`

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

Inherits from `InvalidGitHubTokenError`, which is already mapped to HTTP 422 at the API layer — no new HTTP error mapping needed.

---

## API Contract

### `POST /v1/auth/github/pat` — success response

```json
{
  "github_login": "npochaev",
  "github_user_id": 12345,
  "auth_method": "pat",
  "status": "active",
  "scope_warnings": ["token can delete repositories — consider a narrower token"]
}
```

`scope_warnings` is `null` when no warnings are present.

### `POST /v1/auth/github/pat` — rejection (422 Unprocessable Entity)

```json
{
  "detail": "Token is missing required scopes: repo. Ratatoskr requires read:user and repo."
}
```

### `POST /v1/auth/github/device/poll` — same `scope_warnings` field added

No change to shape otherwise.

---

## Testing Plan

### New file: `tests/adapters/github/test_scope_validation.py`

Unit tests for the scope validation logic, all GitHub HTTP calls mocked via `respx`:

| Test | Mock setup | Expected outcome |
|---|---|---|
| `test_classic_pat_sufficient_scopes` | `X-GitHub-OAuthScopes: "repo, read:user"` | Accept, no warnings |
| `test_classic_pat_missing_repo_scope` | `X-GitHub-OAuthScopes: "read:user, public_repo"` | `InsufficientScopeError(missing=["repo"])` |
| `test_classic_pat_missing_read_user` | `X-GitHub-OAuthScopes: "repo"` | `InsufficientScopeError(missing=["read:user"])` |
| `test_classic_pat_overbroad_delete_repo` | `X-GitHub-OAuthScopes: "repo, read:user, delete_repo"` | Accept, warning for `delete_repo` |
| `test_classic_pat_unknown_scope` | `X-GitHub-OAuthScopes: "repo, read:user, custom:scope"` | Accept, generic unknown-scope warning |
| `test_fine_grained_probe_succeeds` | Empty scope header + `GET /user/starred` → 200 | Accept, `token_scopes="fine-grained"` |
| `test_fine_grained_probe_fails` | Empty scope header + `GET /user/starred` → 403 | `InsufficientScopeError` |

### Extended `tests/api/test_github_auth_pat.py`

| Test | What it verifies |
|---|---|
| `test_pat_stores_token_scopes` | `UserGitHubIntegration.token_scopes` populated after successful submit |
| `test_pat_scope_warnings_in_response` | API response body includes `scope_warnings` list for overbroad token |
| `test_pat_insufficient_scope_returns_422` | HTTP 422, detail lists missing scopes |

---

## Files Changed

| Action | File | Change |
|---|---|---|
| Modify | `app/adapters/github/github_api_client.py` | Add `get_user_with_scopes()` and `probe_repository_access()` |
| Modify | `app/adapters/github/exceptions.py` | Add `InsufficientScopeError` |
| Modify | `app/application/use_cases/manage_github_integration.py` | Scope validation in `validate_and_store()`; return warnings |
| Modify | `app/api/routers/auth/github.py` | Add `scope_warnings` to response models; update Device Flow scopes |
| Create | `tests/adapters/github/test_scope_validation.py` | 7 unit tests |
| Modify | `tests/api/test_github_auth_pat.py` | 3 new integration tests |

No new database migrations — `token_scopes` column already exists.
