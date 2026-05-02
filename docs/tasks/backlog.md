# Backlog — ratatoskr

> Source of truth for `#status/backlog` tasks. Syntax: `- [ ] #task <title> #repo/ratatoskr #area/<area> #status/backlog <priority> [paperclip:POY-N]`


## auth

- [ ] #task Refresh token rotation and revocation hardening #repo/ratatoskr #area/auth #status/backlog ⏫ [paperclip:POY-265]
  - Paperclip: POY-265 · assigned to: unassigned
  
  ## Goal
  Make refresh-token issuance safe under replay and device loss. Companion to POY-256 (nickname/password login) and POY-257 (auth threat model).

  ## Scope
  - Track token families: each refresh issues a new token chained to the prior; reuse of a retired token revokes the whole family and forces re-login.
  - Persist revocations in `RefreshToken` table (or device-scoped tombstone); enforce on every refresh.
  - `POST /v1/auth/logout` revokes current device; `POST /v1/auth/logout-all` revokes every active family for the user.
  - Surface revoked-family events in audit log (`AuditLog`).
  - Integration tests: replay attack, logout-everywhere, expiry, rotation under concurrent refresh.

  ## Acceptance Criteria
  - Replay of a retired refresh token returns 401 + family revocation persisted.
  - Logout-all invalidates every active refresh for the user across devices.
  - New tests under `tests/api/test_auth_refresh.py` pass; existing JWT/Telegram WebApp flows untouched.

  ## References
  - `app/api/routers/auth.py`
  - `app/db/models.py` (`RefreshToken`, `UserDevice`, `AuditLog`)
  - POY-256, POY-257
  - `.cursor/rules/mobile_api.mdc`


## general

- [ ] #task Add nickname + password login with Remember Me option #repo/ratatoskr #area/general #status/backlog 🔼 [paperclip:POY-256]
  - Paperclip: POY-256 · assigned to: unassigned
  
  ## Goal
  Add a classic credential-based login flow to the web client (`clients/web/`) and Mobile API alongside the existing hybrid auth (Telegram WebApp header mode + JWT). Users should be able to authenticate with a nickname (username) and password, with an optional Remember Me checkbox that controls session persistence.

  ## Scope
  - Web frontend: nickname + password form on the login screen, plus a Remember Me checkbox.
  - Mobile API (`app/api/`): new `/auth/login` route accepting `{ nickname, password, remember_me }`; password hashing (argon2/bcrypt); JWT issuance; refresh token rotation.
  - Persistence: extend `User` model (or add `UserCredential`) to store nickname (unique) and password hash; respect single-user owner whitelist (`ALLOWED_USER_IDS`).
  - Remember Me semantics: when true, issue a long-lived refresh token + persist in `localStorage`; when false, session-scoped storage and shorter refresh TTL.
  - Account bootstrap: CLI or one-time setup to create the owner's nickname + password (no public signup).

  ## Acceptance Criteria
  - Login with valid nickname + password returns access + refresh tokens.
  - Remember Me=false -> tokens cleared on browser close; Remember Me=true -> session survives reload until refresh expiry.
  - Wrong credentials return generic error (no user enumeration); rate-limited.
  - Existing Telegram WebApp + JWT flows remain untouched.
  - `cd clients/web && npm run check:static && npm run test` passes; backend `make lint type` and pytest pass.

  ## References
  - `clients/web/src/auth/AuthProvider.tsx`
  - `app/api/routers/auth.py`
  - `app/api/services/` (token issuance)
  - `docs/reference/frontend-web.md` (hybrid auth contract)

