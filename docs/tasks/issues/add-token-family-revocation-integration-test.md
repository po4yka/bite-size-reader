---
title: Add integration test for end-to-end token-family revocation cascade
status: backlog
area: testing
priority: high
owner: unassigned
blocks: []
blocked_by:
  - wire-token-family-rotation-and-add-logout-all
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Add integration test for end-to-end token-family revocation cascade #repo/ratatoskr #area/testing #status/backlog ⏫

## Objective

`tests/security/test_token_family_policy.py` only exercises the pure `TokenFamilyPolicy.decide()` function. The security-meaningful behaviour — "presenting a retired token revokes every sibling in the family" — has no end-to-end integration test. A refactor of `tokens.py` or `endpoints_sessions.py` could silently break the cascade without any test failing.

## Context

- `rg "REVOKE_FAMILY" tests/` matches only the policy unit test.
- No integration test exercises the rotate-chain happy path, retired-token replay, or `POST /v1/auth/logout-all`.
- Blocked by [[wire-token-family-rotation-and-add-logout-all]] — the cascade behaviour cannot be tested until the policy is invoked on `/refresh`.

## Scope

- New integration tests in `tests/api/test_auth_refresh.py` (or a new `tests/api/test_token_family_cascade.py`): - **Rotate-chain happy path**: login → refresh × 3 → all four tokens form one `family_id`, latest is active. - **Retired-token replay**: present the first refresh token after 3 rotations → 401 returned + all 4 sibling rows revoked + one `AuditLog` row written for the family. - **Expired leaf**: present a stale active token after expiry → 401, family NOT revoked. - **Logout-all**: bearer auth → all active families for the user revoked across simulated multi-device sessions. - **Concurrent refresh**: two parallel `POST /v1/auth/refresh` from the same client → serialize correctly; second either succeeds on the new child or gets REJECT, no family-revoke cascade. - Each test asserts the `ratatoskr_token_family_decisions_total{decision}` counter increments by the expected delta (once [[add-token-family-revocation-metrics-and-alert]] lands).

## Acceptance criteria

- [ ] Five integration tests covering the scenarios above.
- [ ] Tests run inside the standard `tests/api` pytest harness (real DB via `tests/db_helpers.py`).
- [ ] Tests pass against the wired implementation; fail meaningfully if `TokenFamilyPolicy` is not invoked on `/refresh`.

## References

- Policy: `app/security/token_family_policy.py`
- Existing unit test: `tests/security/test_token_family_policy.py`
- Existing test helpers: `tests/db_helpers.py`
- Depends on: [[wire-token-family-rotation-and-add-logout-all]]
- Related: [[add-token-family-revocation-metrics-and-alert]]
