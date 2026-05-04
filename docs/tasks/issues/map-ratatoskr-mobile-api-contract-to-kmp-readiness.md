---
title: Map Ratatoskr mobile API contract to KMP client readiness
status: doing
area: kmp
priority: high
owner: CTO
blocks: []
blocked_by: []
created: 2026-04-30
updated: 2026-05-04
---

- [ ] #task Map Ratatoskr mobile API contract to KMP client readiness #repo/ratatoskr #area/kmp #status/doing ⏫

## Objective

Produce a cross-repo contract map between the Ratatoskr FastAPI mobile API and the ratatoskr-client KMP app, then identify the smallest set of implementation, QA, or documentation follow-ups needed for a mobile release-readiness baseline.

## Context

Ratatoskr CLAUDE.md, docs/SPEC.md, docs/MOBILE_API_SPEC.md, DESIGN.md, ratatoskr-client AGENTS.md, composeApp/AGENTS.md, DESIGN.md, and docs/ARCHITECTURE.md were read for context. The backend mobile API source of truth is docs/openapi/mobile_api.yaml/json and uses /v1 envelope responses, bearer auth, Telegram initData, secret-login, session sync, summaries/articles aliases, collections, search, digest, signals, and mixed-source aggregation surfaces. The KMP client uses Kotlin Multiplatform, Decompose navigation, SQLDelight/offline-first data, Ktor auth refresh, secure storage, and Frost design rules. Do not edit docs/openapi/mobile_api.yaml directly.

## Owner

CTO. Coordinate with Senior Python Backend Engineer, Senior KMP/Compose Engineer, and Security Engineer as needed.

## Acceptance criteria

- [ ] Identify current backend mobile API surfaces that the KMP client depends on: auth, refresh/logout, summaries/articles aliases, sync sessions/full/delta/apply, collections, search, digest, signals, system/health as applicable.
- [ ] Identify current ratatoskr-client modules/features that consume those surfaces and any gaps or uncertain contracts.
- [ ] Call out whether docs/openapi/mobile_api.yaml, docs/MOBILE_API_SPEC.md, client DTOs, client repositories, or tests are out of sync.
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
