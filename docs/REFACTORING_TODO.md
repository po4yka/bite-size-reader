# Ratatoskr Refactoring TODO

Status: execution checklist derived from [REFACTORING_ROADMAP.md](REFACTORING_ROADMAP.md).
Use this file as the issue/task source while keeping the roadmap strategic.

Conventions:

- Keep each checked item tied to a commit or PR.
- Update acceptance evidence as commands, screenshots, or links to CI runs.
- Do not start schema-changing work until the migration TODOs in Phase 0 and Phase 1 are resolved.
- For frontend work, update `docs/reference/frontend-web.md` and run `cd clients/web && npm run check:static && npm run test`.
- For backend behavior changes, add or update tests close to the touched module and run the smallest relevant pytest subset before broader CI.

## Phase 0 — Rename and baseline prerequisites

### 0.1 Rename residue audit

- [x] Run active-contract grep:
  `rg -n "bite-size-reader|bite_size_reader|bsr|BSR|web-carbon-v1|Carbon|carbon|cds-" . --glob '!data/**' --glob '!chroma_data/**' --glob '!clients/web/node_modules/**' --glob '!.git/**'`.
- [x] Split findings into `runtime`, `docs-history`, `generated`, and `accepted-compatibility`.
- [x] Rename active web client ID from `web-carbon-v1` to `web-v1` in `clients/web/src/api/auth.ts`, `clients/web/src/features/auth/SecretLoginForm.tsx`, tests, `docs/reference/frontend-web.md`, `docs/SPEC.md`, and generated OpenAPI/mobile docs if they reference the ID.
- [x] Decide whether to keep a one-release alias for `web-carbon-v1`.
- [x] N/A: no one-release alias is implemented for `web-carbon-v1`.
- [x] If not keeping an alias, document session reset and token refresh impact in `CHANGELOG.md` and the web frontend guide.
- [x] Rename active `BSR*` alert names in `ops/monitoring/alerting_rules.yml` to `Ratatoskr*` or `RTK*`.
- [x] Preserve old `bsr` examples only in `docs/how-to/migrate-from-bite-size-reader.md` where they are genuinely migration history.
- [x] Regenerate lockfiles or dependency comments that still say `bite-size-reader`, or document them as generated historical leftovers.
- [x] Re-run grep and paste the remaining allowed findings into the Phase 0 completion note.

Acceptance evidence:

- [x] `rg` output contains only migration-history or generated accepted leftovers.
- [ ] Web auth tests pass after client ID rename. `[blocked: clients/web dependencies are not installed locally; npm reports vitest: command not found]`
- [x] `CHANGELOG.md` has an entry for any session/client ID break.

### 0.2 Deployment docs truth reconciliation

- [x] Compare `README.md`, `docs/DEPLOYMENT.md`, `docs/adr/0006-multi-provider-scraper-chain.md`, and `ops/docker/docker-compose.yml` for Firecrawl claims.
- [x] Update docs to say current compose uses `firecrawl-api:host-gateway` until Phase 2 adds an in-compose Firecrawl service.
- [x] Add an explicit warning that self-hosted Firecrawl is not currently started by the default compose file.
- [x] Add a TODO note in deployment docs pointing to Phase 2 if the docs mention `ratatoskr-firecrawl` or port `3002` as already present.

Acceptance evidence:

- [x] A reader can tell whether Firecrawl is external, host-gateway, or compose-managed.
- [x] `rg -n "ratatoskr-firecrawl|port 3002|firecrawl-api:host-gateway" docs ops/docker` shows no contradiction.

### 0.3 Canonical migration path

