---
title: Instrument web search enrichment agent with decision counters
status: backlog
area: observability
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Instrument web search enrichment agent with decision counters #repo/ratatoskr #area/observability #status/backlog 🔼

## Objective

`WebSearchAgent` runs an extra OpenRouter call on top of standard
summarization, but has no per-request counters or hit/skip ratio.
Cost regressions and "is the enrichment actually firing as
intended" questions can only be answered via log scraping.

## Context

- Agent: `app/agents/web_search_agent.py`.
- `rg "metric|prometheus|record_" app/agents/web_search_agent.py`
  returns no hits; only structured logging at line 158
  (`web_search_completed`).

## Scope

- New counter `ratatoskr_web_search_decisions_total{decision}` —
  labels for `executed`, `skipped_low_value`, `skipped_disabled`,
  `failed`.
- New histogram `ratatoskr_web_search_query_results` — number of
  results returned per query.
- Tie web-search cost into the existing
  `ratatoskr_openrouter_cost_usd` metric via a `purpose="web_search"`
  label if not already separable.
- Alert: `executed` rate > 2× baseline for 30m → warning (= cost
  regression).

## Acceptance criteria

- [ ] Both metrics registered and incremented per request.
- [ ] OpenRouter cost label exposes web-search vs summary separately.
- [ ] Alert rule added.
- [ ] Unit test asserts counter increments per decision kind.

## References

- Agent: `app/agents/web_search_agent.py:158`
- Web search guide: `docs/guides/enable-web-search.md`
