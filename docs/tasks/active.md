# Active — ratatoskr

> `#status/todo` · `#status/doing` · `#status/review` tasks.


## doing

- [ ] #task Map Ratatoskr mobile API contract to KMP client readiness #repo/ratatoskr #area/kmp #status/doing ⏫ [paperclip:POY-253]
  - Paperclip: POY-253 · assigned to: CTO
  
  Objective
  Produce a cross-repo contract map between the Ratatoskr FastAPI mobile API and the ratatoskr-client KMP app, then identify the smallest set of implementation, QA, or documentation follow-ups needed for a mobile release-readiness baseline.

  Context
  CEO heartbeat read ratatoskr CLAUDE.md, docs/SPEC.md, docs/MOBILE_API_SPEC.md, DESIGN.md, ratatoskr-client AGENTS.md, composeApp/AGENTS.md, DESIGN.md, and docs/ARCHITECTURE.md. The backend mobile API source of truth is docs/openapi/mobile_api.yaml/json and uses /v1 envelope responses, bearer auth, Telegram initData, secret-login, session sync, summaries/articles aliases, collections, search, digest, signals, and mixed-source aggregation surfaces. The KMP client uses Kotlin Multiplatform, Decompose navigation, SQLDelight/offline-first data, Ktor auth refresh, secure storage, and Frost design rules. CEO must not edit docs/openapi/mobile_api.yaml directly.

  Owner
  CTO. Coordinate with Senior Python Backend Engineer, Senior KMP/Compose Engineer, Product Manager, QA Lead, and Security Engineer as needed.

  Priority
  High.

  Parent issue or goal linkage
  Goal: Ratatoskr ecosystem mobile contract and release-readiness baseline. Project: ratatoskr.

  Acceptance criteria
  - Identify current backend mobile API surfaces that the KMP client depends on: auth, refresh/logout, summaries/articles aliases, sync sessions/full/delta/apply, collections, search, digest, signals, system/health as applicable.
  - Identify current ratatoskr-client modules/features that consume those surfaces and any gaps or uncertain contracts.
  - Call out whether docs/openapi/mobile_api.yaml, docs/MOBILE_API_SPEC.md, client DTOs, client repositories, or tests are out of sync.
  - Split concrete follow-up issues only where ownership is clear; do not start implementation in this issue.
  - Include security/privacy implications for secret-login, refresh tokens, secure storage, and deletion/account endpoints.

  Expected artifact
  Paperclip comment or attached contract map with backend endpoint surface, client feature owner, current status, risk, and next issue recommendations.

  Constraints
  Do not edit product code. Do not edit docs/openapi/mobile_api.yaml directly. Use current repo files as source of truth. Do not expose secrets or run live external service calls.

  Risks
  Backend/client drift can break mobile sync, auth refresh, offline-first behavior, or account deletion semantics.

  Verification plan
  Use static repo inspection only for this issue; list targeted tests/builds that follow-up owners should run.

  Definition of done
  A cross-repo contract map exists with concrete follow-up issues or a written decision that no further work is needed before the next release gate.

- [ ] #task Add backend sync-apply response contract fixture #repo/ratatoskr #area/sync #status/doing ⏫ [paperclip:POY-260]
  - Paperclip: POY-260 · assigned to: Senior Python Backend Engineer (Ratatoskr)
  
  Objective
  Add or refresh a backend contract fixture/test for `/v1/sync/apply` showing the exact JSON response shape consumed by ratatoskr-client.

  Context
  CTO contract map POY-253 found backend sync-apply response is coherent and should stand: `sessionId`, `results[]`, `conflicts[]`, `hasMore`. KMP will adapt in POY-258. Backend should preserve this contract with focused test evidence so future changes do not reintroduce drift.

  Owner
  Senior Python Backend Engineer. Coordinate with CTO and QA Lead.

  Priority
  High.

  Parent issue or goal linkage
  Related: POY-253 and POY-258. Goal: Ratatoskr ecosystem mobile contract and release-readiness baseline. Project: ratatoskr.

  Acceptance criteria
  - Add or update a focused test/fixture for `/v1/sync/apply` response JSON, including at least success result, conflict result, and `hasMore` behavior where supported.
  - Verify response envelope and camelCase aliases match the mobile API contract.
  - Do not change `docs/openapi/mobile_api.yaml` unless CTO explicitly requests a contract update in a separate issue.
  - Report the exact pytest command used.

  Expected artifact
  Backend test/fixture change plus passing test evidence.

  Constraints
  Do not run live external service calls. Do not expose secrets. Keep routers transport-focused and service logic in service classes per Ratatoskr docs.

  Risks
  Without backend fixture coverage, KMP may fix against a shape that later drifts again.

  Verification plan
  Run the smallest relevant pytest target for sync apply response contract.

  Definition of done
  Backend has stable automated evidence for the sync-apply response shape and POY-255 can reference it as a release gate input.

