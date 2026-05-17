---
title: Wire Alertmanager so Prometheus and Loki alerts route to a receiver
status: backlog
area: observability
priority: high
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Wire Alertmanager so Prometheus and Loki alerts route to a receiver #repo/ratatoskr #area/observability #status/backlog ⏫

## Objective

Prometheus and Loki are configured with 19+ alert rules but `ops/monitoring/prometheus.yml:10-14` has the Alertmanager section **commented out**, `ops/monitoring/loki-config.yml:67` has `alertmanager_url: ""`, and `ops/docker/docker-compose.yml:761-829` declares no Alertmanager service. Every alert fires into a black hole — incidents are discovered only by user complaints. This also nullifies the 10 new metrics + alerts queued in today's audit batch.

## Context

- Prometheus alert config: `ops/monitoring/prometheus.yml:10-14` (commented).
- Loki alert URL: `ops/monitoring/loki-config.yml:67` (empty).
- Monitoring stack: `ops/docker/docker-compose.yml:761-829` — Prometheus + Grafana + Loki, no Alertmanager.
- Existing rules: `ops/monitoring/alerting_rules.yml` (19+ rules that evaluate but route nowhere).

## Scope

- Add `alertmanager` service to `ops/docker/docker-compose.monitoring.yml` (or main compose file) pinned to a tested upstream image.
- Provide a default `alertmanager.yml` with env-templated receivers — at minimum a webhook receiver driven by `ALERT_WEBHOOK_URL`.
- Uncomment the Prometheus `alerting:` block; set `loki-config.yml:67` to `http://alertmanager:9093`.
- Provide example receiver configs for Slack, Telegram bot webhook, and PagerDuty as commented snippets in the file.
- Document the new env var and topology in `docs/explanation/observability-strategy.md` and `docs/reference/environment-variables.md`.
- Add a startup self-check: log error if no receivers configured in production.

## Acceptance criteria

- [ ] Alertmanager runs in the monitoring compose stack.
- [ ] A firing rule reaches the configured webhook in a manual test.
- [ ] Loki ruler delivers alerts to the same Alertmanager.
- [ ] Docs updated.

## References

- Prometheus config: `ops/monitoring/prometheus.yml:10-14`
- Loki config: `ops/monitoring/loki-config.yml:67`
- Compose: `ops/docker/docker-compose.yml:761-829`
- Alert rules: `ops/monitoring/alerting_rules.yml`
