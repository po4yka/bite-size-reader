---
title: Wire ScraperAttemptRecorder into the scraper chain orchestrator
status: backlog
area: scraper
priority: high
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Wire ScraperAttemptRecorder into the scraper chain orchestrator #repo/ratatoskr #area/scraper #status/backlog ⏫

## Objective

`ScraperAttemptRecorder` and `serialize_attempt_log` exist (`app/adapters/content/scraper/attempt_log.py`), and migration `0015` added `CrawlResult.attempt_log` (JSON) + `CrawlResult.winning_provider` columns (commit `67bd1771`), but the chain orchestrator never instantiates the recorder. The migration ships NULL forever and operators have to reconstruct chain failures from log scraping instead of querying one column.

## Context

- Recorder defined: `app/adapters/content/scraper/attempt_log.py`.
- Only callers in `app/`: the module itself and the matching columns (`app/db/models/core.py:411-415`, comment "populated… when chain wiring lands").
- Chain walks providers at `app/adapters/content/scraper/chain.py:92-263`, appends to a local `errors: list[str]`, returns a `FirecrawlResult` (line 258) — never instantiates a recorder, never serializes to JSON, never sets `winning_provider`.
- Completion record (`docs/tasks/COMPLETION-2026-05-17.md`) flags this as inline TODO #2.

## Scope

- In `ContentScraperChain.scrape_markdown` (`app/adapters/content/scraper/chain.py`): - Instantiate `ScraperAttemptRecorder` at the top. - Record one `ScraperAttemptEntry` per provider with status (`success|error|timeout|skipped`), latency_ms, error message (if any), and bytes_extracted (on success). - Serialize via `serialize_attempt_log` and pass through to the persisted `CrawlResult.attempt_log`. - Fill `CrawlResult.winning_provider` with the provider name on success; leave NULL on total chain failure.

## Acceptance criteria

- [ ] Every `CrawlResult` row written by the chain has a non-null `attempt_log` JSON.
- [ ] `winning_provider` is populated on success, NULL on total failure.
- [ ] Test that exercises 2 failures + 1 success asserts the JSON shape matches `ScraperAttemptEntry` and `winning_provider` equals the third provider's name.
- [ ] Existing scraper-chain success path tests still pass without modification (additive change).

## References

- Recorder: `app/adapters/content/scraper/attempt_log.py`
- Chain: `app/adapters/content/scraper/chain.py:92-263`
- Model: `app/db/models/core.py:CrawlResult` (lines 411-415)
- Migration: `app/db/alembic/versions/0015_add_crawl_result_attempt_log.py`
- Completion record: `docs/tasks/COMPLETION-2026-05-17.md` (inline TODO #2)