- [ ] #task Freeze and version the Mobile API surface #repo/ratatoskr #area/general #status/backlog ⏫ [paperclip:POY-263]
  - Paperclip: POY-263 · assigned to: unassigned
  
  ## Goal
  Lock the Mobile API surface against `docs/MOBILE_API_SPEC.md` and `docs/openapi/mobile_api.yaml` so the KMP client (POY-253) can ship without contract drift.

  ## Scope
  - Diff every route under `app/api/routers/` against the OpenAPI document; reconcile any divergence (path, params, envelope shape, error codes).
  - Add a CI step that re-generates an OpenAPI snapshot from FastAPI and fails on diff vs. checked-in spec.
  - Tag the contract with a semver `api_version` returned in the success envelope `meta`.
  - Document the freeze policy: any breaking change requires a version bump + KMP coordination.

  ## Acceptance Criteria
  - `app/api/main.py` exposes a generated OpenAPI doc that matches `docs/openapi/mobile_api.yaml` byte-for-byte (or via a documented normalization step).
  - CI fails on uncommitted spec drift.
  - Envelope `meta.version` populated on every response.

  ## References
  - `docs/MOBILE_API_SPEC.md`, `docs/openapi/mobile_api.yaml`
  - `app/api/main.py`, `app/api/routers/`
  - POY-253 (KMP client readiness)

- [ ] #task Scraper chain failure correlation and metrics #repo/ratatoskr #area/general #status/backlog 🔼 [paperclip:POY-266]
  - Paperclip: POY-266 · assigned to: unassigned
  
  ## Goal
  Make scraper-chain failures debuggable end-to-end. Motivated by recent `fix: align scraper providers with current upstream APIs` and `fix: address audit findings from scraper-stack code review` — provider drift is recurring and hard to triage without per-provider telemetry.

  ## Scope
  - Emit a structured `scraper.attempt` event per provider call with: provider name, correlation_id, url host, latency_ms, status (success|error|timeout|skipped), error class.
  - Prometheus counters: `scraper_attempts_total{provider,status}`, histogram `scraper_attempt_latency_seconds{provider}`.
  - Tag every `crawl_results` row with the winning provider; persist failed-provider list in a new `crawl_results.attempt_log` JSON column (or sibling table).
  - Add a Grafana panel under `ops/monitoring/grafana/` showing per-provider success rate + p95 latency.

  ## Acceptance Criteria
  - Logs include `scraper.attempt` for every chain step; correlation_id present.
  - `/metrics` exposes the new counters and histogram.
  - One Grafana JSON dashboard checked into `ops/monitoring/grafana/`.
  - Unit tests cover attempt-log serialization and partial-failure paths.

  ## References
  - `app/adapters/content/scraper/`
  - `app/observability/`
  - Roadmap P2 #1

- [ ] #task LLM call retry-budget telemetry #repo/ratatoskr #area/general #status/backlog 🔼 [paperclip:POY-267]
  - Paperclip: POY-267 · assigned to: unassigned
  
  ## Goal
  Expose how often summarization burns its retry budget so OpenRouter outages and prompt regressions show up in metrics, not in user complaints.

  ## Scope
  - Persist on every `LLMCall`: attempt index, fallback model used (vs. primary), retry-exhaustion flag, total wall-clock latency.
  - Prometheus: `llm_call_attempts_total{provider,model,status}`, `llm_call_retry_exhaustion_total{model}`, histogram `llm_call_latency_seconds{model}`.
  - Surface fallback model usage in summary `meta` so downstream agents can detect quality drift.
  - Alert recipe in docs: trigger when retry exhaustion rate >5%/15min.

  ## Acceptance Criteria
  - New columns/JSON keys backfilled-safe (nullable) and documented in `docs/SPEC.md` data model section.
  - `/metrics` exposes the listed counters/histogram.
  - One Grafana panel + a documented alert rule.

  ## References
  - `app/adapters/openrouter/`, `app/adapters/llm/`
  - `app/db/models.py` (`LLMCall`)
  - Roadmap P2 #1