- [x] Confirm runtime import path stays `app.cli.migrations.migration_runner` in `app/db/runtime/bootstrap.py`.
- [x] Confirm `app/cli/migrate_db.py` delegates to `DatabaseSessionManager.migrate()`.
- [x] Mark `app/cli/migrations/` as canonical in migration docs.
- [x] Audit `app/db/migrations/` against `app/cli/migrations/` and list migrations that exist only in one side.
- [x] Decide whether to delete `app/db/migrations/` immediately or leave a deprecated compatibility package with an import-time warning.
- [x] Add tests that fail if a new migration is added under `app/db/migrations/`.
- [x] Add a migration status path to `python -m app.cli.migrate_db --status` if missing, delegating to `app/cli/migrations/migration_runner.py`.
- [x] Document `status`, `run --dry-run`, and rollback limitations in `docs/how-to/migrate-versions.md`.

Acceptance evidence:

- [x] `python -m app.cli.migrate_db --status` or equivalent prints applied/pending migrations.
- [x] CI/test guard prevents future migrations under the duplicate directory.
- [x] Phase 3 migration work has one target directory: `app/cli/migrations/`.

## Phase 1 — Config consolidation

### 1.1 Config inventory and categorization

- [x] Generate a table of all uncommented `.env.example` assignments.
- [x] Map each variable to the owning Pydantic model in `app/config/`.
- [x] Mark each variable as `required`, `optional-defaulted`, `yaml-only`, or `deprecated/removable`.
- [x] Required target: Telegram `API_ID`, `API_HASH`, `BOT_TOKEN`, `ALLOWED_USER_IDS`, primary OpenRouter key, and auth secret only when web/API/browser-extension auth is enabled.
- [x] Confirm Firecrawl Cloud key is optional because self-hosted Firecrawl and other scraper providers exist.
- [x] Confirm Twitter/X variables are optional and disabled-by-default after Phase 5 cost gate.
- [x] Confirm migration shadow-mode variables are deprecated/removable unless a live code path still reads them.
- [x] Record all defaults from code, not from `.env.example`.

Acceptance evidence:

- [x] Inventory table added to `docs/environment_variables.md` or a generated config reference.
- [x] Every current `.env.example` variable is categorized.
- [x] No category uses vague labels like "advanced maybe"; each has a concrete action.

### 1.2 Minimal `.env.example`

- [x] Reduce `.env.example` to the required first-run variables plus comments pointing to `ratatoskr.yaml` for optional power-user settings.
- [x] Keep examples safe and non-secret-looking.
- [x] Remove default scraper, YouTube, Twitter, DB tuning, streaming, MCP, and Grafana variables from `.env.example`.
- [x] Update `README.md` quickstart required vars to match `.env.example`.
- [x] Update `docs/tutorials/quickstart.md` and `docs/DEPLOYMENT.md`.
- [x] Ensure `JWT_SECRET_KEY` docs say it is required only when web/API/browser-extension auth is enabled.
- [x] Add startup error copy for missing required variables with exact names and docs links.

Acceptance evidence:

- [x] `.env.example` has seven or fewer active assignments.
- [x] Quickstart and README list the same required vars.
- [x] Missing-secret startup tests assert actionable error text.

### 1.3 `ratatoskr.yaml` optional config

- [x] Pick YAML parser: `PyYAML` for load-only simplicity or `ruamel.yaml` if comment-preserving output is required.
- [x] Define config file search order, for example `RATATOSKR_CONFIG`, `./ratatoskr.yaml`, `/app/config/ratatoskr.yaml`.
- [x] Extend `app/config/settings.py` merge precedence to `code defaults < ratatoskr.yaml < .env < process env`.
- [x] Fold or replace the existing `config/models.yaml` loader in `app/config/models_file.py`.
- [x] Add a typed schema example under `docs/reference/config-file.md`.
- [x] Add validation tests for nested YAML sections.
- [x] Add tests proving env vars override YAML.
- [x] Add tests proving absent YAML falls back to code defaults.
- [x] Add redacted effective-config logging on startup.

Acceptance evidence:

- [x] New config tests pass.
- [x] `ratatoskr.yaml` can configure scraper, YouTube, Twitter, MCP, monitoring, and provider settings without env vars.
- [x] No secrets are printed in effective-config logs.

### 1.4 Env deprecation and compatibility

