# Changelog

All notable changes to Ratatoskr will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Breaking — Project renamed to Ratatoskr

The project has been renamed from `bite-size-reader` to `ratatoskr`. All artifacts that encoded the old name have been updated. Historical entries below this section are preserved as records of past releases.

- **Docker image:** `bite-size-reader:latest` → `ratatoskr:latest`. Pull and update your `docker-compose.yml` or `docker run` invocation accordingly. GHCR image moves to `ghcr.io/po4yka/ratatoskr` (the rename of `po4yka/bite-size-reader` is preserved by GitHub redirects, but pin the new path in CI).
- **Docker Compose service & containers:** Service `bsr` → `ratatoskr`. Container names `bsr-bot`, `bsr-mobile-api`, `bsr-mcp`, `bsr-mcp-write`, `bsr-mcp-public`, `bsr-redis`, `bsr-chroma`, plus monitoring containers `bsr-prometheus|grafana|loki|promtail|node-exporter` → `ratatoskr-*`. Recreate containers after updating compose.
- **Default database filename:** `/data/app.db` → `/data/ratatoskr.db`. On first start, `DatabaseSessionManager` automatically renames an existing `app.db` next to the new path. Custom `DB_PATH` values that don't end in `ratatoskr.db` are not auto-migrated; rename manually if desired.
- **Pyrogram session name:** `bite_size_reader_bot` → `ratatoskr_bot`. Sessions run `in_memory=True`, so no disk migration is needed.
- **MCP protocol surface:** Resource URIs `bsr://...` → `ratatoskr://...` (15 resources). MCP server registration name `"bite-size-reader"` → `"ratatoskr"`. HTTP gateway header defaults `X-BSR-Forwarded-Access-Token` and `X-BSR-MCP-Forwarding-Secret` → `X-Ratatoskr-*`. Update MCP-client configs (OpenClaw, Claude Desktop, hosted SSE) accordingly.
- **CLI client (`clients/cli/`):** Python package `bsr_cli` → `ratatoskr_cli`. Console script `bsr` → `ratatoskr`. Config directory `~/.config/bsr/` → `~/.config/ratatoskr/` (existing tokens are not migrated; run `ratatoskr login` again). Env var `BSR_SERVER_URL` → `RATATOSKR_SERVER_URL`. Class names `BSRConfig`/`BSRClient`/`BSRError` → `RatatoskrConfig`/`RatatoskrClient`/`RatatoskrError`.
- **Web frontend:** npm package `bite-size-reader-web` → `ratatoskr-web`. CSS variable namespace `--bsr-*` → `--ratatoskr-*`, animation classes `bsr-shimmer`/`bsr-fade-in` → `ratatoskr-*`. localStorage key `bsr_web_auth_tokens` → `ratatoskr_web_auth_tokens` (logs out existing browser sessions on first load).
- **Browser extension:** Context-menu IDs `bsr-save-page`/`bsr-save-selection` → `ratatoskr-*`.
- **HTTP cookies and Redis keys:** Refresh-cookie `bsr_refresh_token` → `ratatoskr_refresh_token` (existing browser sessions log out). Redis prefix default `bsr` → `ratatoskr`; cache keys `bsr:batch:*`, `bsr:query:*`, `bsr:embed:*`, `bsr:auth:*` → `ratatoskr:*`. Existing keyspace will be ignored — flush old keys after deploy if you want to reclaim memory.
- **Webhook headers:** Outgoing webhook headers `X-BSR-Signature` and `X-BSR-Event` → `X-Ratatoskr-*`. Update webhook receivers to the new header names.
- **Prometheus metrics:** All `bsr_*` metric names → `ratatoskr_*` (~28 metrics). Existing time-series in Prometheus stop collecting under the old name — recording rules and Grafana dashboards have been updated. If you operate long-retention dashboards, plan a query backfill or accept a gap.
- **Grafana dashboards:** Files renamed `bsr-overview.json` → `ratatoskr-overview.json`, `bsr-aggregation.json` → `ratatoskr-aggregation.json`. Folder `Bite-Size Reader` → `Ratatoskr`. Provider `BSR Dashboards` → `Ratatoskr Dashboards`. Dashboard UIDs are also renamed; bookmarks need updating.
- **Loki / Promtail:** `tenant_id`, `job` label, log path `/var/log/bsr/` → `ratatoskr`. If you rely on the old labels in queries, update them.
- **Backup filenames:** SQLite dump prefix `bite_size_reader_backup_` → `ratatoskr_backup_`. ZIP archive prefix `bsr-backup-` → `ratatoskr-backup-`. Existing backups keep their old filenames; only newly created backups use the new prefix.
- **OpenAPI server URLs:** Production `bitsizereaderapi.po4yka.com` → `ratatoskrapi.po4yka.com`. The DNS change is not part of this PR; update DNS separately.
- **`.env.example`:** `OPENROUTER_HTTP_REFERER`, `OPENROUTER_X_TITLE`, `FIRECRAWL_SELF_HOSTED_API_KEY` (default `fc-bsr-local` → `fc-ratatoskr-local`), `REDIS_PREFIX` (default `bsr` → `ratatoskr`), and the example paths for the external Rust runtime binaries (`bsr-summary-contract`, `bsr-pipeline-shadow`, `bsr-interface-router`, `bsr-telegram-runtime`) have been updated to the new naming. The Karakeep block (`KARAKEEP_*` env vars) is removed entirely — the integration has been retired. **Note:** the actual Rust runtime binaries live in a separate repository and were not renamed here; if/when they are renamed, update env values accordingly. Until then, point the `*_RUST_BIN` overrides at the actual binary names on disk.
- **Generated assets:** `app/static/digest/assets/index-*.js` is a built artifact that still encodes `bsr_library_filter` localStorage. Rebuild the digest mini-app to regenerate it.

