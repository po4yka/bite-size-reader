---
title: "Add refresh-token rotation test for /v1/auth/refresh"
status: doing
area: auth
priority: high
owner: Senior Python Backend Engineer
blocks: []
blocked_by: []
created: 2026-04-30
updated: 2026-05-04
---

- [ ] #task Add refresh-token rotation test for /v1/auth/refresh #repo/ratatoskr #area/auth #status/doing ⏫

## Context

Coordinate with [[review-mobile-auth-threat-model]] (security engineer).

## Objective

Existing tests in tests/api/test_auth_sessions.py cover token persistence and logout revocation but do NOT prove that calling POST /v1/auth/refresh issues a new refresh token AND revokes the previous one. Without this, an attacker who steals one refresh token can keep refreshing indefinitely.

## Expected artifact

- New test in tests/api/test_auth_sessions.py:
  - `test_refresh_rotates_refresh_token_and_revokes_previous`
  - `test_refresh_with_revoked_token_returns_401`
- Run via: `pytest tests/api/test_auth_sessions.py -v`

## Definition of done

- Tests pass.
- Tests fail if app/api/routers/auth/endpoints_sessions.py refresh_access_token regresses to reusing the same refresh token or fails to revoke the previous one.
