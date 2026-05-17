# LLM call retry-budget telemetry

This page documents the Prometheus signals exposed for the LLM
summarization retry loop and the operator-facing alert that fires when
those signals indicate trouble.

## Exposed metrics

| Metric | Type | Labels | Notes |
| --- | --- | --- | --- |
| `ratatoskr_llm_call_attempts_total` | counter | `provider`, `model`, `status` | Incremented for every attempt the retry loop issues, including same-model retries and fallback-model retries. `status` is free-form (`success`, `error`, `soft_failure`, `timeout`). |
| `ratatoskr_llm_call_retry_exhaustion_total` | counter | `model` | Incremented **once per request** when the entire fallback chain has been exhausted without success. `model` is the *primary* model the request started with. |
| `ratatoskr_llm_call_latency_seconds` | histogram | `model` | End-to-end latency of a single attempt. Buckets: 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300 s. |

All three metrics are emitted by `app/observability/metrics.py`. When
`prometheus_client` is not installed the recorder functions no-op
(see ``record_llm_call_attempt`` / ``record_llm_call_retry_exhaustion``
/ ``record_llm_call_latency``).

## Alert rule

Defined in `ops/monitoring/alerting_rules.yml` under the
`ratatoskr_llm_retry_budget` group:

```yaml
- alert: RatatoskrLLMRetryExhaustionHigh
  expr: |
    (
      sum(rate(ratatoskr_llm_call_retry_exhaustion_total[15m]))
      /
      sum(rate(ratatoskr_llm_call_attempts_total{status="success"}[15m]))
    ) > 0.05
  for: 5m
  labels:
    severity: warning
```

Trigger: more than 5% of summarization requests in a 15-minute window
burn through the entire fallback chain. Sustained for 5 minutes before
paging to absorb transient OpenRouter blips.

## Operator playbook

1. Check the OpenRouter status page and the upstream provider that the
   primary `model` label points at.
2. Inspect recent commits to `app/prompts/summary_system_*.txt` —
   a prompt regression can spike soft-failure rate without any
   provider-side change.
3. Inspect the per-model latency histogram for the same window. A
   tail latency spike often precedes retry-exhaustion by a few minutes.
4. If the spike is correlated with a specific upstream provider name
   (visible in the `openrouter_provider_rotation` audit events), the
   provider-rotation tracker should be limiting the fallout — verify
   `MODEL_ROUTING_MAX_PROVIDER_ROTATIONS` is non-zero.

## Follow-ups not in this change

Per the task spec, two additional pieces remain:

1. Persist `fallback_model_used`, `retry_exhausted`, and
   `total_latency_ms` on the `llm_calls` table (Alembic migration +
   model edit + back-fill-safe defaults).
2. Surface fallback-model usage in the summary `meta` blob so
   downstream agents can detect quality drift.

Both are tracked under the original task issue and remain to be
implemented in a follow-up commit.
