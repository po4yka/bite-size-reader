---
title: Add Reddit and Hacker News as first-class scraper-chain providers
status: backlog
area: scraper
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Add Reddit and Hacker News as first-class scraper-chain providers #repo/ratatoskr #area/scraper #status/backlog 🔼

## Objective

`app/adapters/ingestors/reddit.py` and `app/adapters/ingestors/hn.py:27` exist for *signal ingestion* (background topic / feed listing) but are not registered in the scraper chain factory (`app/adapters/content/scraper/factory.py`). When a user pastes a single `reddit.com/comments` URL it goes through the generic chain (Scrapling / Playwright) and misses the free, stable JSON endpoint (`/comments/<id>.json`) that returns thread structure cleanly. Reddit + HN URLs are common, and each platform's JSON endpoint yields dramatic quality lift over screen scraping with one file per provider.

## Context

- Existing ingestors (signal layer): `app/adapters/ingestors/reddit.py:1`, `app/adapters/ingestors/hn.py:27`.
- Scraper-chain factory: `app/adapters/content/scraper/factory.py` — no `reddit` / `hn` builders.
- Existing provider pattern: `app/adapters/content/scraper/scrapling_provider.py` etc.

## Scope

- New `app/adapters/content/scraper/reddit_provider.py` implementing `ContentScraperProtocol` — calls `https://www.reddit.com/comments/<id>.json` (or `https://api.reddit.com/...`) for matching hosts only; assembles markdown with OP body + top-N replies.
- New `app/adapters/content/scraper/hn_provider.py` — calls the Algolia HN API (`https://hn.algolia.com/api/v1/items/<id>`) for matching hosts; assembles markdown with story + comment tree.
- Register both ahead of `scrapling` in the chain when the URL matches a known host pattern.
- Config flags: `SCRAPER_REDDIT_ENABLED=true`, `SCRAPER_HN_ENABLED=true`, `SCRAPER_REDDIT_USER_AGENT=...` (Reddit requires UA).
- Test fixtures: a known Reddit comment URL → OP body + top-5 replies as markdown; a known HN story URL → story + first-page comments.

## Acceptance criteria

- [ ] A Reddit comment URL summarized end-to-end produces visibly-better content than the generic chain.
- [ ] Same for an HN story URL.
- [ ] Providers only fire on matching hosts; non-matching URLs pass through to the existing chain unchanged.

## References

- Existing ingestors: `app/adapters/ingestors/reddit.py:1`, `app/adapters/ingestors/hn.py:27`
- Factory: `app/adapters/content/scraper/factory.py`
- Protocol: `app/adapters/content/scraper/protocols.py` (or equivalent)
