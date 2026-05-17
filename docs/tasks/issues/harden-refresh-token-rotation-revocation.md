---
title: Wire token-family policy into refresh endpoint and add family_id column
status: backlog
area: auth
priority: high
owner: unassigned
blocks: []
blocked_by: []
created: 2026-04-30
updated: 2026-05-17
---

- [ ] #task Wire token-family policy into refresh endpoint and add family_id column #repo/ratatoskr #area/auth #status/backlog ⏫

## Goal

The pure decision module
`app/security/token_family_policy.py` is in place with 8 unit tests
covering: first-use rotation, retired-token replay (cascade
revocation), expired-leaf reject (benign no-cascade), and the
logout-all family enumeration. What remains is the database schema
and endpoint wiring so the policy is actually consulted on every
refresh.

## Scope

- Alembic migration adding two non-nullable columns to
  `refresh_tokens`:
  - `family_id` (UUID / text). Each first-login token generates a
    new family; rotated tokens inherit the parent's family.
  - `parent_token_hash` (text, nullable for the root of each family).
- Backfill: assign a unique `family_id` to each existing row;
  leave `parent_token_hash` null.
- In `app/api/routers/auth/tokens.py`:
  - `create_refresh_token(parent_family_id=None, parent_token_hash=None)`
    accepts a parent and inherits its `family_id`.
- In `app/api/routers/auth/endpoints_sessions.py` refresh handler:
  - Load all family rows for the presented token's family.
  - Invoke `TokenFamilyPolicy.decide(...)`.
  - On `REVOKE_FAMILY`: bulk-revoke every row in the family,
    write one `AuditLog` event (`event_type=refresh_family_revoked`,
    payload includes `family_id`, `presented_token_hash_prefix`,
    `source_ip`), return 401.
  - On `REJECT`: 401 with no cascade.
  - On `ROTATE`: revoke the presented token, create a child token
    in the same family.
- New `POST /v1/auth/logout-all` endpoint:
  - Auth-required (current bearer).
  - Calls `TokenFamilyPolicy.family_ids_for_user(records)` and
    bulk-revokes every active family for the authed user.
  - Writes one `AuditLog` row per revoked family.
- Integration tests in `tests/api/test_auth_refresh.py`:
  - Replay attack: present a retired token → 401 + family revoked.
  - Logout-all: bearer auth → all of user's families revoked.
  - Expiry: stale token → 401, family not touched.
  - Concurrent refresh: two parallel POST /v1/auth/refresh from the
    same client serialize correctly (the second sees the first's
    revoked token and either succeeds on the new child or, if it
    raced past the revoke, gets REJECT).

## Acceptance criteria

- [ ] Replay of a retired refresh token returns 401 + family
  revocation persisted in `refresh_tokens` AND in `AuditLog`.
- [ ] `POST /v1/auth/logout-all` invalidates every active family
  for the user across devices.
- [ ] New integration tests under `tests/api/test_auth_refresh.py`
  pass; existing JWT/Telegram WebApp flows untouched.
- [ ] Alembic migration ships with a tested downgrade.

## References

- Decision module: `app/security/token_family_policy.py`
- Existing model: `app/db/models/core.py` (`RefreshToken`,
  `UserDevice`, `AuditLog`)
- Existing flow: `app/api/routers/auth/{endpoints_sessions,tokens}.py`
- [[review-mobile-auth-threat-model]]
