---
title: Wire TokenFamilyPolicy into refresh handler and add POST /v1/auth/logout-all
status: backlog
area: auth
priority: critical
owner: unassigned
blocks:
  - add-token-family-revocation-metrics-and-alert
  - add-token-family-revocation-integration-test
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Wire TokenFamilyPolicy into refresh handler and add POST /v1/auth/logout-all #repo/ratatoskr #area/auth #status/backlog 🔺

## Objective

The pure decision module `app/security/token_family_policy.py` and
the `RefreshToken.family_id` + `parent_token_hash` columns
(migration `0016`) shipped in commits `98a1709f` and `f3e6053f`,
but the refresh handler does not call them and the advertised
`POST /v1/auth/logout-all` endpoint does not exist. Until both
gaps are closed, the documented "stolen refresh token cascade
contained per family" guarantee is not enforced — the runtime
still falls back to "revoke ALL user tokens on any reuse" and
operators cannot revoke a single device-family on demand.

## Context

Confirmed by two independent audit agents on 2026-05-17:

- `app/api/routers/auth/endpoints_sessions.py:54-155` — `/refresh`
  handler runs a hand-rolled "revoke ALL user tokens" branch at
  lines 84-91; never calls `TokenFamilyPolicy.decide`, never reads
  `family_id` / `parent_token_hash`.
- The rotation call at `endpoints_sessions.py:118` omits
  `parent_token_hash`, so the family graph is never built — every
  new token starts a new family in practice.
- `rg -n "logout-all|logout_all" app/api/routers/` returns no
  matches; only `/logout` exists at `endpoints_sessions.py:158`.
- The completion record (`docs/tasks/COMPLETION-2026-05-17.md`)
  flags this as inline TODO #3 — recorder + DB columns + decision
  module are all in place, only the wiring is missing.

## Scope

- In `app/api/routers/auth/endpoints_sessions.py` `/refresh`:
  - Load all family rows for the presented token's `family_id`.
  - Invoke `TokenFamilyPolicy.decide(records, presented_hash, now)`.
  - On `REVOKE_FAMILY`: bulk-revoke every row in the family, write
    one `AuditLog` row (`event_type=refresh_family_revoked`,
    payload includes `family_id`, `presented_token_hash_prefix`,
    `source_ip`), return 401.
  - On `REJECT`: 401 with no cascade.
  - On `ROTATE`: revoke the presented token, create a child token
    in the same family, passing `parent_token_hash`.
- In `app/api/routers/auth/tokens.py` `create_refresh_token`:
  accept `parent_family_id=None` and `parent_token_hash=None`,
  inherit family on rotation.
- New endpoint `POST /v1/auth/logout-all`:
  - Auth-required (current bearer).
  - Calls `TokenFamilyPolicy.family_ids_for_user(records)`.
  - Bulk-revokes every active family for the authed user.
  - Writes one `AuditLog` row per revoked family.
- Register the endpoint in `app/api/routers/auth/endpoints.py`
  and document it in `docs/openapi/mobile_api.yaml` + the standard
  envelope.

## Acceptance criteria

- [ ] `/refresh` loads the family rows for the presented token,
  invokes `TokenFamilyPolicy.decide`, and applies ROTATE /
  REVOKE_FAMILY / REJECT per the policy contract.
- [ ] New refresh tokens persist `family_id` (inherited from parent)
  and `parent_token_hash` (sha256 of the presented token).
- [ ] On REVOKE_FAMILY, only the matching `family_id` rows are
  revoked (not all user tokens) and one `AuditLog` row is written
  per revoked family.
- [ ] `POST /v1/auth/logout-all` exists, requires bearer auth, calls
  `TokenFamilyPolicy.family_ids_for_user`, and bulk-revokes every
  active family for the authed user.
- [ ] Endpoint is documented in `docs/openapi/mobile_api.yaml` and
  `docs/reference/mobile-api.md`.

## References

- Decision module: `app/security/token_family_policy.py`
- Refresh handler: `app/api/routers/auth/endpoints_sessions.py`
- Model: `app/db/models/core.py:RefreshToken`
- Migration: `app/db/alembic/versions/0016_add_refresh_token_family_columns.py`
- Completion record: `docs/tasks/COMPLETION-2026-05-17.md` (inline TODO #3)
- Related: [[add-token-family-revocation-metrics-and-alert]],
  [[add-token-family-revocation-integration-test]]