- [ ] #task Articles management overhaul (filters, bulk actions, real signal) #repo/ratatoskr #area/general #status/backlog 🔼 [paperclip:POY-281]
  - Paperclip: POY-281 · assigned to: unassigned
  
  ## Goal
  Make the All Articles + Library screens usable as a real workspace, not a static list. Today users can only sort by date and click into a row. There is no real filtering, no bulk action surface, the Library search box does not query the API, and the Library `HIGH SIGNAL` filter relies on a `confidence` field that is not present on `SummaryCompact` (it is read through a cast and silently no-ops).

  ## Concrete defects to fix
  - `clients/web/src/features/articles/ArticlesPage.tsx`: `searchTerm` is local state only and never reaches the API; no filter beyond sort.
  - `clients/web/src/features/library/LibraryPage.tsx`: hardcoded `limit:100, offset:0` (no real pagination); HIGH SIGNAL filter casts to `SummaryCompact & { confidence?: number }` — field is not in the API contract; INBOX/PENDING/TOTAL counters reflect only the loaded page; the `INGEST · SYNC ACTIVE` footer is a static literal, not wired to anything.

  ## Scope
  - Wire ArticlesPage search to `GET /v1/summaries?search=...` (or the `/v1/search/...` endpoint, whichever the API uses; reconcile with `app/api/routers/summaries.py` and `app/api/routers/search.py`).
  - Add filters on both screens: read/unread, favorited, language, source domain, topic tag, collection, date range. Hook to existing query params; extend the API where missing.
  - Add a real `confidence` (or rename to `signal_score`) to the `SummaryCompact` API model so the HIGH SIGNAL filter is server-side, not a client-side cast.
  - Replace Library's offset pagination with cursor/keyset pagination (or at minimum proper limit/offset paging tied to a count query); virtualize the row list for >500 items.
  - Bulk actions in ArticlesPage: multi-select rows + apply mark read/unread, favorite, add tag, add to collection, delete. Backend: ensure batch endpoints exist or add them under `/v1/summaries/batch`.
  - Inline row actions on Library: `m` mark read, `f` favorite, `t` tag, `d` delete, `c` collection — all keyboard-bound, mouse fallback in row hover menu.
  - Saved views: persist `{filter, sort, search}` per user as named presets via `UserPreference` (or add a `SavedView` model if cleaner).
  - Wire the Library footer ingest status to a real signal: subscribe to the existing background task / sync state instead of the hardcoded string.

  ## Acceptance Criteria
  - Search + filter changes hit the API and update the URL (deep-linkable).
  - Bulk actions: select 10 rows, mark all read in one request; UI updates optimistically and rolls back on error.
  - HIGH SIGNAL filter is server-side; documented contract for the score in `docs/SPEC.md`.
  - Library scrolls smoothly with 5000 rows in the dataset (virtualized).
  - Saved views survive reload and tab close.
  - New tests: pytest on batch endpoints; Playwright on filter + bulk-action flow; React Testing Library on saved-view persistence.
  - `cd clients/web && npm run check:static && npm run test` passes; backend `make lint type` and pytest pass.

  ## References
  - `clients/web/src/features/articles/ArticlesPage.tsx`
  - `clients/web/src/features/library/LibraryPage.tsx`
  - `clients/web/src/hooks/useSummaries.ts`
  - `app/api/routers/summaries.py`, `app/api/routers/search.py`, `app/api/routers/tags.py`, `app/api/routers/collections.py`
  - `app/db/models.py` (`Summary`, `SummaryTag`, `Collection`, `CollectionItem`)
  - POY-268 (Mobile Phase 7 regression pass) — coordinate so mobile views inherit the same filter/bulk surface.


## sync