- [ ] #task Backend: add refresh-token rotation test for /v1/auth/refresh #repo/ratatoskr #area/auth #status/doing ⏫ [paperclip:POY-277]
  - Paperclip: POY-277 · assigned to: Senior Python Backend Engineer (Ratatoskr)
  
  Filed from [POY-255](/POY/issues/POY-255) QA gate (row B9). Coordinate with Security Engineer ([POY-257](/POY/issues/POY-257)).

  Objective
  Existing tests in tests/api/test_auth_sessions.py cover token persistence and logout revocation but do NOT prove that calling POST /v1/auth/refresh issues a new refresh token AND revokes the previous one. Without this, an attacker who steals one refresh token can keep refreshing indefinitely.

  Owner: Senior Python Backend Engineer (Ratatoskr).

  Expected artifact
  - New test in tests/api/test_auth_sessions.py:
    - test_refresh_rotates_refresh_token_and_revokes_previous
    - test_refresh_with_revoked_token_returns_401
  - Run via: pytest tests/api/test_auth_sessions.py -v

  Definition of done
  - Tests pass.
  - Tests fail if app/api/routers/auth/endpoints_sessions.py refresh_access_token regresses to reusing the same refresh token or fails to revoke the previous one.

- [ ] #task Backend: add sync handler integration tests covering full/delta/apply + idempotency #repo/ratatoskr #area/sync #status/doing ⏫ [paperclip:POY-278]
  - Paperclip: POY-278 · assigned to: Senior Python Backend Engineer (Ratatoskr)
  
  Filed from [POY-255](/POY/issues/POY-255) QA gate (row B10).

  Objective
  Today tests/api/test_sync_service.py only covers SyncService._coerce_iso datetime serialization. The actual handlers (POST /sessions, GET /full, GET /delta, POST /apply in app/api/routers/sync.py) have no integration coverage. tests/test_api_rate_limit_and_sync.py exists but is excluded from CI.

  Owner: Senior Python Backend Engineer (Ratatoskr).

  Expected artifact
  - New tests/api/test_sync.py covering:
    - create session returns sessionId in {data,meta} envelope
    - full sync paginated by cursor
    - delta sync after full returns only changed items
    - apply changes with idempotent re-apply (same idempotency key) returns same result without double-applying
    - apply with conflict returns conflict count in envelope without 5xx
  - Mark with appropriate pytest marker so they run in CI test job (not skipped like the rate_limit_and_sync file).
  - Run via: pytest tests/api/test_sync.py -v

  Definition of done
  - Tests pass and run on every CI build.
  - Tests fail if a sync handler regresses on cursor pagination, idempotency, or conflict surfacing.

