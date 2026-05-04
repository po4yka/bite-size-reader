---
title: Freeze and version the Mobile API surface
status: backlog
area: api
priority: high
owner: unassigned
blocks: []
blocked_by: []
created: 2026-04-30
updated: 2026-05-04
---

- [ ] #task Freeze and version the Mobile API surface #repo/ratatoskr #area/api #status/backlog ⏫

## Goal

Lock the Mobile API surface against `docs/MOBILE_API_SPEC.md` and `docs/openapi/mobile_api.yaml` so the KMP client ([[map-ratatoskr-mobile-api-contract-to-kmp-readiness]]) can ship without contract drift.

## Scope

- Diff every route under `app/api/routers/` against the OpenAPI document; reconcile any divergence (path, params, envelope shape, error codes).
- Add a CI step that re-generates an OpenAPI snapshot from FastAPI and fails on diff vs. checked-in spec.
- Tag the contract with a semver `api_version` returned in the success envelope `meta`.
- Document the freeze policy: any breaking change requires a version bump + KMP coordination.

## Acceptance criteria

- [ ] `app/api/main.py` exposes a generated OpenAPI doc that matches `docs/openapi/mobile_api.yaml` byte-for-byte (or via a documented normalization step).
- [ ] CI fails on uncommitted spec drift.
- [ ] Envelope `meta.version` populated on every response.

## References

- `docs/MOBILE_API_SPEC.md`, `docs/openapi/mobile_api.yaml`
- `app/api/main.py`, `app/api/routers/`
- [[map-ratatoskr-mobile-api-contract-to-kmp-readiness]]
