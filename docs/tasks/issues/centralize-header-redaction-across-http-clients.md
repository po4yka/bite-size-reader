---
title: Centralize Authorization header redaction across HTTP clients
status: backlog
area: observability
priority: low
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Centralize Authorization header redaction across HTTP clients #repo/ratatoskr #area/observability #status/backlog 🔽

## Objective

The GitHub client defines a sealed `_REDACTED_HEADER_KEYS` set (`app/adapters/github/github_api_client.py:32`) but no equivalent constant exists in the scraper providers that also set `Authorization: Bearer <token>` headers. If `DEBUG_PAYLOADS=1` is enabled or an httpx error logs the full request, secrets could leak from scraper providers. A shared redaction helper + reuse across openrouter / github / scraper providers closes the gap and prevents future drift.

## Context

- Scraper bearer-token sites: - `app/adapters/content/scraper/crawl4ai_provider.py:79` - `app/adapters/content/scraper/defuddle_provider.py:166`
- Existing redaction: - `app/adapters/github/github_api_client.py:32` (`_REDACTED_HEADER_KEYS`). - `app/adapters/openrouter/payload_logger.py:34-35`, `request_builder.py:363-365`, `chat_attempt_runner.py:291`.
- No equivalent in scraper providers; no test asserting redaction.

## Scope

- Extract the redaction set + helper into `app/core/logging_utils.py` (or a new `app/security/header_redaction.py`).
- Replace the per-client constants with the shared helper.
- Add a test per HTTP client that captures `logging` output for a forced 401 and asserts the token string is absent from the captured log records and exception messages.

## Acceptance criteria

- [ ] One canonical redaction helper used by openrouter, github, scraper providers.
- [ ] Tests for each client assert no token leak on error paths.
- [ ] mypy + ruff clean.

## References

- GitHub client: `app/adapters/github/github_api_client.py:32`
- Scraper sites: `app/adapters/content/scraper/crawl4ai_provider.py:79`, `app/adapters/content/scraper/defuddle_provider.py:166`
- Openrouter sites: `app/adapters/openrouter/payload_logger.py:34-35`
