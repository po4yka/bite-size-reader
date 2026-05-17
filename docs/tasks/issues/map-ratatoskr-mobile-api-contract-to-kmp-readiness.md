---
title: Map Ratatoskr mobile API contract to KMP client readiness
status: blocked
area: kmp
priority: high
owner: CTO
blocks: []
blocked_by: []
created: 2026-04-30
updated: 2026-05-17
---

- [ ] #task Map Ratatoskr mobile API contract to KMP client readiness #repo/ratatoskr #area/kmp #status/blocked #blocked ⏫

    - blocked_reason: The KMP client lives in the separate `ratatoskr-client` repository which is not part of this checkout. The cross-repo contract map requires read access to that repo to identify consuming modules. The mobile-API source-of-truth (`docs/openapi/mobile_api.yaml`, `docs/reference/mobile-api.md`) IS in this repo and ready to feed the comparison. **Backend-side half** of the contract map is now published at `docs/reference/kmp-contract-map-backend.md`; merging it with the client-side half requires access to the `ratatoskr-client` repo.

## Objective

Produce a cross-repo contract map between the Ratatoskr FastAPI mobile API and the ratatoskr-client KMP app, then identify the smallest set of implementation, QA, or documentation follow-ups needed for a mobile release-readiness baseline.

## Inputs available from this repo

- `docs/openapi/mobile_api.yaml` / `mobile_api.json` — backend
  surface (auth, refresh/logout, summaries/articles aliases,
  sync sessions/full/delta/apply, collections, search, digest,
  signals, system/health)
- `docs/reference/mobile-api.md` — long-form contract notes
- `docs/SPEC.md` data model section
- `app/api/routers/auth/` — actual handler shapes
- `app/api/routers/sync.py` — sync endpoints

## Inputs needed from the ratatoskr-client repo

- `AGENTS.md`, `composeApp/AGENTS.md`, `DESIGN.md`,
  `docs/ARCHITECTURE.md`
- Client DTOs, repositories, tests
- Decompose component graph for the consuming features

## Acceptance criteria

- [ ] Identify current backend mobile API surfaces that the KMP client depends on: auth, refresh/logout, summaries/articles aliases, sync sessions/full/delta/apply, collections, search, digest, signals, system/health as applicable.
- [ ] Identify current ratatoskr-client modules/features that consume those surfaces and any gaps or uncertain contracts.
- [ ] Call out whether docs/openapi/mobile_api.yaml, docs/reference/mobile-api.md, client DTOs, client repositories, or tests are out of sync.
- [ ] Split concrete follow-up issues only where ownership is clear; do not start implementation in this issue.
- [ ] Include security/privacy implications for secret-login, refresh tokens, secure storage, and deletion/account endpoints.

## Expected artifact

Paperclip comment or attached contract map with backend endpoint surface, client feature owner, current status, risk, and next issue recommendations.

## Constraints

Do not edit product code. Do not edit docs/openapi/mobile_api.yaml directly. Use current repo files as source of truth. Do not expose secrets or run live external service calls.

## Risks

Backend/client drift can break mobile sync, auth refresh, offline-first behavior, or account deletion semantics.

## Definition of done

A cross-repo contract map exists with concrete follow-up issues or a written decision that no further work is needed before the next release gate.
