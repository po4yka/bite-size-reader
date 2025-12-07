# YouTube Summary Reliability & UX Improvements
- Doc ID: TD-youtube-summary
- Date: 2025-12-07
- Owner: AI Assistant
- Status: Draft
- Related Docs: REQ_youtube-summary.md, TEST_youtube-summary.md, SPEC.md (YouTube flow)

## Summary
- Improve YouTube summarization by adding transcript fallback to downloaded VTT captions, surfacing video metadata into summarization, tightening error/UX messaging, and enabling storage cleanup under configured budgets.

## Context & Problem
- Current state: Only youtube-transcript-api is used for transcripts; failure returns empty text. yt-dlp already downloads subtitles/metadata but the transcript path ignores them. Notifications cover only start/complete. Storage cleanup is only logged, not executed.
- Gaps: Missing fallback to VTT, metadata not fed into summarization, no explicit dedupe notification, no active cleanup, limited observability for transcript/download outcomes.

## Goals / Non-Goals
- Goals: Reliability of transcript acquisition, clearer user UX/errors, metadata-aware summaries, automated cleanup respecting limits, observability.
- Non-Goals: Changing DB schema, altering non-YouTube flows, new external services.

## Assumptions & Constraints
- yt-dlp remains sync in a thread; avoid heavy dependencies. ffmpeg available. Subtitle download stays enabled. Storage path writable.

## Requirements Traceability
- FR1/FR2/FR3/FR4/FR5 from REQ_youtube-summary mapped to: transcript fallback + metadata injection; user notifications and dedupe reuse message; cleanup routine; logging/metrics.

## Architecture / Flow
- ContentExtractor detects YouTube -> YouTubeDownloader.download_and_extract:
  1) Try youtube-transcript-api with small retry/backoff.
  2) Run yt-dlp download (with subtitles). On success, if transcript empty, parse downloaded VTT and use as transcript (mark source=vtt).
  3) Detect language, build metadata dict, and prepend concise metadata header to transcript for summarization.
  4) Persist video_downloads with transcript_source and subtitle_language; reuse cached downloads when status=completed (inform user).
  5) Return transcript + metadata text to URLProcessor for summarization; rest of pipeline unchanged.
- Storage: before download, compute usage; if over 90% or above limit and auto_cleanup enabled, delete oldest files (by mtime) older than retention days until under 90% or limit; log actions.

## Data & Contracts
- No schema changes. `video_downloads.transcript_source` values expanded to include "vtt" to indicate fallback path. Metadata header included in content_text (title/channel/duration/resolution if available).

## Algorithms / Logic
- Transcript retry: up to 2 attempts with 1s backoff on transient errors (non VideoUnavailable/TranscriptsDisabled).
- VTT parsing: simple text extraction ignoring timestamps/cues. Use subtitle_file_path selected during download; skip if missing.
- Metadata header: `Title: ... | Channel: ... | Duration: Xm Ys | Resolution: ...` + newline + transcript; omitted fields skipped.
- Storage cleanup: compute total bytes under storage_path; collect mp4/info.json/vtt/jpg/png/webp; sort by mtime asc, skip files newer than retention window; delete until under threshold or no candidates; log reclaimed bytes.

## Interfaces / Config
- Reuse existing config keys (`YOUTUBE_*`). No new flags. Cleanup respects `auto_cleanup_enabled`, `max_storage_gb`, `cleanup_after_days`.

## Failure, Reliability, Performance
- Error handling: categorize age-restricted/geo/private/premiere/members-only/timeout as today; add explicit messages for transcript missing after both attempts. Continue summarization with VTT when API fails. If both fail, raise clear error with correlation ID.
- Timeouts: reuse existing yt-dlp behavior; retries only on transcript API.

## Security & Privacy
- No new data; logs keep correlation IDs; avoid logging subtitles content.

## Observability
- New log fields: transcript_source, transcript_fallback_used, vtt_fallback_success, cleanup_reclaimed_bytes, cleanup_candidates. Counters to track transcript_api_failures and vtt_fallback_success (logged).

## Testing Strategy
- Unit tests for transcript fallback, VTT parsing, metadata header, cleanup selection logic, dedupe reuse messaging, and error categorization.
- Integration tests with mocks for youtube-transcript-api and yt-dlp to ensure fallback path and notifications.

## Rollout / Migration
- No migration. Deploy; monitor logs for vtt_fallback and cleanup actions. Rollback by reverting code; no data format changes.

## Risks / Trade-offs
- Subtitle files may be absent; fallback logs and continues. Cleanup could delete files still referenced; mitigated by only deleting older-than-retention and logging.

## Alternatives Considered
- Adding external speech-to-text: rejected (scope/complexity). Using heavy VTT parser dependency: rejected in favor of lightweight parsing.

## Open Questions
- Should we expose transcript_source in user-facing summary footer?
- Do we need a feature flag to disable VTT fallback?
