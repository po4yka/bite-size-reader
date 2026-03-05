# Changelog

All notable changes to Bite-Size Reader will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Channel digest subsystem with userbot, scheduler, and commands (`/digest`, `/channels`, `/subscribe`, `/unsubscribe`)
- Bot-mediated userbot session initialization via `/init_session` with Telegram Mini App OTP/2FA flow
- gRPC service implementation with comprehensive Python client library and integration tests
- Quality assessment and web verification in summary output
- Critical analysis and caveats sections in summaries
- Embedded image analysis support in PDFs and web articles
- PDF metadata extraction, table of contents parsing, and improved layout handling
- Language filtering in SearchFilters
- Karakeep bookmark sync command (`/sync_karakeep`) in Telegram bot menu
- Progress tracking for PDF processing and batch operations
- Editable progress messages for LLM and YouTube processing in Telegram
- Typing indicators for long-running operations in Telegram bot
- Full logging and dynamic status updates for batch processing
- Redirect-aware X article link resolver with structured reason codes (`path_match`, `redirect_match`, `canonical_match`, `not_article`, `resolve_failed`)
- Optional manual live smoke script for X article links (`scripts/twitter_article_live_smoke.py`) with per-link JSON diagnostics

### Changed
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

### Fixed
- Updated tests for renamed ContentExtractor methods
- Fixed PDF processing async extraction and Russian detection issues
- Fixed batch processing stalls with improved UX and logging
- Limited verification scope to prevent performance issues
- Implemented integrity checks for data validation
- Improved Playwright X article scraping reliability by moving to locator-first readiness and selector fallback diagnostics
- Fixed Unicode boundary corruption in Rust `questions_answered` parsing for `Question:/Answer:` textual payloads.
- Fixed Rust entity normalization to avoid emitting metadata-only values (for example `type`, `confidence`) as entity names.

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