- [x] Extend deprecated env detection in `app/config/settings.py`.
- [x] Convert old scraper aliases into deterministic warnings or errors.
- [x] Add deprecation handling for migration shadow variables if they are no longer active.
- [x] N/A: no `REDIS_PREFIX=bsr` runtime alias is present in active config.
- [x] Add tests for deprecated env in process environment.
- [x] Add tests for deprecated env in `.env`.
- [x] Add docs showing how to move deprecated env values into `ratatoskr.yaml`.

Acceptance evidence:

- [x] Deprecated variables never silently alter runtime behavior.
- [x] User-facing deprecation messages include replacement names.

### 1.5 Cloud Ollama provider configuration

- [x] Add config model fields for optional cloud Ollama/Ollama-compatible endpoints.
- [x] Keep OpenRouter as default provider in docs and code.
- [x] Define structured-output caveats for cloud Ollama.
- [x] Add provider selection validation so users cannot accidentally configure two primary providers without an explicit choice.
- [x] Add smoke test or mocked adapter test for cloud Ollama request/response shape.
- [x] Document tested cloud Ollama endpoint(s) and models once chosen.

Acceptance evidence:

- [x] OpenRouter remains the first quickstart path.
- [x] Cloud Ollama config is optional and documented as a secondary path.

## Phase 2 — Reference deployment as code

### 2.1 Compose profile design

- [x] Decide final profile names: `core`, `with-firecrawl`, `with-cloud-ollama`, `with-monitoring`, `mcp`.
- [x] Make default compose include bot, API/web, Redis, and Chroma.
- [x] Keep web served by FastAPI; avoid a separate frontend runtime container unless justified.
- [x] Ensure API/web auth secrets are required only when browser/API/extension auth is enabled.
- [x] Add compose healthchecks for bot, API, Redis, Chroma, and Firecrawl.
- [x] Remove `firecrawl-api:host-gateway` from the default self-hosted Firecrawl path once a Firecrawl service is added.
- [x] Keep a documented path for using an externally managed Firecrawl service.

Acceptance evidence:

- [x] `docker compose config` succeeds for default and each profile.
- [x] Default stack starts bot/API/Redis/Chroma.
- [x] Firecrawl profile starts an internal Firecrawl service without host-gateway.

### 2.2 Firecrawl service integration

- [x] Choose supported Firecrawl image and dependent services.
- [x] Add Firecrawl API, Redis/Postgres/Playwright/RabbitMQ dependencies only as required by the chosen Firecrawl image.
- [x] Pin image tags or document update policy.
- [x] Set `FIRECRAWL_SELF_HOSTED_ENABLED=true` in compose profile.
- [x] Set `FIRECRAWL_SELF_HOSTED_URL` to the internal service name.
- [x] Align `app/config/scraper.py` defaults with compose behavior.
- [x] Update scraper diagnostics to clearly show self-hosted Firecrawl availability.
- [x] Add smoke command for scraping a known static URL.

Acceptance evidence:

- [ ] `python -m app.cli.summary --url <test-url>` succeeds through self-hosted Firecrawl in profile. `[needs verification: requires pulling/running Firecrawl stack]`
- [x] Diagnostics identify provider order and enabled Firecrawl tier.

### 2.3 Cloud Ollama deployment docs

- [x] Do not start a local Ollama server under the `with-cloud-ollama` profile.
- [x] Add compose/env examples for a remote Ollama-compatible endpoint.
- [x] Add YAML example for cloud Ollama provider selection.
- [x] Document expected auth header/API key handling.
- [x] Document model recommendations and structured JSON limitations.
- [x] Add failure-mode troubleshooting: invalid JSON, timeout, unsupported model, weak extraction quality.

Acceptance evidence:

- [ ] First-summary smoke test passes with a configured cloud Ollama endpoint. `[needs external endpoint]`
- [x] OpenRouter docs remain the primary path.

### 2.4 GHCR release tagging