- [ ] #task Backend CI: promote web-playwright-visual to required status-check job #repo/ratatoskr #area/ci #status/doing ⏫ [paperclip:POY-279]
  - Paperclip: POY-279 · assigned to: Senior Build Gradle CI Engineer
  
  Filed from [POY-255](/POY/issues/POY-255) QA gate (row B14).

  Objective
  .github/workflows/ci.yml job web-playwright-visual runs the Playwright route + Storybook visual snapshot suite (Frost components, mobile route snapshots across desktop/iPhone 12/Pixel 5/iPad Mini). It is the canonical Frost parity reference for the v1 mobile release. Today it can fail without blocking status-check, which means a Frost regression can ship.

  Owner: Senior Build Gradle CI Engineer.

  Expected artifact
  - Updated .github/workflows/ci.yml status-check job: web-playwright-visual added to needs and to the success list.
  - If the job is too slow for every PR, gate via path filter (clients/web/**, docs/openapi/mobile_api.yaml, .github/workflows/ci.yml) but still block status-check when it runs.

  Definition of done
  - A PR that breaks a committed Playwright snapshot fails the merge gate.

- [ ] #task Unify ALLOWED_USER_IDS allowlist semantics across all auth paths #repo/ratatoskr #area/auth #status/doing ⏫ [paperclip:POY-280]
  - Paperclip: POY-280 · assigned to: Senior Python Backend Engineer (Ratatoskr)
  - Blocks: POY-257
  
  ## Background
  From the security review on [POY-257](/POY/issues/POY-257) (finding B1):

  `app/api/routers/auth/dependencies.py:117-120` calls `Config.is_user_allowed(user_id, fail_open_when_empty=True)`, while `webapp_auth.py:103`, `telegram.py:117`, and `secret_auth.py:76` all pass `fail_open_when_empty=False`. The startup validator at `app/config/settings.py:315-323` prevents an empty list under production config, but is bypassed by `allow_stub_telegram=True` (the lazy-load default in `secret_auth._get_cfg`).

  ## Risk
  High. Any deployment that instantiates `Settings(allow_stub_telegram=True)` and forgets `ALLOWED_USER_IDS` allows any validly-signed JWT to pass `get_current_user`. Other auth paths fail closed in the same condition — this is a divergence between code paths that must be either codified (documented as intentional multi-user mode) or removed.

  ## Acceptance
  - Decision recorded: keep fail-open for JWT (multi-user) OR unify to fail-closed.
  - If kept: add a startup `WARNING` log when `ALLOWED_USER_IDS` is empty AND any JWT path is used; document in `docs/MOBILE_API_SPEC.md` §Authentication.
  - If unified: change `dependencies.py:117-120` to `fail_open_when_empty=False` and update `tests/api/auth/` with a matrix test (empty | populated-include | populated-exclude) × {JWT, WebApp, Telegram-Login, secret-login}.
  - No regression in existing WebApp / secret-login tests.

  ## Owner
  Senior Python Backend Engineer (with Security Engineer + CTO sign-off on the policy decision).

- [ ] #task Decouple SECRET_LOGIN_PEPPER from JWT signing key #repo/ratatoskr #area/auth #status/doing ⏫ [paperclip:POY-282]
  - Paperclip: POY-282 · assigned to: Senior Python Backend Engineer (Ratatoskr)
  - Blocks: POY-257
  
  ## Background
  From the security review on [POY-257](/POY/issues/POY-257) (finding B2):

  `app/api/routers/auth/secret_auth.py:42-52` (`_get_secret_pepper`) returns `cfg.runtime.jwt_secret_key` when `SECRET_LOGIN_PEPPER` is unset.

  ## Risk
  High. Two unrelated security domains share a single secret:
  - Rotating `JWT_SECRET_KEY` invalidates every stored `ClientSecret.secret_hash` and locks every user out of secret-login.
  - A leak of either secret compromises both — JWT signing keys live in different places (env, CI runners, deploy secrets) than DB peppers should.

  ## Acceptance
  - Production `.env` and `.env.example` require an explicit `SECRET_LOGIN_PEPPER` (≥32 chars, generated independently of `JWT_SECRET_KEY`).
  - `_get_secret_pepper()` raises a startup `RuntimeError` if `SECRET_LOGIN_ENABLED=true` AND `SECRET_LOGIN_PEPPER` is unset (do not silently fall back to JWT key).
  - Migration path documented for any pre-existing `ClientSecret` rows hashed under the old pepper (one-time re-hash on next successful login, or forced rotation banner).
  - Bandit / pip-audit / unit tests still green.

  ## Owner
  Security Engineer + Senior Python Backend Engineer + CTO sign-off on rotation plan.

- [ ] #task Use constant-time compare for Telegram link nonce #repo/ratatoskr #area/general #status/doing ⏫ [paperclip:POY-283]
  - Paperclip: POY-283 · assigned to: Senior Python Backend Engineer (Ratatoskr)
  - Blocks: POY-257
  
  ## Background
  From the security review on [POY-257](/POY/issues/POY-257) (finding B3):

  `app/api/routers/auth/endpoints_telegram.py:146` validates the link-confirmation nonce with a plain `payload.nonce != link_nonce` comparison, while every other security-sensitive comparison in this module already uses `hmac.compare_digest` (e.g. `webapp_auth.py:68`, `telegram.py:110`, `endpoints_secret_keys.py:142`).

  ## Risk
  High in principle (anti-replay/CSRF-class token), low in practice (32-byte URL-safe random, 10-min TTL). Easy fix; should be uniform across the auth module.

  ## Acceptance
  - Replace `payload.nonce != link_nonce` with `not hmac.compare_digest(payload.nonce, link_nonce)`.
  - Add a regression test in `tests/api/auth/test_telegram_link.py` asserting the constant-time path is taken.
  - Spot-check the rest of `app/api/routers/auth/` for any remaining non-constant-time security comparisons and fix in the same PR.

  ## Owner
  Senior Python Backend Engineer.

- [ ] #task Decide second-wave Ratatoskr auth/security policy scope #repo/ratatoskr #area/auth #status/doing ⏫ [paperclip:POY-284]
  - Paperclip: POY-284 · assigned to: CTO
  - Blocks: POY-257
  
  Objective
  Decide the second-wave Ratatoskr auth/security policy scope from the Security/AppSec review in POY-257, then create the follow-up implementation/review issues that are warranted.

  Context
  Security marked Ratatoskr mobile auth, secret-login, and client storage not release-ready. The three high implementation blockers were already filed as POY-280, POY-282, and POY-283 and assigned to Backend. Security deferred 11 additional follow-ups pending CTO/board direction.

  Owner
  CTO.

  Priority
  High.

  Parent issue or goal linkage
  Parent: POY-257. Goal: Ratatoskr ecosystem mobile contract and release-readiness baseline.

  Acceptance criteria
  - Decision memo posted on this issue covering TLS pinning policy, secret show-once strategy, AuditLog retention, hosted MCP/CLI exposure scope, and default clearSavedCredentials UX.
  - Each decision is classified as implementation follow-up, security review follow-up, product/UX follow-up, board approval needed, or no-action-with-rationale.
  - Follow-up issues are created with explicit owners, acceptance criteria, expected artifact, constraints, risks, verification plan, and definition of done.
  - Board approval is requested before any external exposure expansion, credential policy change, telemetry/privacy scope change, or release-readiness claim.

  Expected artifact
  A concise CTO decision memo plus the resulting child issues/interactions.

  Constraints
  - Do not edit product code in this task.
  - Do not grant credentials or change external access.
  - Do not approve release readiness until Security and QA have signed off after follow-up remediation.
  - Keep mobile/API contract compatibility with ratatoskr-client in view.

  Risks
  - Shipping with inconsistent auth semantics or weak credential separation would undermine user trust.
  - Over-scoping TLS pinning or hosted MCP/CLI exposure can create operational and support cost without a clear release gate.
  - Under-documenting AuditLog retention or credential clearing UX leaves privacy claims ambiguous.

  Verification plan
  - Cross-check the decision memo against POY-257 findings and the existing Ratatoskr docs/specs.
  - Confirm every selected follow-up has an owner and is linked to this issue or POY-257.
  - Confirm any board-gated decision has an approval request instead of an implementation task.

  Definition of done
  CTO has posted the decision memo, created or explicitly rejected the deferred follow-ups, and left POY-257 with a clear Security/AppSec re-review path.
