---
title: Add Slack, Discord, and Matrix outbound delivery channels
status: backlog
area: api
priority: low
owner: unassigned
blocks: []
blocked_by:
  - emit-summary-events-to-webhook-publisher
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Add Slack, Discord, and Matrix outbound delivery channels #repo/ratatoskr #area/api #status/backlog 🔽

## Objective

Incoming-webhook URLs for Slack / Discord work *today if* a user wires them via an AutomationRule, but there is no first-class "post my new summary to #channel" UX. No `app/adapters/slack/` / `discord/` / `matrix/`. Slack and Discord both accept simple JSON POSTs, so the work is mostly UX + formatter, not heavy SDK work.

## User story

As a team user, I want my new summaries to land in a shared Slack / Discord / Matrix channel automatically, so that my team sees what I just saved without me forwarding it.

## Context

- Generic webhook port covered by [[emit-summary-events-to-webhook-publisher]] — must land first.
- No `app/adapters/slack` / `discord` / `matrix` exists.

## Scope

- `delivery_channel` registry in `app/adapters/delivery/` (new) with three implementations: `slack`, `discord`, `matrix`.
- Each adapter consumes the `summary.created` event from [[emit-summary-events-to-webhook-publisher]].
- Markdown / block-kit formatter per channel: - Slack: Block Kit. - Discord: Embed. - Matrix: HTML message via the Matrix Client-Server API.
- Per-rule channel selection captured in `AutomationRule.actions_json` (or a new `delivery_channels` table).
- Config: per-user webhook URLs stored Fernet-encrypted using `app/security/token_crypto.py`.
- Metrics: `ratatoskr_delivery_dispatches_total{channel,outcome}`.

## Acceptance criteria

- [ ] User can configure a webhook URL per channel.
- [ ] New summary delivers to the configured channel within 30 seconds.
- [ ] Format renders correctly in each target client.
- [ ] Failure path retries per webhook policy.

## References

- Depends on: [[emit-summary-events-to-webhook-publisher]]
- Token storage: `app/security/token_crypto.py`
- Models: `app/db/models/rules.py:AutomationRule`
