---
title: Add LLM call retry-budget telemetry
status: backlog
area: observability
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-04-30
updated: 2026-05-04
---

- [ ] #task Add LLM call retry-budget telemetry #repo/ratatoskr #area/observability #status/backlog 🔼

## Goal

Expose how often summarization burns its retry budget so OpenRouter outages and prompt regressions show up in metrics, not in user complaints.

## Scope

- Persist on every `LLMCall`: attempt index, fallback model used (vs. primary), retry-exhaustion flag, total wall-clock latency.
- Prometheus: `llm_call_attempts_total{provider,model,status}`, `llm_call_retry_exhaustion_total{model}`, histogram `llm_call_latency_seconds{model}`.
- Surface fallback model usage in summary `meta` so downstream agents can detect quality drift.
- Alert recipe in docs: trigger when retry exhaustion rate >5%/15min.

## Acceptance criteria

- [ ] New columns/JSON keys backfilled-safe (nullable) and documented in `docs/SPEC.md` data model section.
- [ ] `/metrics` exposes the listed counters/histogram.
- [ ] One Grafana panel + a documented alert rule.

## References

- `app/adapters/openrouter/`, `app/adapters/llm/`
- `app/db/models.py` (`LLMCall`)
