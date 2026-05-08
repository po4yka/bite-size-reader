---
title: Use a cheap LLM call to resolve ambiguous content tier classification
status: backlog
area: llm
priority: medium
owner: TBD
blocks: []
blocked_by: []
created: 2026-05-08
updated: 2026-05-08
---

- [ ] #task Use a cheap LLM call to resolve ambiguous content tier classification #repo/ratatoskr #area/llm #status/backlog 🔽

## Problem

`classify_content` uses keyword heuristics and domain signals. When both `tech_weight` and `socio_weight` are tied at >= 1 the function falls back to DEFAULT, losing the ability to route the request to the most appropriate specialist model. This ambiguity arises most often for interdisciplinary content (e.g. AI policy, bioinformatics regulation, tech-law). A single cheap LLM classification call (<$0.0001) would resolve the ambiguity in ~300ms and allow the correct specialist to be selected.

## Proposed approach

- Add an optional `LLMClassifier` service in `app/core/content_classifier.py` that is invoked only when `tech_weight == socio_weight >= 1` (tie case).
- The classifier sends a minimal prompt (~100 tokens) to a configurable cheap model (default: `qwen/qwen3.6-flash`) asking for a single-word tier label (`technical`, `sociopolitical`, `default`).
- Cache the classification result keyed on a hash of the URL (or first 512 chars of content) with a short TTL (e.g. 1 hour via Redis) to avoid duplicate LLM calls for the same article.
- Expose `LLM_CLASSIFIER_MODEL` and `LLM_CLASSIFIER_ENABLED` env vars; disabled by default (opt-in).
- When the LLM call fails or times out, fall through to the existing DEFAULT tier without raising.

## Open questions

- Which classifier model minimises latency/cost while producing reliable single-label output? `qwen/qwen3.6-flash` or `minimax/minimax-m2`?
- What is an acceptable latency budget for the classifier call? 300ms may be acceptable in background Telegram workflows but not in the mobile API hot path.
- Should the classification result be stored in `requests.lang_detected`-style column for analytics, or logged only?

## Files to touch

- `app/core/content_classifier.py`
- `app/config/llm.py` (new classifier config fields)
- `app/di/` (wire classifier service)
- `app/core/logging_utils.py` (structured log event for classifier call)