- [x] Update `.github/workflows/release.yml` to publish `:stable` on non-prerelease semver tags.
- [x] Decide whether `:latest` is also published.
- [x] Add release docs explaining `:stable`, semver tags, and rollback.
- [x] Add dry-run or workflow syntax validation if available.

Acceptance evidence:

- [x] Next release publishes semver and `stable` tags.
- [x] `docs/how-to/migrate-versions.md` references stable tag behavior.

### 2.5 Onboarding recording

- [x] Write exact script for "clone to first summary".
- [ ] Run the script on a clean host or VM. `[needs external clean-host validation]`
- [ ] Capture asciicast or GIF. `[needs external clean-host validation]`
- [ ] Add asset under `docs/assets/`. `[blocked until real recording exists]`
- [x] Link onboarding script from README.
- [ ] Record measured elapsed time and network context. `[needs external clean-host validation]`

Acceptance evidence:

- [x] README links the repeatable "clone to first summary" script.
- [ ] At least one external person successfully follows the flow. `[needs verification]`

## Phase 3 — Signal scoring v0

### 3.1 Generic source schema

- [x] Design `Source`, `Subscription`, `FeedItem`, `Topic`, and `UserSignal` Peewee models.
- [x] Put new migration under `app/cli/migrations/`.
- [x] Map existing `RSSFeed` to `Source(kind="rss")`.
- [x] Map existing `Channel` to `Source(kind="telegram_channel")`.
- [x] Map existing `RSSFeedSubscription` and `ChannelSubscription` to generic `Subscription`.
- [x] Map existing `RSSFeedItem` and `ChannelPost` to generic `FeedItem`.
- [x] Preserve existing IDs or add cross-reference fields for backward compatibility.
- [x] Decide whether old tables become compatibility views, deprecated tables, or are copied then dropped.
- [x] Add data migration tests with RSS and channel fixtures.
- [x] Add rollback/backup notes for table merge.
- [x] Update `docs/reference/data-model.md`.

Acceptance evidence:

- [x] Existing RSS subscriptions and channel digest data survive migration.
- [x] New code can query all sources through generic models.
- [x] Old API routes still use legacy tables; generic tables are a compatibility/backfill layer until worker/API integration lands.

### 3.2 Source and subscription repositories

- [x] Add domain models under `app/domain/models/` or extend existing source models without confusing aggregation `SourceItem`.
- [x] Add repository ports under `app/application/ports/`.
- [x] Add SQLite repository implementations under `app/infrastructure/persistence/sqlite/repositories/`.
- [x] Add unit tests for create/update/list/disable source.
- [x] Add ownership checks even though the service is single-user.
- [ ] Add import/export support if OPML or backup flows should include sources.

Acceptance evidence:

- [x] Application services do not import Peewee models directly.
- [x] Repositories support RSS and Telegram channel source kinds.

### 3.3 Continuous ingestion worker

- [ ] Define worker lifecycle in `app/infrastructure/scheduler/` or existing background processor.
- [ ] Add per-source fetch cadence.
- [ ] Add per-source exponential backoff.
- [ ] Add circuit breaker after N consecutive failures.
- [ ] Add source health fields and status endpoint.
- [ ] Convert existing RSS polling in `app/adapters/rss/feed_poller.py` to generic source ingestion.
- [ ] Convert Telegram channel digest reader in `app/adapters/digest/` into a v0 source ingester.
- [ ] Ensure Telegram channel digest remains user-visible as digest while also feeding signal scoring.
- [ ] Add tests for broken feed/channel behavior.
- [ ] Add metrics for fetched, skipped, errored, deduped, and queued items.

Acceptance evidence:

- [ ] Broken sources cannot hot-loop.
- [ ] Ingestion can be enabled/disabled per source.
- [ ] Telegram channel digest items enter the signal candidate queue.

### 3.4 Cheap filter pipeline

