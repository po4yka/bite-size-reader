# Multi-Source Aggregation Roadmap

## Goal

Implement a first-class aggregation workflow that can ingest and synthesize information from:

- X post
- X article
- Threads post
- Instagram post
- Instagram carousel
- Instagram reel
- Web article
- Telegram post
- Telegram post with images
- YouTube video

The end state is a single AI-agent-driven pipeline that can accept one or many mixed sources, extract the relevant content from each source, normalize it into a shared representation, and generate one aggregated summary with source-aware provenance.

## Current Gaps

- Only YouTube and X have first-class platform extractors.
- Threads and Instagram have no dedicated extraction path.
- Aggregation exists only for URL batches and only after relationship detection.
- There is no mixed-source bundle request model.
- Telegram forwarded posts with caption text ignore attached images.
- Telegram albums/carousels are not treated as a single source unit.
- X extraction keeps alt text but does not pass image URLs into the multimodal summary path.
- Non-YouTube video extraction is missing.
- Article image-aware summarization exists only as an optional partial path and is off by default.

## Phase 1: Foundations

### Objective

Introduce shared domain and persistence primitives for mixed-source aggregation.

### TODO

- [ ] Add a `SourceKind` enum for all supported source types.
- [ ] Add a normalized `SourceItem` model that represents one extracted source.
- [ ] Add a `SourceBundle` / `AggregationRequest` model for multi-source input.
- [ ] Add a `NormalizedSourceDocument` schema for extracted text, media, metadata, and provenance.
- [ ] Add an `AggregationSession` persistence model separate from URL batch analysis.
- [ ] Add `AggregationSessionItem` persistence to link one session to many extracted requests.
- [ ] Define stable IDs and dedupe rules for source items inside an aggregation session.
- [ ] Decide how bundle-level and item-level failures are stored and surfaced.

### Deliverables

- Shared source models in the domain/application layer.
- Database migration for aggregation session storage.
- Clear contract for what every extractor must return.

## Phase 2: Unified Extraction Orchestrator

### Objective

Build one orchestration path that accepts heterogeneous inputs and dispatches each item to the correct extractor.

### TODO

- [ ] Add a `MultiSourceExtractionAgent` or equivalent orchestrator for source bundles.
- [ ] Add source classification for URLs and Telegram-native submissions.
- [ ] Route each source item to a dedicated extractor or fallback extractor.
- [ ] Support mixed inputs in one request: links, forwarded Telegram posts, and media attachments.
- [ ] Allow aggregation even when sources are unrelated; relationship analysis should enrich the result, not gate it.
- [ ] Add partial-success behavior so one failed source does not discard the whole bundle.
- [ ] Return item-level extraction status, normalized payload, and error diagnostics.

### Deliverables

- A single entry point for mixed-source aggregation.
- Item-level extraction results ready for synthesis.

## Phase 3: Threads and Instagram Coverage

### Objective

Close the largest platform coverage gaps with first-class extractors.

### TODO

- [ ] Add a Threads URL detector and extractor.
- [ ] Support Threads post text, quoted context, images, and video metadata where available.
- [ ] Add Instagram URL detectors for post, carousel, and reel URLs.
- [ ] Add an Instagram post extractor for caption text and metadata.
- [ ] Add an Instagram carousel extractor that treats the full carousel as one source item.
- [ ] Add an Instagram reel extractor for caption, OCR/frame analysis, and audio/transcript fallback where feasible.
- [ ] Define authenticated vs unauthenticated extraction strategy for Meta surfaces.
- [ ] Add platform-specific quality checks and fallback tiers for login-wall or low-value extraction.

### Deliverables

- First-class support for Threads, Instagram posts, Instagram carousels, and Instagram reels.

## Phase 4: Telegram Multimodal Completion

### Objective

Fix Telegram-specific routing so forwarded posts and albums are extracted as complete multimodal sources.

### TODO

- [ ] Change forwarded Telegram post routing so `caption + images` is handled as one multimodal source, not text-only.
- [ ] Add a Telegram post extractor that combines text, caption, and media into one normalized source item.
- [ ] Add album/media-group detection using Telegram grouping metadata.
- [ ] Treat Telegram albums as one source item with ordered images.
- [ ] Support forwarded posts with images even when text exists.
- [ ] Support forwarded posts with image-only content plus OCR/vision extraction.
- [ ] Decide whether Telegram videos should enter the non-YouTube video extraction flow.
- [ ] Preserve Telegram provenance: source chat, original post ID, sender metadata, and media order.

### Deliverables

- Correct multimodal extraction for forwarded Telegram posts and Telegram albums.

## Phase 5: X and Article Multimodal Upgrades

### Objective

Close the remaining multimodal gaps in existing X and article support.

### TODO

