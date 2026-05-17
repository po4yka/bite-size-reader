---
title: Cascade to stronger model on JSON-parse failure during summarization
status: backlog
area: llm
priority: medium
owner: TBD
blocks: []
blocked_by: []
created: 2026-05-08
updated: 2026-05-17
---

- [ ] #task Cascade to stronger model on JSON-parse failure during summarization #repo/ratatoskr #area/llm #status/backlog 🔽

## Problem

Every summarization request is routed to a single model regardless of whether the response is well-formed JSON. Cheap flash models are fast but occasionally produce malformed or low-confidence output. Today the caller either retries the same model or falls back via the standard retry budget. There is no mechanism to escalate to a stronger model specifically when the cheaper model's response fails JSON validation or confidence checks. This wastes the retry budget on a model that has already demonstrated it cannot handle the request, while expensive ceiling models (`technical_model`, `deepseek-v4-pro`) remain unused for the vast majority of simple inputs.

## Proposed approach

- Add a "soft failure" detection hook in `app/adapters/llm/` or `app/adapters/openrouter/openrouter_client.py` that fires after each attempt: JSON parse error, schema validation failure (from `app/core/summary_contract.py`), or explicit low-confidence signal triggers escalation rather than same-model retry.
- On soft failure, advance to the next model in the tier-specific fallback chain (`technical_fallback_models` for TECHNICAL tier, else shared `fallback_models`) instead of retrying the same model.
- Hard 4xx/5xx errors continue to use the existing retry/fallback path unchanged.
- Introduce a max-escalation budget (e.g. 2 escalations per request) to cap cost exposure.
- Log the escalation event with `correlation_id`, failed model name, and failure reason for observability.

## Open questions

- Where is the cleanest seam to detect "soft failure" vs hard 4xx — inside `openrouter_client.py` after `json_repair` or inside `SummarizationAgent`'s validation loop?
- Should the cost cap be a separate env var (`MODEL_ROUTING_MAX_ESCALATIONS`) or derived from the fallback chain length?
- Does escalation interact with the `SummarizationAgent` self-correction retry loop (up to 3x)? Must ensure the two mechanisms don't compound beyond the intended retry budget.

## Files to touch

- `app/adapters/openrouter/openrouter_client.py`
- `app/adapters/llm/` (orchestrator layer)
- `app/agents/summarization_agent.py`
- `app/core/summary_contract.py` (expose validation result for callers)
- `app/config/llm.py` (optional: max escalation budget field)
