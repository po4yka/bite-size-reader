# Multi-Source Aggregation Roadmap

## Status

Completed.

The mixed-source aggregation workflow described in this roadmap is implemented in the main codebase and covered by tests. The system now supports one or many mixed sources in a single bundle, preserves multimodal inputs, stores provenance-rich extraction results, and produces one synthesized aggregation output with coverage, duplicate, and contradiction signals.

## Delivered End State

Supported bundle inputs now include:

- X posts
- X article links
- Threads posts
- Instagram posts
- Instagram carousels
- Instagram reels
- Web articles
- Telegram forwarded posts
- Telegram posts with images
- Telegram albums
- YouTube videos

The shared pipeline accepts mixed bundles, extracts each item with source-specific logic or a controlled fallback, persists per-item results, and synthesizes one source-aware output even when only part of the bundle succeeds.

## Phase Status

### Phase 1: Foundations

Implemented.

- Shared source taxonomy and bundle primitives live in `app/domain/models/source.py`.
- Shared extraction and synthesis DTOs live in `app/application/dto/aggregation.py`.
- Aggregation session persistence lives in `app/db/_models_aggregation.py`.
- Database support landed in `app/db/migrations/021_add_aggregation_sessions.py` and `app/db/migrations/022_add_aggregation_session_lifecycle.py`.
- Stable IDs, dedupe keys, and bundle/item failure storage are implemented in the domain model plus the aggregation session repository.

### Phase 2: Unified Extraction Orchestrator

Implemented.

- `app/agents/multi_source_extraction_agent.py` is the heterogeneous extraction entry point.
- URL and Telegram-native classification lives in `app/adapters/content/multi_source_classification.py`.
- Mixed inputs are accepted through `SourceSubmission` and routed per item.
- Partial success is first-class: one failed source does not discard the whole bundle.
- Item-level extraction status, normalized payload, duplicates, and failures are persisted and returned.

### Phase 3: Threads and Instagram Coverage

Implemented.

- Dedicated URL detection lives in `app/core/urls/meta.py`.
- First-class Threads and Instagram extraction lives in `app/adapters/meta/platform_extractor.py`.
- Threads quoted context, image/video metadata, Instagram post/carousel/reel handling, and login-wall fallback tiers are implemented.
- Shared fixtures and tests cover these paths in `tests/test_meta_platform_extractor.py`, `tests/core/urls/test_meta.py`, and `tests/agents/test_multi_source_extraction_agent.py`.

### Phase 4: Telegram Multimodal Completion

Implemented.

- Telegram multimodal extraction lives in `app/adapters/telegram/multimodal_extractor.py`.
- Forwarded caption + media, albums/media groups, ordered images, forwarded provenance, and video handoff into the shared video extractor are implemented.
- Telegram routing uses these paths through `app/adapters/telegram/routing/content_router.py`.
- Coverage exists in `tests/test_telegram_multimodal_extractor.py` and `tests/test_forward_routing.py`.

### Phase 5: X and Article Multimodal Upgrades

Implemented.

- X/Twitter platform extraction preserves image URLs, alt text, and quoted-post media metadata through `app/adapters/twitter/platform_extractor.py` and `app/adapters/twitter/extraction_coordinator.py`.
- Article image selection, filtering, and decorative/tracker rejection live in `app/adapters/content/article_media.py`.
- Generic article extraction propagates normalized multimodal article documents through `app/adapters/content/content_extractor.py`.
- Coverage exists in `tests/test_twitter_platform_extractor.py` and `tests/test_platform_extraction_router.py`.

### Phase 6: Video Extraction Beyond YouTube

Implemented.

- The shared interface and metadata-driven implementation live in `app/adapters/video/source_extractor.py`.
- The extractor is reused for Instagram reels and Telegram videos, and complements the YouTube pipeline.
- Transcript, audio-transcript, OCR/frame-text, media provenance, and runtime controls are included in the normalized output.
- Coverage exists in `tests/test_video_source_extractor.py`, `tests/test_meta_platform_extractor.py`, `tests/test_telegram_multimodal_extractor.py`, and `tests/test_youtube_platform_extractor.py`.

### Phase 7: Aggregated Synthesis and Output Contract

Implemented.

- `app/agents/multi_source_aggregation_agent.py` synthesizes extracted bundle items.
- Bundle synthesis no longer depends on relationship gating; relationship analysis is optional enrichment.
- Duplicate detection, contradiction hints, provenance-aware claims, evidence weighting, source coverage, and mixed-source typing are implemented.
- The persisted aggregation output contract lives in `app/application/dto/aggregation.py`.
- Coverage exists in `tests/agents/test_multi_source_aggregation_agent.py`.

### Phase 8: API, Telegram UX, and Product Surface

Implemented.

- Telegram `/aggregate` command support lives in `app/adapters/telegram/command_handlers/aggregation_commands_handler.py`.
- Telegram bundle handling and progress rendering live in `app/adapters/telegram/multi_source_aggregation_handler.py`.
- Mixed-link and link-plus-forward-or-attachment routing lives in `app/adapters/telegram/routing/content_router.py`.
- REST API create/get/list support lives in `app/api/routers/aggregation.py`.
- Aggregated outputs are persisted and retrievable as dedicated aggregation sessions. Legacy summary search remains separate by design until a dedicated aggregation search read model is introduced.

### Phase 9: Validation, Observability, and Rollout

Implemented.

- Unit and integration coverage exists for domain models, extractors, synthesis, persistence, API, CLI, MCP, and routing.
- Fixture-backed bundle tests cover Threads, Instagram, Telegram, X, YouTube, and generic web article flows.
- Aggregation metrics, bundle success/partial-success signals, synthesis coverage metrics, rollout flags, and deployment guidance are implemented.
- Key files include `tests/agents/test_multi_source_extraction_agent.py`, `tests/agents/test_multi_source_aggregation_agent.py`, `tests/observability/test_aggregation_metrics.py`, `tests/test_aggregation_rollout.py`, and `docs/DEPLOYMENT.md`.

## Definition of Done

Completed.

- A single request can contain one or many mixed sources.
- Each source is extracted with source-specific logic or a controlled fallback.
- Multimodal content is preserved instead of silently downgraded to text-only.
- Aggregation no longer depends on URL-batch relationship detection.
- Threads, Instagram, Telegram media posts, X media posts, articles, and YouTube are supported in the same workflow.
- The final summary includes provenance and handles partial extraction failures cleanly.
