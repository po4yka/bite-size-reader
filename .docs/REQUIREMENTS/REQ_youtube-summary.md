# YouTube Summary Reliability & Quality
- Requirement ID: REQ-youtube-summary
- Date: 2025-12-07
- Owner: AI Assistant
- Status: Draft
- Related Docs: TD_youtube-summary.md, TEST_youtube-summary.md

## Background
- Problem statement: YouTube link summarization can fail when transcripts are missing, error messages are inconsistent, and storage cleanup is manual. Summaries lack consistent metadata context (title/channel/duration), and user notifications are minimal.
- Objectives: Increase successful summarizations with reliable transcripts/downloads, improve user-visible messaging, and keep storage within configured budgets.

## Personas & Use Cases
- Persona: Bot owner consuming summaries of YouTube videos via Telegram.
- User story: As an owner, when I send a YouTube link, I want a concise, accurate summary with video context and predictable progress/error messages, even if transcripts are missing, without running out of storage.
- Preconditions: Bot configured with YouTube download enabled, ffmpeg present, valid API keys, storage path writable.

## Scope
- In scope: Transcript/download reliability, metadata propagation to summarization, Telegram UX messaging for YouTube flow, storage limit enforcement/cleanup, tests and observability for the YouTube pipeline.
- Out of scope: Non-YouTube content, mobile API changes, DB schema changes beyond existing `video_downloads`.

## Functional Requirements
- FR1: When `youtube-transcript-api` fails or returns empty, the system must attempt VTT subtitle fallback from downloaded files before declaring no transcript.
- FR2: Summaries must include video context (title, channel, duration when available) in the text passed to the summarizer or via structured fields.
- FR3: User notifications must cover start, reuse/dedupe, completion, and clear categorized errors with correlation IDs.
- FR4: If a video is already downloaded and summarized, the bot must reuse cached artifacts and inform the user.
- FR5: Storage management must respect `YOUTUBE_MAX_STORAGE_GB` and `YOUTUBE_CLEANUP_AFTER_DAYS`, triggering cleanup automatically when over budget or nearing thresholds.

## Non-Functional Requirements
- Performance: End-to-end YouTube summarization should normally complete within 90s for <=20 minute videos on default settings.
- Reliability/Availability: ≥95% of eligible YouTube requests should return a summary or a clear actionable error on first attempt; transcript availability (API+VTT fallback) should cover ≥95% of supported videos.
- Observability: Logs must include correlation IDs, transcript source, fallback path taken, and storage cleanup actions. Key counters: transcript_api_failures, transcript_vtt_fallback_success, youtube_download_errors by category.

## Constraints & Assumptions
- Constraint: No new external services beyond yt-dlp and youtube-transcript-api; avoid heavy dependencies.
- Constraint: Must remain async-safe; yt-dlp stays in threads.
- Assumption: ffmpeg available; storage path writable; subtitles are downloaded by yt-dlp when available.

## Dependencies
- Upstream: YouTube availability, youtube-transcript-api, yt-dlp, filesystem capacity.
- Downstream: OpenRouter summarization pipeline, DB persistence, ResponseFormatter Telegram messaging.

## Acceptance Criteria
- AC1: For a video with manual subtitles removed and auto-captions present, the system falls back to VTT and produces a summary.
- AC2: For an already-downloaded video, the bot skips re-download, informs the user, and returns a summary without duplicate DB rows.
- AC3: When storage exceeds configured budget, cleanup runs and logs actions; downloads proceed or fail with a clear message if budget cannot be reclaimed.
- AC4: User-facing errors are categorized (age-restricted, geo-blocked, private/deleted, rate-limit, transcript-missing) with correlation IDs.

## Metrics
- Success metrics: transcript coverage >=95%; YouTube summary success rate >=95%; storage cleanup keeps usage <90% of max; user-visible error rate <5% of YouTube requests; median YouTube summarization latency <=90s.

## Open Questions
- Should we persist a flag indicating VTT fallback usage in `video_downloads`? (not required if only logged)
- Do we need per-chat rate limits for heavy YouTube downloads?
