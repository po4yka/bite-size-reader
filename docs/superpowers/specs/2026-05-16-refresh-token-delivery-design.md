# Refresh-Token Delivery Policy: Web vs Mobile/CLI

**Date:** 2026-05-16  
**Status:** Approved

## Problem

All four token-issuing endpoints currently set an httpOnly cookie AND return the refresh token in the JSON response body for every client type. Web clients reading `refreshToken` from the response body can expose the token to JavaScript, defeating the purpose of the httpOnly cookie. Mobile and CLI clients cannot use cookies and rely on the body token.

## Goal

- Web clients: refresh token delivered only via httpOnly cookie; JSON body has `refreshToken: null`.
- Mobile/CLI clients: refresh token returned in JSON body; no cookie set.
- No breaking change to the API contract (body field is already `str | None`).

## Approach

Use the existing `resolve_client_type(client_id)` function in `app/api/routers/auth/tokens.py` to infer delivery policy from the `client_id` present in every request. A new thin helper `is_web_client(client_id)` wraps it.

## New Helper

```python
# tokens.py
def is_web_client(client_id: str | None) -> bool:
    """Return True when the client expects cookie-only refresh token delivery."""
    return resolve_client_type(client_id) == "web"
```

## Affected Endpoints

| Endpoint | File | `client_id` source |
|---|---|---|
| `POST /credentials-login` | `endpoints_credentials.py` | `payload.client_id` |
| `POST /telegram-login` | `endpoints_telegram.py` | `login_data.client_id` |
| `POST /secret-login` | `endpoints_secret_keys.py` | `login_data.client_id` |
| `POST /refresh` | `endpoints_sessions.py` | JWT payload `client_id` |

`/logout` is unchanged — it accepts the token from body or cookie and clears the cookie regardless.

## Delivery Pattern (applied at each affected endpoint)

```python
web = is_web_client(client_id)
if web:
    set_refresh_cookie(response, refresh_token, max_age=cookie_max_age)
tokens = TokenPair(
    access_token=access_token,
    refresh_token=None if web else refresh_token,
    expires_in=...,
    token_type="Bearer",
)
```

## Data Flow

### Login endpoints (`/credentials-login`, `/telegram-login`, `/secret-login`)

```
Request arrives with client_id
  → validate_client_id(client_id)
  → is_web = is_web_client(client_id)
  → issue refresh token (unchanged)
  → if is_web: set_refresh_cookie(response, token)
  → return TokenPair(refresh_token=None if is_web else token)
```

### `/refresh` endpoint

```
Incoming token resolved (body → cookie fallback, unchanged)
  → decode JWT → extract client_id from payload
  → is_web = is_web_client(client_id)
  → rotate token (unchanged)
  → if is_web: set_refresh_cookie(response, new_token)
  → return TokenPair(refresh_token=None if is_web else new_token)
```

The cookie fallback (`raw_token = refresh_data.refresh_token or request.cookies.get(REFRESH_COOKIE_NAME)`) is unchanged — web clients send no body token, so the cookie path activates naturally.

## Edge Cases

- **Unknown client type** (`resolve_client_type` returns `"unknown"`): body delivery, no cookie. Unknown clients cannot exploit a cookie they never receive.
- **`/logout`**: reads token from body or cookie; clears cookie; no change needed.
- **`/refresh` reuse detection**: cookie is cleared on revoked-token detection path — unchanged.

## No Schema Changes

`TokenPair.refresh_token` is already `str | None = Field(default=None, ...)`. Returning `null` for web clients is valid today with no migration or model change.

## Test Plan

New tests in `tests/api/test_auth_token_delivery.py`, parametrized across all four login endpoints.

### Web client assertions (client_id `"webapp"`)
- Login response body has `refreshToken: null`
- Response `Set-Cookie` header present and contains `ratatoskr_refresh_token`
- `/refresh` via cookie succeeds; rotated token in cookie; body has `refreshToken: null`
- `/logout` via cookie clears the cookie

### Mobile/CLI client assertions (client_ids `"mobile-ios"`, `"cli-1"`, `"mcp-server"`)
- Login response body has non-null `refreshToken`
- No `Set-Cookie` header in response
- `/refresh` via body token succeeds; rotated token in body; no `Set-Cookie`

### Edge case
- client_id resolving to `"unknown"` → body delivery, no cookie

Approximately 12–14 test cases covering the full policy matrix.
