---
title: Wire LLM retry-budget recorder into chat response handler
status: backlog
area: observability
priority: high
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Wire LLM retry-budget recorder into chat response handler #repo/ratatoskr #area/observability #status/backlog ⏫

## Objective

Migration `0014_add_llm_call_retry_budget_columns.py` added `fallback_model_used`, `retry_exhausted`, and `total_latency_ms` columns on `llm_calls` (commit `da8195f1`), and Prometheus signals + the alert rule shipped in `31605c9b`. But the chat response handler never populates the columns, so the migration ships dead columns and the retry-cascade visibility promised in `docs/reference/llm-retry-telemetry.md` does not exist at runtime.

## Context

- Columns defined: `app/db/models/core.py:480-484` — comment on the columns explicitly says "populated… when wiring lands".
- `rg -n "fallback_model_used|retry_exhausted" app/` returns only the model definition, the migration, and one unrelated log key in `app/utils/retry_utils.py:155`.
- Success outcome built at `app/adapters/openrouter/chat_response_handler.py:145-171` without setting the new columns.
- Terminal error and exhausted-retry outcomes built at `app/adapters/openrouter/chat_response_handler.py:228-295` without setting `retry_exhausted=true`.
- Completion record (`docs/tasks/COMPLETION-2026-05-17.md`) flags this as inline TODO #1.

## Scope

- On a successful response, set `fallback_model_used` to the model the cascade landed on (or `NULL` when first-try success).
- Set `total_latency_ms` to the cascade-wide wall clock for every recorded `llm_calls` row (success and failure).
- On any terminal non-retryable error path AND the exhausted-retry path, set `retry_exhausted=true`.
- Confirm the new columns flow through the `LLMCallRepository` insert path with no schema-mismatch error.

## Acceptance criteria

- [ ] Successful first-try response writes `fallback_model_used=NULL`, `total_latency_ms>0`, `retry_exhausted=false`.
- [ ] Successful response after one fallback writes `fallback_model_used=<actual model>`, `retry_exhausted=false`.
- [ ] Exhausted-retry path writes `retry_exhausted=true` and a non-null `total_latency_ms`.
- [ ] Repository / integration test asserts both columns on a forced cascade across two models.

## References

- Handler: `app/adapters/openrouter/chat_response_handler.py:145-295`
- Model: `app/db/models/core.py:LLMCall` (lines 480-484)
- Migration: `app/db/alembic/versions/0014_add_llm_call_retry_budget_columns.py`
- Telemetry doc: `docs/reference/llm-retry-telemetry.md`
- Completion record: `docs/tasks/COMPLETION-2026-05-17.md` (inline TODO #1)