- [ ] Pass X image URLs into the platform extraction result instead of dropping them.
- [ ] Preserve X image alt text and media URLs together in the normalized source document.
- [ ] Support X posts with multiple images as true multimodal inputs to the summarizer.
- [ ] Decide whether quoted-post media should be included in the same source item.
- [ ] Enable article image extraction for summarization when image URLs are present.
- [ ] Review Firecrawl image extraction defaults and rollout strategy.
- [ ] Make article vision summarization production-ready instead of config-hidden partial support.
- [ ] Add quality checks to avoid feeding logos, trackers, and decorative images into the summary path.

### Deliverables

- Existing X and article extraction paths become consistently multimodal.

## Phase 6: Video Extraction Beyond YouTube

### Objective

Add a reusable video-capable extraction layer for reels and other short-form video sources.

### TODO

- [ ] Define a shared `VideoSourceExtractor` interface for YouTube, Instagram reels, Telegram videos, and future platforms.
- [ ] Reuse the strongest parts of the YouTube flow: transcript lookup, metadata extraction, persistence, and fallback handling.
- [ ] Add OCR/frame-sampling fallback for videos without transcripts.
- [ ] Add audio transcription fallback for supported non-YouTube video sources.
- [ ] Add storage, cleanup, and size limits for downloaded video assets outside YouTube.
- [ ] Add media provenance so the final summary can reference transcript vs OCR vs frame-derived facts.
- [ ] Add timeout and cost controls for video-heavy bundles.

### Deliverables

- A common video extraction path that supports short-form social video, not only YouTube.

## Phase 7: Aggregated Synthesis and Output Contract

### Objective

Move from "combined summary for related URLs" to "bundle synthesis for mixed source sets".

### TODO

- [ ] Add a `MultiSourceAggregationAgent` that synthesizes normalized source items into one output.
- [ ] Make bundle synthesis independent from relationship detection.
- [ ] Keep relationship analysis as an optional enrichment signal inside the final output.
- [ ] Add cross-source dedupe and contradiction detection.
- [ ] Add provenance-aware synthesis so each key claim can be traced back to one or more source items.
- [ ] Add source weighting rules for text, images, OCR, transcript, and metadata-derived facts.
- [ ] Add a new output shape for aggregated summaries if the existing summary contract is too article-centric.
- [ ] Decide how `source_type` should work for mixed bundles.
- [ ] Add "source coverage" fields so the UI can show which bundle items were actually used.

### Deliverables

- One aggregation output that works for related and unrelated mixed sources.

## Phase 8: API, Telegram UX, and Product Surface

### Objective

Expose the new capability through user-facing entry points.

### TODO

- [ ] Add a Telegram command and routing path for explicit multi-source aggregation.
- [ ] Support one Telegram message containing multiple mixed links.
- [ ] Support link + forward + attachment combinations where feasible.
- [ ] Add API endpoints for submitting aggregation bundles outside Telegram.
- [ ] Add progress updates that show per-source extraction stages.
- [ ] Add final response rendering with source list, failures, and confidence/provenance notes.
- [ ] Decide how exports should include aggregation sessions and source item payloads.
- [ ] Decide whether aggregated outputs are searchable and how they relate to existing summary search.

### Deliverables

- End-user entry points for the new aggregation workflow.

## Phase 9: Validation, Observability, and Rollout

### Objective

Make the feature measurable, testable, and safe to release incrementally.

### TODO

- [ ] Add unit tests for each new extractor and shared normalization model.
- [ ] Add integration tests for mixed bundles across supported platforms.
- [ ] Add fixtures for Threads, Instagram posts, Instagram carousels, Instagram reels, Telegram posts, and X media posts.
- [ ] Add regression tests for current YouTube, X, URL, and Telegram flows.
- [ ] Add metrics for extraction success by platform, fallback tier, and media type.
- [ ] Add metrics for bundle-level partial success and synthesis coverage.
- [ ] Add feature flags for new extractors and bundle orchestration.
- [ ] Add cost and latency dashboards for multimodal and video-heavy workloads.
- [ ] Add a staged rollout plan: internal-only, owner-only beta, then wider default enablement.

### Deliverables

- Production readiness for the full multi-source aggregation workflow.

## Suggested Execution Order

1. Phase 1
2. Phase 2
3. Phase 4
4. Phase 5
5. Phase 3
6. Phase 6
7. Phase 7
8. Phase 8
9. Phase 9

## Definition of Done

- A single request can contain one or many mixed sources.
- Each source is extracted with source-specific logic or a controlled fallback.
- Multimodal content is preserved instead of silently downgraded to text-only.
- Aggregation no longer depends on URL-batch relationship detection.
- Threads, Instagram, Telegram media posts, X media posts, articles, and YouTube are all supported in the same workflow.
- The final summary includes provenance and handles partial extraction failures cleanly.