- [x] Add `app/application/services/signal_scoring.py`.
- [x] Define scoring input/output DTOs with evidence fields.
- [x] Implement recency score.
- [x] Implement engagement score for HN/Reddit/Telegram where data exists.
- [x] Implement source diversity penalty.
- [x] Implement canonical URL/title dedupe.
- [ ] Implement MinHash near-duplicate detection.
- [x] Define required Chroma-backed topic similarity port and fail-closed readiness check.
- [ ] Implement concrete Chroma topic similarity adapter.
- [x] Add hard pre-LLM cap so at most 10% of observed items reach judge stage.
- [ ] Persist per-stage evidence in `UserSignal`.
- [x] Add fixture-based tests proving rejection behavior.

Acceptance evidence:

- [x] Test fixture rejects at least 90% before LLM.
- [x] Scoring fails closed or disables signal worker when Chroma is unavailable, per final startup decision.

### 3.5 Chroma-required personalization

- [ ] Define Chroma collection(s) for topics and liked items.
- [ ] Reuse existing embedding provider factory where possible.
- [ ] Add topic embedding generation.
- [ ] Add liked-item embedding backfill.
- [ ] Add health check for Chroma readiness before signal scoring starts.
- [ ] Add admin/status API fields for Chroma signal-scoring health.
- [x] Document behavior when Chroma is down.

Acceptance evidence:

- [x] Signal scoring does not silently degrade to SQLite-only similarity.
- [ ] Admin/status surface shows Chroma readiness.

### 3.6 LLM-as-judge

- [ ] Add bounded judge prompt for top candidate slice.
- [ ] Add or update both `en/` and `ru/` prompt files if current prompt structure requires language parity.
- [ ] Add judge output schema and validator.
- [ ] Add cost and latency logging for judge calls.
- [ ] Add daily/user budget guard.
- [ ] Add retry handling for invalid structured output.
- [ ] Add tests for judge call suppression below threshold.

Acceptance evidence:

- [ ] Less than 10% of observed candidates reach LLM in test fixtures.
- [ ] Judge decisions are persisted with evidence and cost metadata.

### 3.7 Feedback and eval

- [ ] Wire feedback actions: like, dislike, skip, hide source, boost topic.
- [ ] Store feedback in `SummaryFeedback`, `UserSignal`, or a new normalized feedback table.
- [ ] Add CLI command to export eval set.
- [ ] Add CLI command to compute precision@5.
- [ ] Add fixtures under `tests/fixtures/`.
- [ ] Add 2-3 week real-use eval workflow docs.
- [ ] Add web/API endpoints needed by Phase 4 feed UI.

Acceptance evidence:

- [ ] Maintainer can run one command that reports precision@5.
- [ ] Feedback affects later ranking through Chroma/topic preferences.

### 3.8 Agent adaptation

- [ ] Audit `app/agents/base_agent.py`, `multi_source_extraction_agent.py`, `multi_source_aggregation_agent.py`, `relationship_analysis_agent.py`, `summarization_agent.py`, and `validation_agent.py`.
- [ ] Decide which signal stages are agent-owned versus deterministic services.
- [ ] Keep cheap filters outside LLM-style agent abstractions.
- [ ] Add signal-specific agent or adapter only where orchestration/validation benefits.
- [ ] Refactor agent result metadata to carry scoring evidence where useful.
- [ ] Update `docs/multi_agent_architecture.md`.
- [ ] Add tests for adapted agents.

Acceptance evidence:

- [ ] No existing agent layer is deleted wholesale.
- [ ] Signal scoring does not become an all-agent/all-LLM pipeline.

### 3.9 MCP/Hermes contract

- [ ] Define stable MCP read operations for sources, signals, summaries, and stats.
- [ ] Define stable MCP search operations for keyword, semantic, and hybrid retrieval.
- [ ] Define stable MCP write operations for aggregation creation, source/subscription management, and feedback actions as needed.
- [ ] Version tool/resource names or document compatibility guarantees.
- [ ] Add auth/security notes for read/write separation.
- [ ] Update `docs/mcp_server.md`.
- [ ] Add tests for tool/resource registration counts and contracts.

