---
title: Add token-family REVOKE_FAMILY counter and critical Prometheus alert
status: backlog
area: observability
priority: high
owner: unassigned
blocks: []
blocked_by:
  - wire-token-family-rotation-and-add-logout-all
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Add token-family REVOKE_FAMILY counter and critical Prometheus alert #repo/ratatoskr #area/observability #status/backlog ⏫

## Objective

`TokenFamilyPolicy.decide` returns `REVOKE_FAMILY` only when a retired (not-revoked) token is replayed — the system's strongest "credential theft suspected" signal. Today this decision produces no metric and no alert; an active session-hijack attempt is forensically reconstructible from logs only, never proactively surfaced.

## Context

- Policy returns `REVOKE_FAMILY` at `app/security/token_family_policy.py:72-75`.
- `rg "REVOKE_FAMILY|revoke_family|token_family" app/observability/` returns zero hits.
- `ops/monitoring/alerting_rules.yml` mentions no token-family alert.
- Blocked by [[wire-token-family-rotation-and-add-logout-all]] — the metric has nothing to count until the policy is actually invoked on `/refresh`.

## Scope

- New Prometheus counter `ratatoskr_token_family_decisions_total{decision}` with labels for each `FamilyDecision` enum value (`ROTATE`, `REJECT`, `REVOKE_FAMILY`).
- Increment at the call site in `app/api/routers/auth/endpoints_sessions.py` (post-wiring) and `app/api/routers/auth/tokens.py` if rotation decisions land there too.
- Prometheus alert rule: any non-zero `revoke_family` rate over 5m → `severity: critical`, summary "Possible credential theft — family revocation detected".
- Unit test asserts the counter increments per decision kind.

## Acceptance criteria

- [ ] `ratatoskr_token_family_decisions_total{decision}` counter registered in `app/observability/`.
- [ ] Counter increments at every policy call site.
- [ ] Alert rule in `ops/monitoring/alerting_rules.yml` fires on any `revoke_family` increment over 5m.
- [ ] Unit / integration test exercises a REVOKE_FAMILY path and asserts the counter delta.

## References

- Policy: `app/security/token_family_policy.py:55-78`
- Metrics module: `app/observability/`
- Alert rules: `ops/monitoring/alerting_rules.yml`
- Depends on: [[wire-token-family-rotation-and-add-logout-all]]
