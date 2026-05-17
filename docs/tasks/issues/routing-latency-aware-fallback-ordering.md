---
title: Re-order fallback chain by observed P95 latency to minimise time-to-response
status: backlog
area: llm
priority: medium
owner: TBD
blocks: []
blocked_by: []
created: 2026-05-08
updated: 2026-05-17
---

- [ ] #task Re-order fallback chain by observed P95 latency to minimise time-to-response #repo/ratatoskr #area/llm #status/backlog 🔽

## Problem

The fallback model chain is statically ordered by configuration. In practice, model P95 latencies shift with OpenRouter load, provider outages, and time of day. A model that is second in the list may be significantly faster than the first when the first provider is under load. Statically ordered fallbacks miss opportunities to reduce end-user wait time on retry.

## Proposed approach

- Create `app/core/fallback_orderer.py` with a `FallbackOrderer` class that queries `LatencyStatsRepository.get_latency_stats()` to obtain recent P95 latency per model.
- Cache the latency data for ~5 minutes to avoid hot-path database queries on every request.
- Reorder the fallback list at resolution time: keep the primary model fixed (user-configured first choice), then sort remaining models by P95 ascending.
- Apply a stickiness bias — only override configured order if the latency delta between candidate models exceeds a 2x threshold. This prevents thrashing when latencies are similar.
- Wire `FallbackOrderer` into `openrouter_client.py` model iteration so it is invoked once per request before the retry loop begins.
- Cold-start behavior (no latency data for a model): treat as lowest priority (appended after models with data).

## Open questions

- What stickiness threshold (2x) is correct? Should it be configurable via `MODEL_ROUTING_LATENCY_STICKINESS_FACTOR`?
- Should cold-start (unobserved) models be placed at the front or back of the reordered list? Placing them at the front enables faster exploration but increases tail latency risk.
- Does `LatencyStatsRepository` currently expose per-model P95 aggregates, or must a new query be added?

## Files to touch

- `app/core/fallback_orderer.py` (new)
- `app/adapters/openrouter/openrouter_client.py`
- `app/infrastructure/` (latency stats repository — verify existing API or add query)
- `app/config/llm.py` (optional: stickiness factor field)