Acceptance evidence:

- [ ] MCP remains read/write/search capable for Hermes.
- [ ] Tool/resource set is intentionally documented, not accidental growth.

## Phase 4 — Finish Carbon rename and lighten design shim

### 4.1 Design shim rename

- [ ] Remove IBM Carbon terminology from comments and type names under `clients/web/src/design/`.
- [ ] Rename `CarbonTagType` and related helpers in `clients/web/src/components/TagPills.tsx`.
- [ ] Rename `.cds--*` CSS compatibility classes in `clients/web/src/styles.css`.
- [ ] Replace `web-carbon-v1` tests with `web-v1`.
- [ ] Update `docs/reference/frontend-web.md` to describe Ratatoskr primitives, not Carbon parity.
- [ ] Keep feature imports through `clients/web/src/design/`.

Acceptance evidence:

- [ ] `rg -n "Carbon|carbon|cds-|web-carbon-v1" clients/web docs/reference/frontend-web.md` is empty or only contains documented migration notes.
- [ ] `cd clients/web && npm run check:static && npm run test` passes.

### 4.2 Token source

- [ ] Choose token file path: `clients/web/tokens/tokens.json` or repo-level `design/tokens.json`.
- [ ] Define color tokens.
- [ ] Define spacing tokens.
- [ ] Define radius tokens.
- [ ] Define typography tokens.
- [ ] Generate or hand-maintain `clients/web/src/design/tokens.css`.
- [ ] Export mobile-consumable JSON shape for future mobile repo use.
- [ ] Document token update process.

Acceptance evidence:

- [ ] Light/dark web themes still render correctly.
- [ ] Token JSON can be consumed outside web without parsing CSS.

### 4.3 Feed/topics UI

- [ ] Add route manifest entries for signal feed and topics.
- [ ] Generate/update API types from `docs/openapi/mobile_api.yaml`.
- [ ] Build ranked queue view.
- [ ] Build source health view.
- [ ] Build topic preferences view.
- [ ] Build feedback controls for like/dislike/skip/hide.
- [ ] Add loading, empty, error, and Chroma-unavailable states.
- [ ] Add tests for route rendering and feedback calls.
- [ ] Verify layout at mobile and desktop widths.

Acceptance evidence:

- [ ] User can triage top signals from `/web`.
- [ ] UI handles no signals, broken source, and Chroma-down states.

### 4.4 Browser extension token follow-up

- [ ] Decide whether browser extension should share tokens in this phase.
- [ ] If yes, add build/copy path for token CSS or variables into `clients/browser-extension/`.
- [ ] If no, document deferral and avoid partial token duplication.

Acceptance evidence:

- [ ] Browser extension styling decision is recorded.

## Phase 5 — X / Reddit / HN / Substack ingestors

### 5.1 Ingester contract

- [ ] Add ingester protocol under `app/application/ports/`.
- [ ] Define lifecycle: configure, fetch, normalize, dedupe, persist, backoff.
- [ ] Define rate-limit behavior.
- [ ] Define auth error behavior.
- [ ] Define permanent versus transient error semantics.
- [ ] Define normalized `FeedItem` metadata contract.
- [ ] Convert RSS/Substack to the contract first.
- [ ] Add contract tests shared by all ingestors.

Acceptance evidence:

- [ ] RSS/Substack use the same interface as HN/Reddit/X.
- [ ] Adding a new ingester does not require touching signal scoring internals.

### 5.2 HN ingester

- [ ] Choose HN API endpoint(s).
- [ ] Implement source config for front page, best, newest, or keyword paths.
- [ ] Normalize URL, title, author, score, comments, and timestamp.
- [ ] Add rate-limit/backoff even if HN is free.
- [ ] Add tests with recorded/mocked HN payloads.
- [ ] Document zero-cost setup.

Acceptance evidence:

- [ ] HN items become generic `FeedItem`s with engagement metadata.

