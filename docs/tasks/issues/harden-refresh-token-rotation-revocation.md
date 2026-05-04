---
title: Harden refresh-token rotation and revocation
status: backlog
area: auth
priority: high
owner: unassigned
blocks: []
blocked_by: []
created: 2026-04-30
updated: 2026-05-04
---

- [ ] #task Harden refresh-token rotation and revocation #repo/ratatoskr #area/auth #status/backlog ⏫

## Goal

Make refresh-token issuance safe under replay and device loss. Companion to [[add-nickname-password-login-remember-me]] and [[review-mobile-auth-threat-model]].

## Scope

- Track token families: each refresh issues a new token chained to the prior; reuse of a retired token revokes the whole family and forces re-login.
- Persist revocations in `RefreshToken` table (or device-scoped tombstone); enforce on every refresh.
- `POST /v1/auth/logout` revokes current device; `POST /v1/auth/logout-all` revokes every active family for the user.
- Surface revoked-family events in audit log (`AuditLog`).
- Integration tests: replay attack, logout-everywhere, expiry, rotation under concurrent refresh.

## Acceptance criteria

- [ ] Replay of a retired refresh token returns 401 + family revocation persisted.
- [ ] Logout-all invalidates every active refresh for the user across devices.
- [ ] New tests under `tests/api/test_auth_refresh.py` pass; existing JWT/Telegram WebApp flows untouched.

## References

- `app/api/routers/auth.py`
- `app/db/models.py` (`RefreshToken`, `UserDevice`, `AuditLog`)
- [[add-nickname-password-login-remember-me]], [[review-mobile-auth-threat-model]]
