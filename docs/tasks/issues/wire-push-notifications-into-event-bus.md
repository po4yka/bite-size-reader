---
title: Wire PushNotificationEventHandler into DI so summary-ready events reach devices
status: backlog
area: api
priority: high
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Wire PushNotificationEventHandler into DI so summary-ready events reach devices #repo/ratatoskr #area/api #status/backlog ⏫

## Objective

`PushNotificationService` and `PushNotificationEventHandler` are
fully implemented, the FCM/APNS device-token endpoint accepts and
stores tokens, but **nothing subscribes the handler to the event
bus**. Mobile clients can register tokens but no event ever
triggers a delivery. Push is the canonical "summary is ready"
signal for users who close the app — its absence forces polling
or "keep app open" UX.

## User story

As a mobile user with a registered device token, I want a push
notification when my summary finishes, so that I don't have to
keep the app open or poll.

## Context

- Service: `app/infrastructure/push/service.py:34` defines
  `PushNotificationService.send_to_user`.
- Handler: `app/infrastructure/messaging/handlers/push_notification.py:16`
  implements `PushNotificationEventHandler.on_summary_created`.
- Endpoint: `app/api/routers/notifications.py:27` accepts +
  stores tokens.
- DI: `app/di/application.py:42` declares
  `push_notification_service` as an optional parameter; nothing
  constructs or subscribes the handler in `app/api/main.py`,
  `bot.py`, or `app/di/api.py`.
- Repo-wide grep for `PushNotificationEventHandler` /
  `push_notification_handler` / `register.*on_summary_created`
  returns no wiring.

## Scope

- In the DI runtime (`app/di/application.py` or `app/di/api.py`),
  construct `PushNotificationEventHandler` when
  `PUSH_NOTIFICATIONS_ENABLED=true`.
- Subscribe the handler to `SummaryCreated` (and `SummaryFailed`
  if appropriate) on the event bus.
- Handle FCM/APNS failure modes:
  - Invalid / expired token →
    `device_repo.async_disable_token(...)`.
  - Transient failures retry per the existing backoff policy.
- Add Prometheus counter
  `ratatoskr_push_deliveries_total{outcome}` (success, retry,
  invalid_token, failed).
- Update `docs/reference/environment-variables.md` with the
  `PUSH_NOTIFICATIONS_*` block.

## Acceptance criteria

- [ ] When `PUSH_NOTIFICATIONS_ENABLED=true`, an end-to-end test
  with a fake `firebase_admin.messaging.send` records exactly one
  delivery per completed summary.
- [ ] Invalid-token responses disable the offending device row.
- [ ] Counter increments per outcome.
- [ ] No push deliveries fire when feature flag is off.

## References

- Service: `app/infrastructure/push/service.py:34`
- Handler: `app/infrastructure/messaging/handlers/push_notification.py:16`
- Endpoint: `app/api/routers/notifications.py:27`
- DI: `app/di/application.py:42`
