---
title: Add public RSS / Atom feed of user's saved summaries
status: backlog
area: api
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Add public RSS / Atom feed of user's saved summaries #repo/ratatoskr #area/api #status/backlog 🔼

## Objective

RSS is inbound only today — `app/adapters/rss/` ingests *into*
the user, and `app/api/routers/social/rss.py` manages subscriptions.
There is no outbound user-facing feed (grep for `feed\.xml`,
`users.*rss`, `output.*rss` returns zero). Adding one is a tiny
add (one router + `feedgen` template) that gives Obsidian /
Readwise / IFTTT a pull integration without writing per-vendor
connectors.

## User story

As a user with tools like Obsidian, Readwise, or IFTTT, I want a
private RSS feed URL of my saved summaries, so that I can wire
Ratatoskr into the rest of my stack without bespoke connectors.

## Context

- Inbound RSS subscriptions:
  `app/api/routers/social/rss.py`.
- No outbound feed endpoint.
- `SummaryService` already has "read-by-user" query paths.

## Scope

- New `GET /v1/users/me/feed.xml?token=<rss-token>` returns Atom
  feed of the latest N summaries for the user.
- Token storage: extend existing `ClientSecret` OR add an
  `rss_feed_tokens` table.
- Token rotation endpoint + revocation.
- `ETag` + `Cache-Control: private, max-age=300` headers.
- Optional query params: `tag=...`, `collection=...`,
  `language=en|ru`.
- Document in OpenAPI spec + reference doc + add a usage
  example with Obsidian.

## Acceptance criteria

- [ ] Feed validates as Atom 1.0 (W3C validator).
- [ ] Token rotation invalidates the old URL.
- [ ] `If-None-Match` returns 304 when unchanged.
- [ ] Documented end-to-end.

## References

- Inbound RSS:
  `app/api/routers/social/rss.py`
- Existing token storage pattern:
  `app/db/models/core.py:ClientSecret`
