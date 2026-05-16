# Refresh-Token Delivery Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Web clients receive the refresh token only via an httpOnly cookie (body has `null`); mobile/CLI clients receive it in the response body with no cookie set.

**Architecture:** A thin `is_web_client(client_id)` helper wraps the existing `resolve_client_type()` in `tokens.py`. Each of the four token-issuing endpoints (`/credentials-login`, `/telegram-login`, `/secret-login`, `/refresh`) branches on this to decide cookie vs body delivery. No schema changes — `TokenPair.refresh_token` is already `str | None`.

**Tech Stack:** Python, FastAPI/Starlette, PyJWT, pytest, `unittest.mock`

**Spec:** `docs/superpowers/specs/2026-05-16-refresh-token-delivery-design.md`

---

## File Map

| File | Change |
|---|---|
| `app/api/routers/auth/tokens.py` | Add `is_web_client()` after `is_self_service_secret_client` |
| `app/api/routers/auth/endpoints_credentials.py` | Branch on `is_web_client` for cookie + body |
| `app/api/routers/auth/endpoints_telegram.py` | Branch on `is_web_client` for cookie + body |
| `app/api/routers/auth/endpoints_secret_keys.py` | Branch on `is_web_client` for cookie + body |
| `app/api/routers/auth/endpoints_sessions.py` | Branch on `is_web_client` for cookie + body in `/refresh` |
| `tests/api/test_auth_token_delivery.py` | **Create** — all delivery policy tests |

---

## Task 1: `is_web_client()` helper

**Files:**
- Modify: `app/api/routers/auth/tokens.py`
- Create: `tests/api/test_auth_token_delivery.py`

- [ ] **Step 1: Create test file with failing unit tests**

```python
# tests/api/test_auth_token_delivery.py
"""Tests for refresh-token delivery policy: web cookie vs mobile/CLI body."""
from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    "client_id,expected",
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
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/api/test_auth_token_delivery.py::test_is_web_client -v
```
Expected: `ImportError: cannot import name 'is_web_client'`

- [ ] **Step 3: Add `is_web_client()` to `tokens.py`**

Open `app/api/routers/auth/tokens.py`. After `is_self_service_secret_client` (around line 295), add:

```python
def is_web_client(client_id: str | None) -> bool:
    """Return True when the client expects cookie-only refresh token delivery."""
    return resolve_client_type(client_id) == "web"
```

- [ ] **Step 4: Run to verify pass**

```bash
pytest tests/api/test_auth_token_delivery.py::test_is_web_client -v
```
Expected: 9 PASSED

- [ ] **Step 5: Commit**

```bash
git add app/api/routers/auth/tokens.py tests/api/test_auth_token_delivery.py
git commit -m "feat(auth): add is_web_client() helper for refresh-token delivery policy"
```

---

## Task 2: Delivery policy for login endpoints

**Files:**
- Modify: `app/api/routers/auth/endpoints_credentials.py`
- Modify: `app/api/routers/auth/endpoints_telegram.py`
- Modify: `app/api/routers/auth/endpoints_secret_keys.py`
- Modify: `tests/api/test_auth_token_delivery.py`

- [ ] **Step 1: Add failing delivery tests to `tests/api/test_auth_token_delivery.py`**

Append below the existing `test_is_web_client` test (keep the existing imports at the top of the file):