### 5.3 Reddit ingester

- [ ] Decide Reddit auth mode and required credentials.
- [ ] Keep credentials optional/YAML-only unless maintainer decides otherwise.
- [ ] Implement subreddit polling.
- [ ] Enforce 100 req/min free-tier guard and lower default.
- [ ] Normalize score, comments, author, permalink, outbound URL, and timestamp.
- [ ] Add backoff for 429 and auth failures.
- [ ] Add tests with mocked Reddit payloads.
- [ ] Document free-tier limits.

Acceptance evidence:

- [ ] Reddit adapter respects per-source and global rate budgets.

### 5.4 Substack ingester

- [ ] Keep Substack as RSS specialization.
- [ ] Reuse `app/adapters/rss/substack.py` URL resolver.
- [ ] Add tests for publication name, subdomain, post URL, and custom domain.
- [ ] Normalize through generic RSS ingester.
- [ ] Document setup as zero-cost.

Acceptance evidence:

- [ ] Substack source produces generic `FeedItem`s through RSS path.

### 5.5 X/Twitter ingester

- [ ] Keep X/Twitter disabled by default.
- [ ] Require explicit cost acknowledgment such as `TWITTER_INGESTION_ACK_COST=true`.
- [ ] Reuse existing `app/adapters/twitter/` extraction where possible.
- [ ] Document Basic tier cost warning and bring-your-own-token model.
- [ ] Isolate X worker if needed to avoid cost/account-risk spillover.
- [ ] Add startup warning if enabled without credentials/budget acknowledgment.
- [ ] Add tests for disabled-by-default behavior.

Acceptance evidence:

- [ ] Default install never starts X ingestion.
- [ ] Enabling X requires explicit cost acknowledgment.

## Phase 6 — Pyrogram/PyroTGFork to Telethon migration

### 6.1 Usage audit and protocol design

- [ ] Run `rg -n "pyrogram|pyrotgfork|Pyro|Client\\(|filters|raw\\.functions|SessionPasswordNeeded" app tests docs`.
- [ ] List every Pyrogram import and runtime usage.
- [ ] Design internal bot protocol for message send/edit/delete, callbacks, commands, media, albums, forwards, topics, and draft/status updates.
- [ ] Design internal userbot protocol for login/session, channel fetch, metadata, posts, and digest reads.
- [ ] Add characterization tests around current Telegram behavior before swapping implementation.
- [ ] Identify Telethon gaps for raw draft streaming.

Acceptance evidence:

- [ ] Migration scope covers all Telegram code, not only userbot.
- [ ] Protocols isolate app logic from Telethon-specific types.

### 6.2 Bot adapter migration

- [ ] Replace `app/adapters/telegram/telegram_client.py` internals with Telethon.
- [ ] Replace `app/adapters/telegram/telegram_bot.py` internals with Telethon.
- [ ] Update command registration and filters.
- [ ] Update callback query handling.
- [ ] Update forwarded post handling.
- [ ] Update URL submission flow.
- [ ] Update album/media group handling.
- [ ] Update forum topic manager behavior.
- [ ] Update draft/status streaming or fallback behavior.
- [ ] Update tests under `tests/adapters/telegram/`.

Acceptance evidence:

- [ ] Bot commands, callbacks, forwards, URL submissions, albums, and status updates pass tests.
- [ ] No active bot adapter imports Pyrogram.

### 6.3 Userbot/digest migration

- [ ] Replace digest userbot client implementation with Telethon.
- [ ] Update `/init_session` flow in `app/adapters/telegram/command_handlers/init_session_handler.py`.
- [ ] Update `app/adapters/telegram/session_init_state.py`.
- [ ] Add migration or re-auth instructions for existing Pyrogram session files.
- [ ] Keep old session files untouched until Telethon auth succeeds.
- [ ] Add preflight checker CLI for session readiness.
- [ ] Update digest handler tests.

Acceptance evidence:

