---
title: Emit summary.created / summary.failed / digest.delivered events to the webhook publisher
status: backlog
area: api
priority: high
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Emit summary.created / summary.failed / digest.delivered events to the webhook publisher #repo/ratatoskr #area/api #status/backlog ⏫

## Objective

The outbound-webhook system is 90% built: `WebhookSubscription` + `WebhookDelivery` models exist, the dispatcher is wired, and the HTTP adapter is plumbed. But webhook firing is **only invoked from the `RuleExecution` use case** — there is no first-class event publisher that auto-fires `summary.created` / `summary.failed` / `digest.delivered` to all matching subscribers. Subscribers currently have to author an AutomationRule per event type to receive anything, which is a steep cliff vs the standard "subscribe → POSTs" UX.

## User story

As an integrator (Zapier / IFTTT / custom service), I want to subscribe to event types and receive HTTP POSTs whenever events match, so that I can wire Ratatoskr into my own pipeline without defining an AutomationRule for every event.

## Context

- Models: `app/db/models/rules.py:13-79`.
- Dispatcher: `app/infrastructure/messaging/handlers/webhook_dispatcher.py:38`, wired at `app/infrastructure/messaging/wiring.py:123-125`.
- HTTP adapter: `app/di/application.py:23` (`HttpWebhookDispatchAdapter`).
- Router: `app/api/routers/webhooks.py`.
- Only-trigger today: `app/application/use_cases/rule_execution.py:269`.

## Scope

- Publish domain events from existing use cases: - `SummaryCreated` from the URL processor + multi-source aggregator. - `SummaryFailed` from the same paths on terminal failure. - `DigestDelivered` from the digest service after successful Telegram delivery.
- Default fan-out: for each enabled `WebhookSubscription` whose `events_json` includes the type, dispatch via the existing HTTP adapter; persist one `WebhookDelivery` row per attempt.
- Retry + `failure_count` + `status` lifecycle already exist — ensure they update correctly under the new publisher.
- Add `ratatoskr_webhook_dispatches_total{event_type,outcome}` Prometheus counter.
- Document the event-type catalog in `docs/reference/webhooks.md` (or extend `docs/reference/mobile-api.md`).

## Acceptance criteria

- [ ] Creating a summary triggers exactly one dispatch per matching subscription.
- [ ] `WebhookDelivery` row written for every attempt with request/response metadata.
- [ ] Retries respect existing backoff; terminal failures stop retrying.
- [ ] Event-type catalog documented.
- [ ] E2E test asserts a 200 delivery row.

## References

- Models: `app/db/models/rules.py:13-79`
- Dispatcher: `app/infrastructure/messaging/handlers/webhook_dispatcher.py:38`
- Existing rule path: `app/application/use_cases/rule_execution.py:269`
- Related: [[add-slack-discord-matrix-delivery-channels]]
