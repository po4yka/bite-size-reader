# Test Plan: YouTube Summary Reliability & UX
- Doc ID: TEST_youtube-summary
- Date: 2025-12-07
- Owner: AI Assistant
- Status: Draft
- Related Docs: REQ_youtube-summary.md, TD_youtube-summary.md

## Scope & Objectives
- Validate YouTube transcript/download reliability, metadata-aware summarization input, user notifications, and storage cleanup behavior.
- Excludes non-YouTube flows and mobile API.

## Test Approach
- Types: Unit (transcript fallback, VTT parsing, metadata header, cleanup selection), Integration (yt-dlp + transcript API mocks), targeted E2E via CLI optional.
- Mock youtube-transcript-api and yt-dlp; use temp directories for storage.

## Environments & Tooling
- Python 3.13, pytest/pytest-asyncio. Run via `uv run pytest`.
- Temp storage path to avoid touching real `/data/videos`.

## Test Cases
- TC1 Transcript manual success: API returns manual transcript -> summary uses API, transcript_source=youtube-transcript-api.
- TC2 Transcript auto success: Manual missing, auto-generated used -> transcript_source=youtube-transcript-api, auto_generated=True.
- TC3 Transcript API failure fallback: API raises; VTT exists from download -> parsed text returned, transcript_source=vtt, summary proceeds.
- TC4 Transcript API + VTT missing: Both fail -> user-facing error with correlation ID, request marked error.
- TC5 Dedupe reuse: Existing completed download -> no re-download, user informed of reuse, summary returned.
- TC6 Metadata header: Returned content includes title/channel/duration; summarizer input contains header prefix.
- TC7 Storage cleanup: When usage > limit, cleanup removes oldest eligible files (>retention), logs reclaimed bytes; if cannot reclaim, error surfaced before download.
- TC8 Notification flow: start, reuse, completion notifications sent; errors categorized with correlation IDs.
- TC9 Error categorization: Age-restricted/geo-blocked/premiere/member-only/timeouts mapped to friendly messages.

## Regression Coverage
- Ensure non-YouTube flows unaffected (smoke: article URL path still works).

## Non-Functional
- Latency sanity: typical flow completes <90s for mocked downloads.

## Entry / Exit Criteria
- Entry: New code merged, mocks available, temp storage configured.
- Exit: All above cases passing; no new lint/type failures.

## Risks & Mitigations
- Mock drift from yt-dlp: keep fixtures updated with sample info.json. Use lightweight stubs.

## Reporting
- Track pass/fail in CI; monitor logs for vtt_fallback_success and cleanup actions.