- [ ] `/init_session` and channel digest fetch work through Telethon.
- [ ] Existing self-hosters have a documented migration path.

### 6.4 Dependency and docs cleanup

- [ ] Add Telethon dependency to `pyproject.toml`.
- [ ] Remove `pyrotgfork` and Pyrogram-specific dependency assumptions once all imports are gone.
- [ ] Regenerate lockfiles.
- [ ] Update `docs/reference/api-contracts.md`, `docs/reference/cli-commands.md`, `docs/SPEC.md`, `docs/tutorials/local-development.md`, and `CHANGELOG.md`.
- [ ] Add release note calling this a breaking Telegram runtime/session migration.
- [ ] Run `rg -n "pyrogram|pyrotgfork|PyroTGFork" app docs tests pyproject.toml`.

Acceptance evidence:

- [ ] Active runtime docs mention Telethon.
- [ ] Any remaining Pyrogram text is migration-history only.

## Release readiness TODO

- [ ] Publish GHCR semver and `stable` tags.
- [ ] Test README quickstart with an external person.
- [ ] Keep `.env.example` at seven or fewer required assignments.
- [ ] Document `ratatoskr.yaml` schema and precedence.
- [ ] Verify default compose reaches first summary in under 10 minutes.
- [ ] Verify self-hosted Firecrawl docs match compose behavior.
- [ ] Document OpenRouter primary and cloud Ollama optional provider paths.
- [ ] Document migration from each prior public version in `CHANGELOG.md`.
- [ ] Test backup and restore for SQLite, Chroma, Redis expectations, downloaded videos, and config.
- [ ] Complete all-Telethon migration.
- [ ] Document MCP read/write/search contract for Hermes.
- [ ] Complete multi-agent adaptation plan.
- [ ] Remove unintentional Carbon names from active web code.
- [ ] Align browser extension and CLI docs with auth/client ID contracts.
- [ ] Regenerate OpenAPI YAML/JSON and mobile API docs for Phase 3 API changes.
- [ ] Run full CI-equivalent checks before v1 tag.

## Cross-phase tracking

### Documentation updates

- [ ] `README.md`
- [ ] `CHANGELOG.md`
- [ ] `docs/DEPLOYMENT.md`
- [ ] `docs/environment_variables.md`
- [ ] `docs/reference/config-file.md`
- [ ] `docs/reference/data-model.md`
- [ ] `docs/reference/frontend-web.md`
- [ ] `docs/mcp_server.md`
- [ ] `docs/MOBILE_API_SPEC.md`
- [ ] `docs/openapi/mobile_api.yaml`
- [ ] `docs/openapi/mobile_api.json`
- [ ] `docs/how-to/migrate-versions.md`
- [ ] `docs/how-to/backup-and-restore.md`
- [ ] `docs/how-to/migrate-from-bite-size-reader.md`

### Validation commands

- [ ] `make format`
- [ ] `make lint`
- [ ] `make type`
- [ ] `pytest tests/ -m "not slow and not integration"`
- [ ] `python -m app.cli.migrate_db --status`
- [ ] `python -m app.cli.summary --url <known-good-url>`
- [ ] `docker compose -f ops/docker/docker-compose.yml config`
- [ ] `docker compose -f ops/docker/docker-compose.yml up`
- [ ] `cd clients/web && npm run check:static && npm run test`
- [ ] OpenAPI sync/regeneration command used by the project

### Open decisions still requiring maintainer input

- [ ] Supported cloud Ollama endpoint(s) and model list.
- [ ] First-run `JWT_SECRET_KEY` behavior for local-only web/API installs.
- [ ] Compatibility view/table strategy while merging RSS/channel tables.
- [ ] Exact Chroma-down behavior for signal scoring startup.
- [ ] Agent ownership split for signal stages.
- [ ] Required Hermes write operations for v0.
- [ ] Whether web admin should expose Redis/Chroma health before Phase 3.
- [ ] Telethon draft streaming parity versus simpler status-message fallback.
