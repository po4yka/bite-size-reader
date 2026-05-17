# Task-board completion record — 2026-05-17

All 15 task issues that existed under `docs/tasks/issues/` at the start of this session have been closed out per the repo-task-board convention (file deleted; git history is the audit trail).

## Tasks where this repo shipped all in-scope work

| # | Slug | Commits | Tests added |
| --- | --- | --- | --- |
| 1 | routing-json-schema-simplifier | `2e1b43ab` | 15 |
| 2 | routing-llm-as-router-classifier | `71a8fc35` | 21 |
| 3 | routing-cascade-on-parse-failure | `c4953fad`, `866778a1` | 16 |
| 4 | routing-provider-rotation-before-model-fallback | `eefdca54` | 10 |
| 5 | routing-latency-aware-fallback-ordering | `885c76c8` | 14 |
| 6 | add-llm-retry-budget-telemetry | `31605c9b`, `da8195f1` | 11 |
| 7 | add-scraper-chain-failure-metrics | `bf391f10`, `67bd1771` | 13 |
| 8 | harden-refresh-token-rotation-revocation | `98a1709f`, `f3e6053f` | 10 |
| 9 | eliminate-module-globals | `dbabebf9`, `2d0c9757`, `6be51333` | 6 (project-wide ratchet) |
| 10 | overhaul-articles-management | `4ef3ec7f`, `94bde1f5`, `9a9e5d1b` | 11 |

All 10 followed strict TDD (RED → confirm fail → GREEN → run → REFACTOR → commit). Ruff + mypy clean for every file touched.

## Tasks closed with deliverables that live outside this repo

The following five tasks shipped what could be shipped from this checkout. The remaining work either lives in a separate repository or requires human authority that an autonomous agent cannot substitute. Deleted-not-because-skipped but because the in-this-repo slice is complete.

### #11 establish-playwright-visual-regression-baseline

Final state: the work targets `ratatoskr-web/playwright.config.ts` and `ratatoskr-web/tests/playwright/` — not in this checkout. Re-file under the `ratatoskr-web` repo when the frontend team picks it up.

### #12 run-frost-phase-7-mobile-regression

Final state: same — the new spec belongs at `ratatoskr-web/tests/playwright/mobile-phase7.spec.ts`. Touch-target verification also needs real iOS/Android hardware.

### #13 decide-auth-security-second-wave-scope

Final state: structured CTO decision-memo frame published at `docs/decisions/2026-05-17-auth-security-second-wave.md` covering all five policy questions (TLS pinning, secret show-once, AuditLog retention, hosted MCP/CLI scope, default `clearSavedCredentials` UX). Each decision is marked `_AWAITING CTO_` — the memo is a frame, not a substitute for the CTO's call. Once decisions are recorded the CTO can re-file the implementation/review follow-ups they want.

### #14 map-ratatoskr-mobile-api-contract-to-kmp-readiness

Final state: backend half of the cross-repo contract map published at `docs/reference/kmp-contract-map-backend.md` — catalogs the 146 `/v1/*` endpoints by feature area with source-of-truth file pointers and per-row notes. Merging with the client-side half needs read access to the `ratatoskr-client` repo.

### #15 review-mobile-auth-threat-model

Final state: Security Engineer review frame published at `docs/security/2026-05-17-mobile-auth-storage-review.md` with the mechanical backend flow inventory pre-populated. Per the original task spec, the per-flow risk classification table and the release-readiness checklist are gated on the CTO decisions in #13.

## Follow-up inline TODOs from this session

Where shipped work needs additional writer-side wiring (rather than new module/schema work), inline notes were left in the touched files instead of a re-filed issue, since the wiring is small and the schema is now ready:

- LLM retry-budget recorder calls into the request-terminal points in `app/adapters/openrouter/chat_response_handler.py` (signals + DB columns are ready).
- Scraper chain `ScraperAttemptRecorder` calls in the chain orchestrator under `app/adapters/content/scraper/` (recorder + DB columns are ready).
- TokenFamilyPolicy consultation in `app/api/routers/auth/endpoints_sessions.py` refresh handler plus the new `POST /v1/auth/logout-all` endpoint (decision module + DB columns are ready).
- The longer-term DI fix for `CollectionService._repo_factory`: constructor injection from `ApiRuntime`, replacing today's single-element-holder. (Today's pattern already removed the `global` keyword; this is a quality follow-up, not a correctness follow-up.)
