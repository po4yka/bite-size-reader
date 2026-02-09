# Changelog

All notable changes to Bite-Size Reader will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
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

### Changed
- Renamed ContentExtractor methods (breaking change for tests)
- Improved PDF extraction flow with async processing and enhanced Russian language detection
- Enhanced "Analyzing with AI" messages with additional context
- Made input validation less strict for better usability

### Fixed
- Updated tests for renamed ContentExtractor methods
- Fixed PDF processing async extraction and Russian detection issues
- Fixed batch processing stalls with improved UX and logging
- Limited verification scope to prevent performance issues
- Implemented integrity checks for data validation

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