- [ ] #task Sync v2 contract regression suite #repo/ratatoskr #area/sync #status/backlog ⏫ [paperclip:POY-264]
  - Paperclip: POY-264 · assigned to: unassigned
  
  ## Goal
  Lock `/v1/sync` semantics with a pytest suite so KMP offline-first work (Roadmap P1 #2) cannot regress server behavior.

  ## Scope
  - Order: created/updated/tombstone-deleted strictly ordered by `server_version`.
  - Pagination: `has_more` + `next_since` correctness across multi-page pulls.
  - Chunk limits: clamp to [1..500] (default 200), server downsizes oversized requests without erroring.
  - Session TTL: expired session returns 410 with envelope error.
  - Upload whitelist: only `summary.is_read` and `client_note` mutate; everything else 422.
  - `last_seen_version` enforcement: stale uploads rejected with conflict envelope.

  ## Acceptance Criteria
  - New tests under `tests/api/test_sync_v2_contract.py` cover all bullets above.
  - Tests run under `pytest -q` in <10s with the default fixture DB.
  - Coverage for `app/api/routers/sync.py` rises to >=90% lines.

  ## References
  - `app/api/routers/sync.py`
  - `docs/MOBILE_API_SPEC.md` (Sync v2 section)
  - `.cursor/rules/mobile_api.mdc`


## testing

- [ ] #task Mobile regression pass for Frost Phase 7 #repo/ratatoskr #area/testing #status/backlog 🔼 [paperclip:POY-268]
  - Paperclip: POY-268 · assigned to: unassigned
  
  ## Goal
  Prove the mobile rollout shipped in commits 8aa4ec8b..7092000d (Phase 7a–7d, Group A–E) holds up across a real viewport sweep and on touch hardware.

  ## Scope
  - Playwright mobile spec covering: Library, Articles, Article detail, Search, TagManagement, Collections, Submit, Ingestion, Settings, Dashboard, Automation, Login.
  - Viewport sweep: 360, 390, 414, 480, 600, 768 px wide; both portrait and landscape.
  - Verify: bottom tab bar visibility, drawer focus trap, 44×44 touch targets, container-query breakpoints, full-screen modal scroll lock.
  - File any regressions as child issues; fix obvious ones inline.

  ## Acceptance Criteria
  - New `clients/web/tests/playwright/mobile-phase7.spec.ts` runs in CI green.
  - Visual snapshots stored under `clients/web/tests/playwright/__snapshots__/` for each screen × viewport.
  - Defect list captured in the issue or as linked children.

  ## References
  - Recent commits: 8aa4ec8b, 4af8bcf1, 35c77fcc, 747301c9, 333f1be0, 2828e9c9, e1aa2e69, 7092000d
  - `clients/web/`
  - `DESIGN.md` (Mobile section)

- [ ] #task Playwright visual-regression baseline and docs #repo/ratatoskr #area/testing #status/backlog 🔼 [paperclip:POY-269]
  - Paperclip: POY-269 · assigned to: unassigned
  
  ## Goal
  Finish the migration started in `d4b22a52 ci(web): replace Chromatic with local-only Playwright visual regression`. Without baseline snapshots and an update workflow, visual regression is dormant.

  ## Scope
  - Generate baseline snapshots for the existing Frost screens and Storybook stories.
  - Document the baseline-update workflow (when to run, how to review diffs, how to commit) in `docs/reference/frontend-web.md`.
  - Add an npm script `npm run test:visual:update` that updates snapshots locally; CI must never auto-update.
  - Decide and document how snapshots are stored (in-repo vs. Git LFS) and the platform/font assumptions.

  ## Acceptance Criteria
  - Baseline snapshots checked in; CI runs visual regression green on a clean checkout.
  - `docs/reference/frontend-web.md` has a Visual Regression section.
  - A deliberate UI tweak in a throwaway branch causes CI to fail with a readable diff.

  ## References
  - Commit d4b22a52
  - `clients/web/` Playwright config
  - `docs/reference/frontend-web.md`

- [ ] #task Channel digest scheduler smoke test #repo/ratatoskr #area/testing #status/backlog 🔼 [paperclip:POY-270]
  - Paperclip: POY-270 · assigned to: unassigned
  
  ## Goal
  Give the channel-digest subsystem an automated safety net. APScheduler + Redis lock + Telethon userbot is the highest-risk untested path in the bot today.

  ## Scope
  - Smoke test: APScheduler fires the digest job at the configured cadence in a fast-forward clock fixture.
  - Redis distributed lock contention: two scheduler instances do not double-deliver a digest.
  - Userbot session reuse: a fresh session is not created on every run.
  - Idempotence: re-running the job for the same period does not duplicate `DigestDelivery` rows.
  - Failure modes: Redis down (graceful degrade or fail-fast per config), Telethon auth expired (clear error path).

  ## Acceptance Criteria
  - New `tests/integration/test_channel_digest_scheduler.py` covers all bullets with mocked Redis (fakeredis) and Telethon.
  - Failures surface to logs with correlation_id; no silent swallow.
  - `docs/reference/` gains a short ops section for the digest subsystem.

  ## References
  - `app/adapters/digest/`
  - `app/db/models.py` (`DigestDelivery`, `ChannelSubscription`, `UserDigestPreference`)
  - `CLAUDE.md` Channel Digest section