#### Migration steps for self-hosters

1. **Pull the new image / rebuild:**
   ```sh
   docker compose -f ops/docker/docker-compose.yml down
   docker compose -f ops/docker/docker-compose.yml build
   docker compose -f ops/docker/docker-compose.yml up -d
   ```
2. **Update `.env`** to apply the new defaults if you previously copied the example: `FIRECRAWL_SELF_HOSTED_API_KEY`, `REDIS_PREFIX`, and the `*_RUST_BIN` paths if you customized them. Drop any `KARAKEEP_*` lines — the Karakeep integration has been retired.
3. **DB filename** is auto-migrated on first start when the configured `DB_PATH` ends in `ratatoskr.db` and `app.db` exists in the same directory. No action needed for the default config.
4. **CLI users:** reinstall (`pip install -e clients/cli` or `pipx reinstall ratatoskr-cli`), then run `ratatoskr login` again to recreate the config under `~/.config/ratatoskr/`. Set `RATATOSKR_SERVER_URL` instead of `BSR_SERVER_URL` if you used the env override.
5. **Web users:** browser sessions and saved tokens must be re-acquired (storage-key rename); just sign in again.
6. **MCP clients:** update server URIs from `bsr://` to `ratatoskr://`, and (for trusted-gateway deployments) update header names from `X-BSR-*` to `X-Ratatoskr-*`.
7. **Webhook receivers:** update header parsing from `X-BSR-Signature` / `X-BSR-Event` to `X-Ratatoskr-*`.
8. **Grafana / Prometheus:** existing dashboards are replaced with the renamed files; old metric series retain their `bsr_*` names in TSDB and stop collecting from this release. If you need historical continuity, write a recording rule that aliases the old name to the new one.
9. **CI image references:** if your downstream pipelines pin `ghcr.io/po4yka/bite-size-reader:*`, switch to `ghcr.io/po4yka/ratatoskr:*`. GitHub redirects keep the old path working but the redirect can break with login flows.

### Added
- Channel digest subsystem with userbot, scheduler, and commands (`/digest`, `/channels`, `/subscribe`, `/unsubscribe`)
- Bot-mediated userbot session initialization via `/init_session` with Telegram Mini App OTP/2FA flow
- gRPC service implementation with comprehensive Python client library and integration tests
- Quality assessment and web verification in summary output
- Critical analysis and caveats sections in summaries
- Embedded image analysis support in PDFs and web articles
- PDF metadata extraction, table of contents parsing, and improved layout handling
- Language filtering in SearchFilters
- Progress tracking for PDF processing and batch operations
- Editable progress messages for LLM and YouTube processing in Telegram
- Typing indicators for long-running operations in Telegram bot
- Full logging and dynamic status updates for batch processing
- Redirect-aware X article link resolver with structured reason codes (`path_match`, `redirect_match`, `canonical_match`, `not_article`, `resolve_failed`)
- Optional manual live smoke script for X article links (`scripts/twitter_article_live_smoke.py`) with per-link JSON diagnostics

### Removed
- `nlp` optional extra group and spaCy trained model dependencies (en_core_web_sm, ru_core_news_sm) -- codebase only uses `spacy.blank()` + sentencizer
- `lock-piptools` Makefile target -- `lock-uv` is the canonical dependency locking path
- `PROMPT.md` -- referenced non-existent migration docs
- `app/grpc/` module, `app/protos/`, and `grpc` optional extra -- aspirational gRPC layer never wired into production