```python
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# /credentials-login
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_id,expect_cookie,expect_body_token",
    [
        ("webapp", True, False),
        ("mobile-ios", False, True),
    ],
)
async def test_credentials_login_token_delivery(client_id, expect_cookie, expect_body_token):
    from app.api.models.auth import CredentialsLoginRequest
    from app.api.routers.auth.endpoints_credentials import credentials_login

    response = MagicMock()
    payload = CredentialsLoginRequest(
        identifier="testuser",
        password="TestPass123!",
        client_id=client_id,
        remember_me=True,
    )

    mock_cred_repo = AsyncMock()
    mock_cred_repo.async_get_by_canonical = AsyncMock(
        return_value={
            "id": 1,
            "user_id": 123,
            "password_hash": "phc",
            "pepper_version": 1,
            "failed_attempts": 0,
            "locked_until": None,
        }
    )
    mock_cred_repo.async_reset_failure = AsyncMock()
    mock_cred_repo.async_touch_last_login = AsyncMock()

    mock_user_repo = AsyncMock()
    mock_user_repo.async_get_user_by_telegram_id = AsyncMock(
        return_value={"telegram_user_id": 123, "username": "testuser"}
    )

    mock_cfg = MagicMock()
    mock_cfg.auth.credentials_remember_me_days = 30
    mock_cfg.auth.credentials_no_remember_hours = 12

    with (
        patch("app.api.routers.auth.endpoints_credentials.validate_client_id"),
        patch("app.api.routers.auth.endpoints_credentials.validate_password"),
        patch("app.api.routers.auth.endpoints_credentials.ensure_user_allowed"),
        patch(
            "app.api.routers.auth.endpoints_credentials.verify_password",
            return_value=(True, False),
        ),
        patch(
            "app.api.routers.auth.endpoints_credentials.get_user_credential_repository",
            return_value=mock_cred_repo,
        ),
        patch(
            "app.api.routers.auth.endpoints_credentials.get_user_repository",
            return_value=mock_user_repo,
        ),
        patch(
            "app.api.routers.auth.endpoints_credentials.load_config",
            return_value=mock_cfg,
        ),
        patch(
            "app.api.routers.auth.endpoints_credentials.create_access_token",
            return_value="acc.tok",
        ),
        patch(
            "app.api.routers.auth.endpoints_credentials.create_refresh_token",
            new_callable=AsyncMock,
            return_value=("ref.tok", 42),
        ),
    ):
        result = await credentials_login(payload, response)

    tokens = result["data"]["tokens"]
    if expect_cookie:
        response.set_cookie.assert_called_once()
        assert tokens["refreshToken"] is None
    else:
        response.set_cookie.assert_not_called()
        assert tokens["refreshToken"] == "ref.tok"


# ---------------------------------------------------------------------------
# /telegram-login
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_id,expect_cookie,expect_body_token",
    [
        ("webapp", True, False),
        ("mobile-ios", False, True),
    ],
)
async def test_telegram_login_token_delivery(client_id, expect_cookie, expect_body_token):
    from app.api.models.auth import TelegramLoginRequest
    from app.api.routers.auth.endpoints_telegram import telegram_login

    response = MagicMock()
    payload = TelegramLoginRequest(
        telegram_user_id=123456789,
        auth_hash="abc123",
        auth_date=1700000000,
        client_id=client_id,
        username="testuser",
    )

    mock_user_repo = AsyncMock()
    mock_user_repo.async_get_or_create_user = AsyncMock(
        return_value=({"telegram_user_id": 123456789, "username": "testuser"}, False)
    )

    with (
        patch("app.api.routers.auth.endpoints_telegram.validate_client_id"),
        patch("app.api.routers.auth.endpoints_telegram.verify_telegram_auth"),
        patch(
            "app.api.routers.auth.endpoints_telegram.get_user_repository",
            return_value=mock_user_repo,
        ),
        patch(
            "app.api.routers.auth.endpoints_telegram.create_access_token",
            return_value="acc.tok",
        ),
        patch(
            "app.api.routers.auth.endpoints_telegram.create_refresh_token",
            new_callable=AsyncMock,
            return_value=("ref.tok", 42),
        ),
    ):
        result = await telegram_login(payload, response)

    tokens = result["data"]["tokens"]
    if expect_cookie:
        response.set_cookie.assert_called_once()
        assert tokens["refreshToken"] is None
    else:
        response.set_cookie.assert_not_called()
        assert tokens["refreshToken"] == "ref.tok"


# ---------------------------------------------------------------------------
# /secret-login
# NOTE: Before running, open endpoints_secret_keys.py and find what method
# the secret_login handler calls on auth_repo (search for `auth_repo.async_`).
# Update mock_auth_repo below to set that method's return_value instead.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_id,expect_cookie,expect_body_token",
    [
        ("webapp", True, False),
        ("cli-1", False, True),
    ],
)
async def test_secret_login_token_delivery(client_id, expect_cookie, expect_body_token):
    from app.api.routers.auth.endpoints_secret_keys import secret_login

    # SecretLoginRequest field for the secret value may be named `secret_key` or
    # `secret` — check app/api/models/auth.py and adjust if needed.
    from app.api.models.auth import SecretLoginRequest

    response = MagicMock()
    payload = SecretLoginRequest(
        client_id=client_id,
        secret_key="sk-test-value-here",
    )

    # AsyncMock auto-creates any attribute as an AsyncMock, so uncalled methods
    # return an AsyncMock (truthy). If the handler reads a dict field from the
    # return value (e.g. record["is_revoked"]), set the return_value explicitly.
    mock_auth_repo = AsyncMock()

    with (
        patch("app.api.routers.auth.endpoints_secret_keys.ensure_secret_login_enabled"),
        patch("app.api.routers.auth.endpoints_secret_keys.validate_client_id"),
        patch("app.api.routers.auth.endpoints_secret_keys.validate_secret_value"),
        patch(
            "app.api.routers.auth.endpoints_secret_keys.get_auth_repository",
            return_value=mock_auth_repo,
        ),
        patch(
            "app.api.routers.auth.endpoints_secret_keys.hash_secret",
            return_value="hashed",
        ),
        patch("app.api.routers.auth.endpoints_secret_keys.ensure_user_allowed"),
        patch(
            "app.api.routers.auth.endpoints_secret_keys.check_expired",
            return_value=False,
        ),
        patch(
            "app.api.routers.auth.endpoints_secret_keys.reset_failed_attempts",
            new_callable=AsyncMock,
        ),
        patch(
            "app.api.routers.auth.endpoints_secret_keys.create_access_token",
            return_value="acc.tok",
        ),
        patch(
            "app.api.routers.auth.endpoints_secret_keys.create_refresh_token",
            new_callable=AsyncMock,
            return_value=("ref.tok", 42),
        ),
    ):
        result = await secret_login(payload, response)

    tokens = result["data"]["tokens"]
    if expect_cookie:
        response.set_cookie.assert_called_once()
        assert tokens["refreshToken"] is None
    else:
        response.set_cookie.assert_not_called()
        assert tokens["refreshToken"] == "ref.tok"
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/api/test_auth_token_delivery.py -k "login_token_delivery" -v
```
Expected: 6 tests FAIL (endpoints still return token in body and always set cookie)

