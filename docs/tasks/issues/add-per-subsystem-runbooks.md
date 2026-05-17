---
title: Add per-subsystem on-call runbooks for the 6 critical subsystems
status: backlog
area: docs
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Add per-subsystem on-call runbooks for the 6 critical subsystems #repo/ratatoskr #area/docs #status/backlog 🔼

## Objective

`docs/runbooks/` contains exactly **one** file
(`pi-postgres-cutover.md`). At 2 a.m. the on-call needs "what is
broken, how do I prove it, how do I restart it" — not architecture
explanation. Today they would page the maintainer. Existing skills
(e.g. `digest-subsystem-ops`, `scraper-chain-debugging`) are
debugger guidance, not on-call runbooks.

## Context

- `docs/runbooks/pi-postgres-cutover.md` — only existing runbook.
- Subsystems with no runbook: digest userbot (`/init_session`
  lockouts), scraper-chain stuck on a degraded provider, LLM
  cascade exhaustion, vector reconciler backlog, GitHub sync
  rate-limit pause, Taskiq worker stuck.

## Scope

Author at minimum these 6 runbooks under `docs/runbooks/`:

- `digest-userbot.md` — session expiry, OTP/2FA flow recovery,
  channel-removal handling.
- `scraper-chain.md` — provider stuck, force-skip a provider,
  evaluate the attempt log.
- `llm-cascade.md` — outer-budget exhaustion, single-model
  rate-limit, OpenRouter outage failover.
- `vector-reconcile.md` — reconciler backlog, Qdrant outage,
  re-index a subset.
- `github-sync.md` — rate-limit recovery, PAT revoked, daily
  budget exhausted.
- `taskiq-worker.md` — worker stuck, drain queue, replay DLQ
  (depends on [[add-taskiq-retry-middleware-and-dlq]]).

Each runbook follows a shared template:

1. Symptoms (what alerts fire / user-visible behaviour).
2. Log queries (Loki / `docker logs`).
3. Prometheus panels (links to Grafana).
4. Mitigation steps (numbered).
5. Escalation (when to page the maintainer).

## Acceptance criteria

- [ ] All 6 runbooks published.
- [ ] Each follows the shared template.
- [ ] CLAUDE.md links the runbook directory.
- [ ] Each runbook references the relevant alert rule + Grafana
  panel.

## References

- Existing runbook: `docs/runbooks/pi-postgres-cutover.md`
- Skill scaffolding (debug-side):
  `.claude/skills/digest-subsystem-ops/`,
  `.claude/skills/scraper-chain-debugging/`
- Related: [[add-taskiq-retry-middleware-and-dlq]],
  [[wire-alertmanager-for-prometheus-and-loki-alerts]]