### Security
- Update pyjwt 2.11.0 to 2.12.1 (CVE-2026-32597)

### Changed
- Replace `uv pip compile --extra dev` with `uv export --only-group dev` across CI workflows, Makefile, and scripts (PEP 735 dependency groups)
- Add retry wrapper around `uv lock --check` in CI to handle transient GitHub CDN failures
- Prune stale paths from coverage_includes.txt and file_size_baseline.json
- Renamed ContentExtractor methods (breaking change for tests)
- Improved PDF extraction flow with async processing and enhanced Russian language detection
- Enhanced "Analyzing with AI" messages with additional context
- Made input validation less strict for better usability
- Hardened X article extraction flow with strict article-path matching plus redirect/canonical resolution before routing
- Added article-stage metadata fields for observability (`article_resolution_reason`, `article_resolved_url`, `article_canonical_url`, `article_id`, `article_extraction_stage`)
- Added Twitter article config flags (`TWITTER_ARTICLE_REDIRECT_RESOLUTION_ENABLED`, `TWITTER_ARTICLE_RESOLUTION_TIMEOUT_SEC`, `TWITTER_ARTICLE_LIVE_SMOKE_ENABLED`)
- Rust interface routing now treats query-suffixed public endpoints (`/health?*`, `/metrics?*`, `/docs?*`, `/openapi.json?*`) as handled routes.
- Rust summary aggregation now trims whitespace-padded numeric strings before parsing (`" 3 "` -> `3`).
- Rust logging bootstrap now falls back to `info` instead of panicking on invalid log-level config.
- Telegram orchestration flow now delegates lifecycle, callback action execution, and URL policy/state to focused collaborators (`TelegramLifecycleManager`, `CallbackActionRegistry` + `CallbackActionService`, `URLBatchPolicyService`, `URLAwaitingStateStore`).
- Mobile API digest/system routers now delegate orchestration to dedicated services (`DigestFacade`, `SystemMaintenanceService`) instead of in-router DB/Redis/file workflows.
- Formatter component boundaries now enforce protocol interfaces at constructor/public seams rather than concrete `*Impl` coupling.
- Project docs refreshed to reflect current architecture boundaries and service decomposition across Telegram/API/formatting flows.
- Project documentation refreshed for dual frontend setup, including a new Carbon web frontend guide (`FRONTEND.md`) and updated deployment/local-dev/quickstart/spec/API docs.
- Project documentation refreshed for mixed-source aggregation coverage, rollout flags, bundle observability, and FastAPI aggregation endpoints.

### Fixed
- Updated tests for renamed ContentExtractor methods
- Fixed PDF processing async extraction and Russian detection issues
- Fixed batch processing stalls with improved UX and logging
- Limited verification scope to prevent performance issues
- Implemented integrity checks for data validation
- Improved Playwright X article scraping reliability by moving to locator-first readiness and selector fallback diagnostics
- Fixed Unicode boundary corruption in Rust `questions_answered` parsing for `Question:/Answer:` textual payloads.
- Fixed Rust entity normalization to avoid emitting metadata-only values (for example `type`, `confidence`) as entity names.
- Fixed protocol seam drift in response formatting stack by aligning protocol contracts with actual consumer method signatures (message-thread safe replies, admin logging, draft controls, text/link helpers, and summary forwarding signatures).

## Release History

_This project is currently in active development. Formal versioned releases will be documented here._

---

## How to Contribute to This Changelog

When submitting a pull request:

1. Add your changes under the `[Unreleased]` section
2. Use one of these categories: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`
3. Write in the imperative mood ("Add feature" not "Added feature")
4. Link to relevant issues or PRs where applicable
5. Credit contributors with `@username` or full name

### Category Guidelines

- **Added** for new features
- **Changed** for changes in existing functionality
- **Deprecated** for soon-to-be removed features
- **Removed** for now removed features
- **Fixed** for any bug fixes
- **Security** for vulnerability fixes

## Versioning Strategy

This project follows [Semantic Versioning](https://semver.org/):

- **MAJOR** version for incompatible API changes
- **MINOR** version for backwards-compatible functionality additions
- **PATCH** version for backwards-compatible bug fixes

---

**Maintainers:** When cutting a release, move unreleased changes to a new version section with:
- Version number and release date: `## [1.0.0] - 2026-02-09`
- GitHub compare link at bottom: `[1.0.0]: https://github.com/po4yka/bite-size-reader/compare/v0.9.0...v1.0.0`
- Contributor acknowledgments