- [ ] **Step 3: Apply delivery pattern to `/credentials-login`**

Open `app/api/routers/auth/endpoints_credentials.py`.

Add `is_web_client` to the existing tokens import (around line 37):

```python
from app.api.routers.auth.tokens import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    create_refresh_token,
    is_web_client,
    validate_client_id,
)
```

Find the block that calls `set_refresh_cookie` and builds `TokenPair` (around lines 180–187). Replace it with:

```python
    web = is_web_client(payload.client_id)
    if web:
        set_refresh_cookie(response, refresh_token, max_age=cookie_max_age)

    tokens = TokenPair(
        access_token=access_token,
        refresh_token=None if web else refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        token_type="Bearer",
    )
```

- [ ] **Step 4: Apply delivery pattern to `/telegram-login`**

Open `app/api/routers/auth/endpoints_telegram.py`.

Add `is_web_client` to the existing tokens import (around line 34):

```python
from app.api.routers.auth.tokens import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    create_refresh_token,
    is_web_client,
    validate_client_id,
)
```

Find the block that calls `set_refresh_cookie` and builds `TokenPair` (around lines 90–97). Replace it with:

```python
        web = is_web_client(login_data.client_id)
        if web:
            set_refresh_cookie(response, refresh_token)

        tokens = TokenPair(
            access_token=access_token,
            refresh_token=None if web else refresh_token,
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            token_type="Bearer",
        )
```

- [ ] **Step 5: Apply delivery pattern to `/secret-login`**

Open `app/api/routers/auth/endpoints_secret_keys.py`.

Add `is_web_client` to the existing tokens import (around line 47):

```python
from app.api.routers.auth.tokens import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    create_refresh_token,
    is_self_service_secret_client,
    is_web_client,
    validate_client_id,
)
```

Find the `set_refresh_cookie` call and the `TokenPair` block in `secret_login` (around lines 167–176). Replace with:

```python
    web = is_web_client(login_data.client_id)
    if web:
        set_refresh_cookie(response, refresh_token)

    tokens = TokenPair(
        access_token=access_token,
        refresh_token=None if web else refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        token_type="Bearer",
    )
```

- [ ] **Step 6: Run to verify pass**

```bash
pytest tests/api/test_auth_token_delivery.py -k "login_token_delivery" -v
```
Expected: 6 PASSED

