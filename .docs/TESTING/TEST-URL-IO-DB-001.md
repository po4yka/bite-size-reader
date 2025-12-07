# URL IO/DB Separation Test Plan
- Date: 2025-12-07
- Owner: AI Assistant (with user)
- Related Docs: .docs/TECH_DESIGNS/TD-URL-IO-DB-001.md, .docs/PROPOSALS/PRP-URL-IO-DB-001.md

## Scope & Objectives
- Validate that Firecrawl/OpenRouter network calls run under semaphores without being blocked by DB writes.
- Ensure dedupe, status updates, notifications, translation/insight flows remain correct.
- Confirm resilience when persistence fails or DB is slow.

## Test Approach
- Unit and integration tests with async mocks for Firecrawl/OpenRouter and DB.
- Inject artificial DB latency to verify concurrency is preserved.
- Use TaskGroup-friendly assertions to ensure IO completes even when persistence is delayed.

## Environments & Tooling
- `uv run pytest` with asyncio fixtures; existing mock helpers for Firecrawl/OpenRouter/DB.
- Config defaults; no new env vars required.

## Test Cases
- TC1: Firecrawl IO completes while DB write is delayed; semaphore not held during persistence; multiple URLs run concurrently.
- TC2: LLM summarize (single-pass) completes while summary upsert is delayed; responses still sent; status updated after delay.
- TC3: Chunked summarization path: multiple chunk LLM calls complete; persistence occurs post-IO; translation/insight tasks do not block main completion.
- TC4: Persistence failure after IO logs error, keeps request status best-effort, and does not retry network calls.
- TC5: Dedupe/cached summary path unaffected and still short-circuits without extra IO.

## Regression Coverage
- Ensure existing error-handling tests still pass (`test_firecrawl_error_handling`, summary contract tests, URL handler flow).

## Non-Functional
- Concurrency/resilience under simulated DB latency; basic timing asserts to confirm overlap.

## Entry / Exit Criteria
- Entry: design approved, mocks available.
- Exit: new tests pass; existing suites unaffected.

## Risks & Mitigations
- Risk: timing-sensitive tests flaky; Mitigation: use deterministic clocks and bounded timeouts.

## Reporting
- CI pytest output; document notable timing metrics in PR notes if needed.
