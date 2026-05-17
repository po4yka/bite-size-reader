---
title: Add email delivery sink for digests and individual summaries
status: backlog
area: api
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Add email delivery sink for digests and individual summaries #repo/ratatoskr #area/api #status/backlog 🔼

## Objective

Ratatoskr can deliver to Telegram (✓), Mobile API (✓), Web (✓),
and (with this task done) outbound webhooks. There is no email
sink — no `smtp|sendgrid|resend|postmark` references anywhere in
`app/adapters` or `app/api/services`. Email is the only sink that
reaches users without an app installed and is the single
most-requested delivery channel for read-it-later products.

## User story

As a user who lives in email, I want my daily / weekly digest
delivered to my inbox, so that I see new summaries without
opening Telegram or the app.

## Context

- Grep for `smtp|sendgrid|resend|postmark` → zero hits under
  `app/`.
- Existing digest pipeline (Telegram-only):
  `app/adapters/digest/`.
- Existing RSS inbound delivery:
  `app/adapters/rss/rss_delivery_service.py:110`.
- `CustomDigest` / `UserDigestPreference` already model
  per-user digest config.

## Scope

- New `app/adapters/email/` with `EmailDeliveryProtocol` and at
  minimum a Resend (or SMTP) implementation behind
  `EMAIL_PROVIDER=resend|smtp|none`.
- Extend `CustomDigest` / `UserDigestPreference` with
  `delivery_channel = "email"` option.
- Address verification flow (one-time email-confirmation token);
  store in new `user_email_addresses` table.
- Bounce / error path persists into `email_deliveries` table OR
  reuses `WebhookDelivery` schema (decide which is less
  duplicative).
- Metrics: `ratatoskr_email_deliveries_total{outcome}`.
- Document env vars and provider tradeoffs in
  `docs/reference/environment-variables.md`.

## Acceptance criteria

- [ ] User can verify an email address and pick it as digest
  channel.
- [ ] Daily digest delivered to verified address with consistent
  formatting.
- [ ] Bounce / hard-fail surfaces in delivery log.
- [ ] Feature gated by env flag; off by default.

## References

- Existing digest pipeline: `app/adapters/digest/`
- RSS delivery (for shape comparison):
  `app/adapters/rss/rss_delivery_service.py:110`
- Models:
  `app/db/models/digest.py:CustomDigest`,
  `UserDigestPreference`