If `test_secret_login_token_delivery` fails with an unexpected error (not an assertion error), read the failing traceback, find which `auth_repo` method is called in the `secret_login` handler, and mock that method explicitly on `mock_auth_repo`. Delivery-assertion failures mean the endpoint change in Step 5 is wrong — re-check the block you replaced.

- [ ] **Step 7: Commit**

```bash
git add app/api/routers/auth/endpoints_credentials.py \
        app/api/routers/auth/endpoints_telegram.py \
        app/api/routers/auth/endpoints_secret_keys.py \
        tests/api/test_auth_token_delivery.py
git commit -m "feat(auth): apply refresh-token delivery policy to login endpoints"
```

---

## Task 3: Delivery policy for `/refresh`

**Files:**
- Modify: `app/api/routers/auth/endpoints_sessions.py`
- Modify: `tests/api/test_auth_token_delivery.py`

- [ ] **Step 1: Add failing delivery tests to `tests/api/test_auth_token_delivery.py`**

Append at the end of the file (these use the real test DB like existing session tests):

```python
# ---------------------------------------------------------------------------
# /refresh — integration tests against real DB
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_id,expect_cookie,expect_body_token",
    [
        ("webapp", True, False),
        ("mobile-ios", False, True),
    ],
)
async def test_refresh_token_delivery(db, user_factory, client_id, expect_cookie, expect_body_token):
    from app.api.dependencies.database import get_auth_repository
    from app.api.models.auth import RefreshTokenRequest
    from app.api.routers.auth.endpoints_sessions import refresh_access_token
    from app.api.routers.auth.tokens import create_refresh_token

    user = await user_factory(telegram_user_id=999888777, username="delivery_test")
    token, _ = await create_refresh_token(
        user_id=user.telegram_user_id,
        client_id=client_id,
    )

    request = MagicMock()
    request.cookies = {}
    response = MagicMock()
    body = RefreshTokenRequest(refresh_token=token)
    auth_repo = get_auth_repository()

    result = await refresh_access_token(
        request=request,
        response=response,
        refresh_data=body,
        auth_repo=auth_repo,
    )

    tokens = result["data"]["tokens"]
    if expect_cookie:
        response.set_cookie.assert_called_once()
        assert tokens["refreshToken"] is None
    else:
        response.set_cookie.assert_not_called()
        assert tokens["refreshToken"] is not None
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/api/test_auth_token_delivery.py::test_refresh_token_delivery -v
```
Expected: 2 FAIL (currently always sets cookie and always returns token in body)

- [ ] **Step 3: Apply delivery policy to `/refresh`**

Open `app/api/routers/auth/endpoints_sessions.py`.

Add `is_web_client` to the existing tokens import (around line 33):

```python
from app.api.routers.auth.tokens import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    create_refresh_token,
    decode_token,
    is_web_client,
    validate_client_id,
)
```

Find the `set_refresh_cookie` call and `TokenPair` block in `refresh_access_token` (around lines 140–151). Replace it with:

```python
    web = is_web_client(client_id)
    if web:
        set_refresh_cookie(response, new_refresh_token, max_age=cookie_max_age)

    tokens = TokenPair(
        access_token=access_token,
        refresh_token=None if web else new_refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        token_type="Bearer",
    )
    return success_response(AuthTokensResponse(tokens=tokens, session_id=session_id))
```

- [ ] **Step 4: Run to verify pass**

```bash
pytest tests/api/test_auth_token_delivery.py::test_refresh_token_delivery -v
```
Expected: 2 PASSED

- [ ] **Step 5: Run full delivery test suite**

```bash
pytest tests/api/test_auth_token_delivery.py -v
```
Expected: all PASSED (11 tests: 9 unit + 6 login endpoint + 2 refresh integration)

- [ ] **Step 6: Run existing session tests — confirm no regression**

```bash
pytest tests/api/test_auth_sessions.py -v
```
Expected: all PASSED

- [ ] **Step 7: Run full auth test suite**

```bash
pytest tests/api/test_auth_new.py tests/api/test_auth_sessions.py tests/api/test_auth_token_delivery.py -v
```
Expected: all PASSED

- [ ] **Step 8: Commit**

```bash
git add app/api/routers/auth/endpoints_sessions.py tests/api/test_auth_token_delivery.py
git commit -m "feat(auth): apply refresh-token delivery policy to /refresh endpoint"
```
