# Changelog

All notable changes to Ratatoskr will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Web frontend — mobile-responsive layouts

Adds Frost mobile-artboard fidelity to the React web frontend across
all 17 routes + AppShell. Container queries on the main content area
(`@container main (max-width: 768px)`) drive the breakpoint, isolated
from viewport — so embedded views (drawer, modal, side panel) reflow
off available width.

- **NEW** Mobile cell grid: 48-col below 768px (vs web's 178-col),
  computed live by the boot script in index.html.
- **NEW** Mobile chrome: 54px FrostHeader collapses to wordmark +
  hamburger; FrostSideNav becomes a slide-in drawer; new
  MobileTabBar (56px bottom strip with QUEUE · DIGESTS · TOPICS ·
  SETTINGS, active tab has 4px leading spark).
- **NEW** Mobile-specific tokens: `--frost-spark-mobile` 4px,
  `--frost-tab-bar-height` 56px, `--frost-mobile-header` 54px,
  `--frost-pad-page-mobile` 16px, `--frost-gap-ext` 10px.
- **REWRITE** All 17 routes have designed mobile layouts: tables →
  stacked cards, multi-column grids → single column, BracketTabs →
  horizontal-scroll segmented controls. LibraryPage queue is a
  stacked card list with tap-to-open. ArticlePage reader has a
  fixed-bottom action bar above the tab bar.
- **NEW** Touch targets ≥44×44 across all interactive primitives
  (BracketButton, IconButton, Checkbox, RadioButton, Toggle, Tag,
  Accordion, NumberInput, MonoInput/TextArea/Select, BracketSearch).
- **NEW** Playwright mobile device projects (iPhone 12, Pixel 5,
  iPad Mini) plus a desktop project; existing tests run on all
  projects.
- **NEW** Storybook Frost Mobile (393×690) viewport with a
  responsive default; primitive stories render in mobile by default.
- **FIX** `@storybook/addon-viewport` `INITIAL_VIEWPORTS` import
  (broken since Storybook 8+ API change).
- Bundle delta: index.js 186.09 kB → 188.78 kB (+1.4%) across the
  whole mobile migration; CSS payload absorbs the new mobile.css
  aggregator + 5 group-*.mobile.css per-route files.

### Web frontend — Frost design system migration

Full rewrite of the React web frontend (`clients/web/`) to the Frost
design system: editorial monospace minimalism, two-color rule (ink +
page) with a single critical accent (spark `#DC3545`), eight-step alpha
ladder, brutalism (0 corner radius, 1px hairline borders, no shadows).
See `DESIGN.md` at the repo root for the canonical spec.

- **NEW** Frost component surface: `BracketButton`, `BrutalistCard`,
  `BrutalistTable`, `BrutalistModal`, `BracketTabs`, `BracketPagination`,
  `BracketSearch`, `MonoInput`, `MonoTextArea`, `MonoSelect`,
  `MonoProgressBar`, `BrutalistSkeleton`, `SparkLoading`, `StatusBadge`,
  `Toast`, `RowDigest`, `FrostHeader`, `FrostSideNav`. In-place rewrites
  preserve legacy import names for `Tag`, `Link`, `IconButton`, `Toggle`,
  `Checkbox`, `RadioButton`, `Accordion`, `NumberInput`, `UnorderedList`,
  `CodeSnippet`, `FileUploader`, `Dropdown`, `MultiSelect`,
  `FilterableMultiSelect`, `ContentSwitcher`, `TreeView`, `DatePicker`,
  `TimePicker`.
- **NEW** Self-hosted JetBrains Mono (regular/medium/extrabold) + Source
  Serif 4 italic via `@fontsource` packages. Source Serif body shows up
  in the article reader at 16px / 1.55 line-height.
- **NEW** Storybook visual harness (`@storybook/react-vite`) covering
  primitives in light + dark modes, plus a `web-storybook-build` CI job
  that uploads the `storybook-static/` artifact.
- **REWRITE** All 17 pages (Library, Articles, Article, Search,
  TagManagement, Collections, Submit, ImportExport, Backups, Feeds,
  Webhooks, Rules, Signals, Preferences, Digest, CustomDigestView,
  Admin, Login) and the global AppShell migrated. Page widths snap to
  `strip-N` tokens (176-1408px); horizontal page padding is 32px;
  section gap is 48px; page gap is 64px.
- **REMOVED** Legacy components: `Button`, `Tile`, `TextInput`,
  `TextArea`, `Select`, `Search`, `InlineLoading`, `InlineNotification`,
  `Skeleton`, `ProgressBar`, `ButtonSet`, `Tabs`, `Pagination`,
  `DataTable`, `Modal`, `ComposedModal`, `AppHeader`, `AppSideNav`,
  `StructuredList` (.tsx + .stories.tsx pairs, ~30 files total).
- **REMOVED** Carbon-derived tokens (`--rtk-color-focus`,
  `--rtk-color-success`, `--rtk-color-warning`, `--rtk-color-shadow`,
  `--rtk-radius-sm`, `--rtk-radius-md`) and the back-compat `--rtk-*`
  alias section in `tokens.css`. Frost is now the only token surface.
- Bundle delta: index.js 152.61 kB → 189.74 kB across the migration
  (+24% gross), with the legacy-removal phase recovering 12.99 kB once
  legacy components were dead-code-eliminated.
- All gates green throughout: typecheck, lint, 173 unit/render tests,
  build, build-storybook.

### Breaking — Project renamed to Ratatoskr

The project has been renamed from `bite-size-reader` to `ratatoskr`.
The rename touches Docker image / container names, the default DB
filename, the MCP protocol surface (`bsr://` URIs and `X-BSR-*`
headers), the CLI package and config directory, the Carbon web
storage keys and refresh cookie, all `bsr_*` Prometheus metric
names, and the Loki / Promtail labels. The Karakeep integration
is retired in the same release.

**For the full breaking-change inventory and the operator checklist,
see [docs/how-to/migrate-from-bite-size-reader.md](docs/how-to/migrate-from-bite-size-reader.md).**
The migration page is the canonical source — historical-record
discipline keeps this entry short so the breaking-change list does
not drift from the operational guide.

### Breaking — Telegram runtime migrated to Telethon

Ratatoskr now uses Telethon for both the BotFather-token bot adapter and the
channel-digest userbot session. `pyrotgfork`/Pyrogram and `pytgcrypto` are no
longer runtime dependencies. Existing digest userbot sessions must be recreated
with `/init_session` or `python -m app.cli.init_userbot_session`; the migration
flow keeps the previous `.session` file untouched until a new Telethon session
authenticates successfully, then stores the old file as
`<DIGEST_SESSION_NAME>.legacy.bak.session`.

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
- `pyrotgfork`/Pyrogram and `pytgcrypto` runtime dependencies; Telethon is now the only Telegram client stack.
- `nlp` optional extra group and spaCy trained model dependencies (en_core_web_sm, ru_core_news_sm) -- codebase only uses `spacy.blank()` + sentencizer
- `lock-piptools` Makefile target -- `lock-uv` is the canonical dependency locking path
- `PROMPT.md` -- referenced non-existent migration docs
- `app/grpc/` module, `app/protos/`, and `grpc` optional extra -- aspirational gRPC layer never wired into production
- Duplicate versioned migration modules under `app/db/migrations/`; `app/cli/migrations/` is now the sole canonical migration directory used by runtime startup.

### Security
- Update pyjwt 2.11.0 to 2.12.1 (CVE-2026-32597)

### Changed
- Add Phase 2 compose profiles for self-hosted Firecrawl, remote cloud Ollama, monitoring, and MCP; default compose config now works without a local `.env` file.
- Publish GHCR `:stable` on non-prerelease semver tags and keep `:latest` disabled.
- Reduce `.env.example` to the five first-run Telegram/OpenRouter values and move optional power-user settings to `ratatoskr.yaml`.
- Add optional `RATATOSKR_CONFIG` / `ratatoskr.yaml` loading with precedence below `.env` and process environment.
- Add OpenAI-compatible cloud Ollama configuration (`LLM_PROVIDER=ollama`) while keeping OpenRouter as the default provider.
- Reject deprecated migration shadow-mode environment variables at startup instead of silently accepting them.
- Rename the active web client ID from `web-carbon-v1` to `web-v1`; existing web/browser sessions may need to sign in again.
- Rename Prometheus alert rule names from the historical `BSR*` prefix to `Ratatoskr*`.
- Clarify that current Docker Compose points at an externally managed self-hosted Firecrawl API via `firecrawl-api:host-gateway`; the in-compose Firecrawl profile is planned separately.
- Add `python -m app.cli.migrate_db --status [/path/to/db.sqlite]` for canonical migration status reporting.
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
